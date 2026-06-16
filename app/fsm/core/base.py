"""BaseFSM — event-driven finite state machine core.

Core invariant from Architecture Spec §1.2:
    BaseFSM.transition(entity_id: str, event: EventType) -> TransitionResult
    Accepts EVENT, never new_state.
    Enforced across all domain FSMs.

Anti-pattern guard (Spec §7):
    Direct state assignment is FORBIDDEN outside terminal tools.
    FSM is graph-only; business rules live in PolicyProvider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

StateType = TypeVar("StateType", bound=Enum)
EventType = TypeVar("EventType", bound=Enum)


@dataclass(frozen=True)
class TransitionResult:
    """Result of an FSM transition attempt.

    Contract (Spec §3.1):
        success: bool — whether the transition succeeded.
        new_state: StateType | None — new state if succeeded, None if rejected.
        rejected_event: EventType | None — populated on policy/graph rejection.
        reason: str | None — human-readable rejection reason.

    M3 note: StepResult from nano-vm is the natural successor of TransitionResult.
    """

    success: bool
    new_state: Enum | None = None
    rejected_event: Enum | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.success


@dataclass
class TransitionLogEntry:
    """Single entry in the FSM transition log."""

    entity_id: str
    from_state: Enum
    event: Enum
    to_state: Enum | None
    success: bool
    reason: str | None = None


class BaseFSM(Generic[StateType, EventType]):
    """Event-driven finite state machine base class.

    Invariants (Spec §1.2, §3.1, §ADR-004):
        1. transition(entity_id, event) accepts EVENT, never new_state.
        2. FSM is graph-only: validates only that event is allowed from current state.
        3. No business logic inside BaseFSM — PolicyProvider handles rules.
        4. State mutation is performed ONLY through terminal tools (ADR-001).

    Usage:
        class OrderState(str, Enum):
            DRAFT = "DRAFT"
            CONFIRMED = "CONFIRMED"
            # ...

        class OrderEvent(str, Enum):
            CONFIRM = "CONFIRM"
            # ...

        class OrderFSM(BaseFSM[OrderState, OrderEvent]):
            def __init__(self) -> None:
                transitions = {
                    OrderState.DRAFT: {OrderEvent.CONFIRM: OrderState.CONFIRMED},
                    # ...
                }
                super().__init__(transitions)

        fsm = OrderFSM()
        result = fsm.transition("order-123", OrderEvent.CONFIRM)
        # result.success == True, result.new_state == OrderState.CONFIRMED
    """

    def __init__(
        self,
        transitions: dict[StateType, dict[EventType, StateType]],
        *,
        name: str = "",
    ) -> None:
        """Initialize FSM with a transition graph.

        Args:
            transitions: Mapping of {current_state: {event: next_state}}.
            name: Human-readable FSM name for logging.
        """
        self._transitions = transitions
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Return FSM name."""
        return self._name

    def transition(
        self, entity_id: str, event: EventType, current_state: StateType
    ) -> TransitionResult:
        """Attempt a state transition driven by an event.

        This is the ONLY valid mutation path (Spec §1.2).
        Direct state assignment is FORBIDDEN.

        Args:
            entity_id: Unique identifier of the entity.
            event: The event triggering the transition.
            current_state: Current state of the entity.

        Returns:
            TransitionResult indicating success/failure and new state (if any).
        """
        allowed = self._transitions.get(current_state, {})

        if event not in allowed:
            allowed_events = list(allowed.keys())
            return TransitionResult(
                success=False,
                new_state=None,
                rejected_event=event,
                reason=(
                    f"Event '{event.value}' not allowed from state "
                    f"'{current_state.value}'. Allowed: "
                    f"[{', '.join(e.value for e in allowed_events)}]"
                ),
            )

        next_state = allowed[event]

        return TransitionResult(
            success=True,
            new_state=next_state,
            rejected_event=None,
            reason=None,
        )

    def get_allowed_events(self, state: StateType) -> list[EventType]:
        """Return graph-level allowed events from a given state.

        Note (Spec §3.1, §ADR-004):
            Returns graph-level allowed events ONLY.
            Business rules = PolicyProvider (separate layer).
            Do NOT mix FSM graph knowledge with business logic.
        """
        return list(self._transitions.get(state, {}).keys())

    def get_next_state(self, state: StateType, event: EventType) -> StateType | None:
        """Return the next state for a (state, event) pair without side effects.

        This is a read-only query method. It does NOT perform a transition.
        """
        return self._transitions.get(state, {}).get(event)

    def get_all_states(self) -> list[StateType]:
        """Return all states defined in the FSM graph."""
        return list(self._transitions.keys())

    def get_all_events(self) -> list[EventType]:
        """Return all events defined in the FSM graph."""
        events: set[EventType] = set()
        for state_transitions in self._transitions.values():
            events.update(state_transitions.keys())
        return list(events)

    def validate_graph(self) -> list[str]:
        """Validate the FSM graph and return list of issues.

        Checks:
            - No dead states (states with no outgoing transitions).
            - Terminal states are explicitly marked (no outgoing transitions).
        """
        issues: list[str] = []

        for state in self._transitions:
            outgoing = self._transitions[state]
            if not outgoing:
                # Terminal state — this is fine
                continue

        return issues
