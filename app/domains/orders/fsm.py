"""OrderFSM — event-driven finite state machine for orders.

Graph (Spec §3):
    DRAFT → CONFIRMED → PAYMENT_PENDING → PAID → COOKING → PACKING
    → COURIER_ASSIGNED → DELIVERING → DELIVERED → CLOSED

Anti-pattern guards (Spec §7):
    - Direct state mutation: FORBIDDEN.
    - FSM with business rules: FORBIDDEN — FSM is graph-only.
"""

from __future__ import annotations

from enum import StrEnum

from app.fsm.core.base import BaseFSM


class OrderState(StrEnum):
    """Order lifecycle states.

    Stored in orders.current_state (PostgreSQL) — the entity's primary table.
    NO separate fsm_instances table (Spec §1.3, §7).
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    COOKING = "COOKING"
    PACKING = "PACKING"
    COURIER_ASSIGNED = "COURIER_ASSIGNED"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CLOSED = "CLOSED"


class OrderEvent(StrEnum):
    """Events that drive order state transitions.

    Core invariant (Spec §1.2):
        transition(entity_id, event=...) — accepts EVENT, never new_state.
    """

    # DRAFT → CONFIRMED
    CONFIRM = "CONFIRM"

    # CONFIRMED → PAYMENT_PENDING
    INITIATE_PAYMENT = "INITIATE_PAYMENT"

    # PAYMENT_PENDING → PAID
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"

    # PAYMENT_PENDING → (cancel flow)
    PAYMENT_FAILED = "PAYMENT_FAILED"

    # PAID → COOKING
    START_COOKING = "START_COOKING"

    # COOKING → PACKING
    FINISH_COOKING = "FINISH_COOKING"

    # PACKING → COURIER_ASSIGNED
    REQUEST_COURIER = "REQUEST_COURIER"

    # COURIER_ASSIGNED → DELIVERING
    COURIER_PICKED_UP = "COURIER_PICKED_UP"

    # DELIVERING → DELIVERED
    DELIVERY_COMPLETE = "DELIVERY_COMPLETE"

    # DELIVERED → CLOSED
    CLOSE_ORDER = "CLOSE_ORDER"

    # Cancel from non-terminal states
    CANCEL = "CANCEL"


class OrderFSM(BaseFSM[OrderState, OrderEvent]):
    """Order finite state machine.

    Invariants:
        - Graph-only: validates event allowed from current state.
        - No business logic (e.g., "order is not paid" check lives in
          PolicyProvider, not in OrderFSM graph — Spec §ADR-004).
        - State stored in orders table (PostgreSQL), not in FSM.
    """

    def __init__(self) -> None:
        transitions: dict[OrderState, dict[OrderEvent, OrderState]] = {
            OrderState.DRAFT: {
                OrderEvent.CONFIRM: OrderState.CONFIRMED,
                OrderEvent.CANCEL: OrderState.CLOSED,
            },
            OrderState.CONFIRMED: {
                OrderEvent.INITIATE_PAYMENT: OrderState.PAYMENT_PENDING,
                OrderEvent.CANCEL: OrderState.CLOSED,
            },
            OrderState.PAYMENT_PENDING: {
                OrderEvent.PAYMENT_CONFIRMED: OrderState.PAID,
                OrderEvent.PAYMENT_FAILED: OrderState.CONFIRMED,
                OrderEvent.CANCEL: OrderState.CLOSED,
            },
            OrderState.PAID: {
                OrderEvent.START_COOKING: OrderState.COOKING,
            },
            OrderState.COOKING: {
                OrderEvent.FINISH_COOKING: OrderState.PACKING,
            },
            OrderState.PACKING: {
                OrderEvent.REQUEST_COURIER: OrderState.COURIER_ASSIGNED,
            },
            OrderState.COURIER_ASSIGNED: {
                OrderEvent.COURIER_PICKED_UP: OrderState.DELIVERING,
            },
            OrderState.DELIVERING: {
                OrderEvent.DELIVERY_COMPLETE: OrderState.DELIVERED,
            },
            OrderState.DELIVERED: {
                OrderEvent.CLOSE_ORDER: OrderState.CLOSED,
            },
            OrderState.CLOSED: {},
        }

        super().__init__(transitions, name="OrderFSM")


# Singleton instance
_order_fsm = OrderFSM()


def get_order_fsm() -> OrderFSM:
    """Return the singleton OrderFSM instance."""
    return _order_fsm
