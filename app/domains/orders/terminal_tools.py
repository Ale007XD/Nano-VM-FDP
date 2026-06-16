"""Terminal tools — the ONLY valid path for writing order state to PostgreSQL.

Architecture (ADR-001):
    - Every Program must have exactly one terminal tool.
    - Terminal tool atomically writes new entity state to PostgreSQL.
    - ExecutionVM does not complete successfully if terminal tool failed.
    - FSM enforces the execution path; the terminal tool owns the write.
    - Terminal tool MUST execute all PostgreSQL operations inside a single
      transaction. External calls are FORBIDDEN inside that transaction block.

Anti-pattern guard (Spec §7):
    Direct state mutation (order.status = X) is FORBIDDEN anywhere
    outside terminal tools.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.orders.fsm import OrderState
from app.domains.orders.models import Order
from app.trace.models import TraceEntry
from app.trace.service import TraceService


class OrderTerminalTool:
    """Terminal tool for atomic order state writes.

    This is the ONLY component allowed to mutate order.current_state.
    All business transitions must route through this tool.
    """

    def __init__(self, trace_service: TraceService | None = None) -> None:
        self._trace = trace_service or TraceService()

    async def write_state(
        self,
        session: AsyncSession,
        *,
        order_id: str,
        new_state: OrderState,
        event: str,
        previous_state: str,
        metadata: dict[str, object] | None = None,
    ) -> Order:
        """Atomically write new order state to PostgreSQL.

        Args:
            session: Database session (transaction managed by caller).
            order_id: Order identifier.
            new_state: Target state (from FSM transition result).
            event: Event that triggered the transition.
            previous_state: State before transition.
            metadata: Optional transition metadata.

        Returns:
            Updated Order entity.

        Raises:
            ValueError: If order not found.
        """
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order '{order_id}' not found")

        # ─── Atomic state write ───
        order.current_state = new_state.value
        order.updated_at = datetime.utcnow()

        # ─── Timestamp tracking ───
        now = datetime.utcnow()
        match new_state:
            case OrderState.CONFIRMED:
                order.confirmed_at = now
            case OrderState.PAID:
                order.paid_at = now
            case OrderState.COOKING:
                order.cooking_started_at = now
            case OrderState.PACKING:
                order.packed_at = now
            case OrderState.COURIER_ASSIGNED:
                order.courier_assigned_at = now
            case OrderState.DELIVERING:
                order.delivering_started_at = now
            case OrderState.DELIVERED:
                order.delivered_at = now
            case OrderState.CLOSED:
                order.closed_at = now
            case _:
                pass

        # ─── Create trace entry ───
        trace_entry = TraceEntry(
            order_id=order_id,
            entity_type="order",
            entity_id=order_id,
            event=event,
            from_state=previous_state,
            to_state=new_state.value,
            context=metadata or {},
        )
        session.add(trace_entry)

        await session.flush()
        return order

    async def create_order(
        self,
        session: AsyncSession,
        *,
        customer_id: str,
        customer_phone: str | None,
        customer_address: str | None,
        items_data: list[dict[str, Any]],
        currency: str = "RUB",
    ) -> Order:
        """Create a new order in DRAFT state.

        Args:
            session: Database session.
            customer_id: Customer identifier.
            customer_phone: Optional phone number.
            customer_address: Optional delivery address.
            items_data: List of item dicts with menu_item_id, name, quantity, unit_price.
            currency: Currency code.

        Returns:
            Created Order entity.
        """
        from app.domains.orders.models import OrderItem

        total_amount = sum(item["unit_price"] * item.get("quantity", 1) for item in items_data)

        order = Order(
            customer_id=customer_id,
            customer_phone=customer_phone,
            customer_address=customer_address,
            current_state=OrderState.DRAFT.value,
            total_amount=total_amount,
            currency=currency,
        )
        session.add(order)
        await session.flush()

        for item in items_data:
            qty = item.get("quantity", 1)
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=item["menu_item_id"],
                name=item["name"],
                quantity=qty,
                unit_price=item["unit_price"],
                total_price=item["unit_price"] * qty,
            )
            session.add(order_item)

        # Trace entry for creation
        trace_entry = TraceEntry(
            order_id=order.id,
            entity_type="order",
            entity_id=order.id,
            event="ORDER_CREATED",
            from_state="",
            to_state=OrderState.DRAFT.value,
            metadata={"customer_id": customer_id, "item_count": len(items_data)},
        )
        session.add(trace_entry)
        await session.flush()

        return order


# Singleton
def get_terminal_tool() -> OrderTerminalTool:
    """Return terminal tool instance."""
    return OrderTerminalTool()
