"""FSM unit tests — no database required.

Tests enforce architecture invariants from Spec §1.2, §3.1.
"""

from __future__ import annotations

import pytest

from app.domains.orders.fsm import OrderEvent, OrderFSM, OrderState
from app.fsm.core.base import TransitionResult

# ─── Fixtures ───


@pytest.fixture
def fsm() -> OrderFSM:
    """Return fresh OrderFSM instance."""
    return OrderFSM()


# ─── BaseFSM Contract ───


class TestBaseFSMContract:
    """Verify BaseFSM.transition() contract (Spec §3.1)."""

    def test_transition_accepts_event_not_state(self, fsm: OrderFSM) -> None:
        """Core invariant: transition(entity_id, event) — never new_state."""
        result = fsm.transition("test-1", OrderEvent.CONFIRM, OrderState.DRAFT)

        assert isinstance(result, TransitionResult)
        assert result.success is True
        assert result.new_state == OrderState.CONFIRMED
        assert result.rejected_event is None
        assert result.reason is None

    def test_transition_returns_tuple_on_rejection(self, fsm: OrderFSM) -> None:
        """Rejected transitions return TransitionResult with rejected_event set."""
        result = fsm.transition("test-2", OrderEvent.CONFIRM, OrderState.PAID)

        assert isinstance(result, TransitionResult)
        assert result.success is False
        assert result.new_state is None
        assert result.rejected_event == OrderEvent.CONFIRM
        assert result.reason is not None
        assert "CONFIRM" in result.reason
        assert "PAID" in result.reason

    def test_transition_result_is_frozen(self) -> None:
        """TransitionResult is immutable (frozen dataclass)."""
        result = TransitionResult(success=True)

        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ─── OrderFSM Graph ───


class TestOrderFSMGraph:
    """Verify OrderFSM transition graph (Spec §3)."""

    def test_full_happy_path(self, fsm: OrderFSM) -> None:
        """Test complete order lifecycle from DRAFT to CLOSED."""
        path = [
            (OrderState.DRAFT, OrderEvent.CONFIRM, OrderState.CONFIRMED),
            (OrderState.CONFIRMED, OrderEvent.INITIATE_PAYMENT, OrderState.PAYMENT_PENDING),
            (OrderState.PAYMENT_PENDING, OrderEvent.PAYMENT_CONFIRMED, OrderState.PAID),
            (OrderState.PAID, OrderEvent.START_COOKING, OrderState.COOKING),
            (OrderState.COOKING, OrderEvent.FINISH_COOKING, OrderState.PACKING),
            (OrderState.PACKING, OrderEvent.REQUEST_COURIER, OrderState.COURIER_ASSIGNED),
            (OrderState.COURIER_ASSIGNED, OrderEvent.COURIER_PICKED_UP, OrderState.DELIVERING),
            (OrderState.DELIVERING, OrderEvent.DELIVERY_COMPLETE, OrderState.DELIVERED),
            (OrderState.DELIVERED, OrderEvent.CLOSE_ORDER, OrderState.CLOSED),
        ]

        for current, event, expected_next in path:
            result = fsm.transition("order-1", event, current)
            assert result.success, f"Failed at {current.value} -> {event.value}: {result.reason}"
            got = result.new_state.value if result.new_state else None
            assert result.new_state == expected_next, f"Expected {expected_next.value}, got {got}"

    def test_payment_failure_retry(self, fsm: OrderFSM) -> None:
        """Test: PAYMENT_FAILED returns to CONFIRMED, can retry."""
        # First: confirm and initiate payment
        r1 = fsm.transition("o-1", OrderEvent.CONFIRM, OrderState.DRAFT)
        assert r1.new_state == OrderState.CONFIRMED

        r2 = fsm.transition("o-1", OrderEvent.INITIATE_PAYMENT, OrderState.CONFIRMED)
        assert r2.new_state == OrderState.PAYMENT_PENDING

        # Payment fails → back to CONFIRMED
        r3 = fsm.transition("o-1", OrderEvent.PAYMENT_FAILED, OrderState.PAYMENT_PENDING)
        assert r3.new_state == OrderState.CONFIRMED

        # Retry payment
        r4 = fsm.transition("o-1", OrderEvent.INITIATE_PAYMENT, OrderState.CONFIRMED)
        assert r4.new_state == OrderState.PAYMENT_PENDING

        # Now succeeds
        r5 = fsm.transition("o-1", OrderEvent.PAYMENT_CONFIRMED, OrderState.PAYMENT_PENDING)
        assert r5.new_state == OrderState.PAID

    def test_cancel_from_draft(self, fsm: OrderFSM) -> None:
        """Test: CANCEL from DRAFT → CLOSED."""
        result = fsm.transition("o-2", OrderEvent.CANCEL, OrderState.DRAFT)
        assert result.success
        assert result.new_state == OrderState.CLOSED

    def test_cancel_from_confirmed(self, fsm: OrderFSM) -> None:
        """Test: CANCEL from CONFIRMED → CLOSED."""
        result = fsm.transition("o-3", OrderEvent.CANCEL, OrderState.CONFIRMED)
        assert result.success
        assert result.new_state == OrderState.CLOSED

    def test_cancel_from_payment_pending(self, fsm: OrderFSM) -> None:
        """Test: CANCEL from PAYMENT_PENDING → CLOSED."""
        result = fsm.transition("o-4", OrderEvent.CANCEL, OrderState.PAYMENT_PENDING)
        assert result.success
        assert result.new_state == OrderState.CLOSED

    def test_no_cancel_after_paid(self, fsm: OrderFSM) -> None:
        """Test: CANCEL is not allowed from PAID state."""
        result = fsm.transition("o-5", OrderEvent.CANCEL, OrderState.PAID)
        assert not result.success
        assert result.rejected_event == OrderEvent.CANCEL

    def test_closed_is_terminal(self, fsm: OrderFSM) -> None:
        """Test: CLOSED has no outgoing transitions."""
        allowed = fsm.get_allowed_events(OrderState.CLOSED)
        assert len(allowed) == 0


# ─── Query Methods ───


class TestOrderFSMQueries:
    """Test read-only query methods."""

    def test_get_allowed_events_from_draft(self, fsm: OrderFSM) -> None:
        """DRAFT allows CONFIRM and CANCEL."""
        allowed = fsm.get_allowed_events(OrderState.DRAFT)
        assert OrderEvent.CONFIRM in allowed
        assert OrderEvent.CANCEL in allowed

    def test_get_allowed_events_from_paid(self, fsm: OrderFSM) -> None:
        """PAID allows only START_COOKING."""
        allowed = fsm.get_allowed_events(OrderState.PAID)
        assert allowed == [OrderEvent.START_COOKING]

    def test_get_next_state(self, fsm: OrderFSM) -> None:
        """get_next_state returns correct next state without side effects."""
        next_state = fsm.get_next_state(OrderState.DRAFT, OrderEvent.CONFIRM)
        assert next_state == OrderState.CONFIRMED

    def test_get_next_state_invalid(self, fsm: OrderFSM) -> None:
        """get_next_state returns None for invalid transitions."""
        next_state = fsm.get_next_state(OrderState.CLOSED, OrderEvent.CONFIRM)
        assert next_state is None

    def test_all_states_defined(self, fsm: OrderFSM) -> None:
        """All 10 order states are in the graph."""
        states = fsm.get_all_states()
        assert len(states) == 10
        for state in OrderState:
            assert state in states


# ─── FSM is Graph-Only ───


class TestFSMGraphOnly:
    """Verify FSM contains no business logic (Spec §ADR-004)."""

    def test_fsm_has_no_payment_validation(self, fsm: OrderFSM) -> None:
        """FSM does not check if order is paid — that's PolicyProvider."""
        # FSM allows the graph transition regardless of business state
        result = fsm.transition("any-id", OrderEvent.START_COOKING, OrderState.PAID)
        assert result.success  # Graph allows it
        # Business validation happens in PolicyProvider (M3: GovernedToolExecutor)

    def test_fsm_has_no_inventory_checks(self, fsm: OrderFSM) -> None:
        """FSM does not check inventory — that's a business rule."""
        result = fsm.transition("any-id", OrderEvent.FINISH_COOKING, OrderState.COOKING)
        assert result.success  # Graph allows it
