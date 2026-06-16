"""Orders router — FastAPI endpoints.

All endpoints enforce event-driven transitions (Spec §1.2).
Direct state mutation is FORBIDDEN.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.orders.fsm import OrderFSM, OrderState, get_order_fsm
from app.domains.orders.models import Order
from app.domains.orders.schemas import (
    OrderCreate,
    OrderRead,
    OrderStateInfo,
    OrderTransitionRequest,
    OrderTransitionResponse,
)
from app.domains.orders.terminal_tools import OrderTerminalTool, get_terminal_tool
from app.trace.service import TraceService

router = APIRouter(prefix="/orders", tags=["orders"])


async def _get_order_or_404(session: AsyncSession, order_id: str) -> Order:
    """Fetch order by ID or raise 404."""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    return order


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
)
async def create_order(
    data: OrderCreate,
    session: AsyncSession = Depends(get_db),
    terminal: OrderTerminalTool = Depends(get_terminal_tool),
) -> Order:
    """Create a new order in DRAFT state.

    The order is created through the terminal tool — the only valid
    path for writing order state.
    """
    items_data = [
        {
            "menu_item_id": item.menu_item_id,
            "name": item.name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        }
        for item in data.items
    ]

    async with session.begin():
        order = await terminal.create_order(
            session,
            customer_id=data.customer_id,
            customer_phone=data.customer_phone,
            customer_address=data.customer_address,
            items_data=items_data,
            currency=data.currency,
        )

    await session.refresh(order)
    return order


@router.get(
    "",
    response_model=list[OrderRead],
    summary="List orders",
)
async def list_orders(
    state: OrderState | None = None,
    customer_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[Order]:
    """List orders with optional filtering."""
    query = select(Order).order_by(Order.created_at.desc())

    if state:
        query = query.where(Order.current_state == state.value)
    if customer_id:
        query = query.where(Order.customer_id == customer_id)

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Get order by ID",
)
async def get_order(
    order_id: str,
    session: AsyncSession = Depends(get_db),
) -> Order:
    """Get a single order by ID."""
    return await _get_order_or_404(session, order_id)


@router.post(
    "/{order_id}/transition",
    response_model=OrderTransitionResponse,
    summary="Execute order state transition",
)
async def transition_order(
    order_id: str,
    request: OrderTransitionRequest,
    session: AsyncSession = Depends(get_db),
    fsm: OrderFSM = Depends(get_order_fsm),
    terminal: OrderTerminalTool = Depends(get_terminal_tool),
) -> OrderTransitionResponse:
    """Execute an event-driven state transition on an order.

    Core invariant (Spec §1.2):
        Accepts EVENT, never new_state.

    Example:
        POST /orders/{id}/transition
        {"event": "CONFIRM"}

        POST /orders/{id}/transition
        {"event": "PAYMENT_CONFIRMED"}
    """
    async with session.begin():
        order = await _get_order_or_404(session, order_id)

        previous_state = order.current_state
        current_state_enum = OrderState(previous_state)

        # Step 1: FSM validates the event (graph-only, no business logic)
        result = fsm.transition(order_id, request.event, current_state_enum)

        if not result.success:
            return OrderTransitionResponse(
                success=False,
                order_id=order_id,
                previous_state=previous_state,
                new_state=None,
                event=request.event.value,
                reason=result.reason,
                trace_id=None,
            )

        # Step 2: Terminal tool atomically writes new state (ADR-001)
        new_state = OrderState(result.new_state.value) if result.new_state else current_state_enum

        await terminal.write_state(
            session,
            order_id=order_id,
            new_state=new_state,
            event=request.event.value,
            previous_state=previous_state,
            metadata=request.metadata,
        )

    await session.refresh(order)

    return OrderTransitionResponse(
        success=True,
        order_id=order_id,
        previous_state=previous_state,
        new_state=new_state.value,
        event=request.event.value,
        reason=None,
        trace_id=None,  # M1: trace_id generated internally
    )


@router.get(
    "/{order_id}/state",
    response_model=OrderStateInfo,
    summary="Get order state and allowed events",
)
async def get_order_state(
    order_id: str,
    session: AsyncSession = Depends(get_db),
    fsm: OrderFSM = Depends(get_order_fsm),
) -> OrderStateInfo:
    """Get current order state and graph-level allowed events.

    Note (Spec §3.1, §ADR-004):
        Returns graph-level allowed events ONLY.
        Business rules = PolicyProvider (separate layer).
    """
    order = await _get_order_or_404(session, order_id)
    current_state = OrderState(order.current_state)
    allowed = fsm.get_allowed_events(current_state)

    return OrderStateInfo(
        order_id=order_id,
        current_state=current_state,
        allowed_events=[e.value for e in allowed],
    )


@router.get(
    "/{order_id}/trace",
    summary="Get order trace history",
)
async def get_order_trace(
    order_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    """Get trace (event history) for an order."""
    # Verify order exists
    await _get_order_or_404(session, order_id)

    trace_service = TraceService()
    entries = await trace_service.get_entries_for_order(
        session,
        order_id,
        limit=limit,
        offset=offset,
    )

    return [
        {
            "id": entry.id,
            "event": entry.event,
            "from_state": entry.from_state,
            "to_state": entry.to_state,
            "metadata": entry.context,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in entries
    ]
