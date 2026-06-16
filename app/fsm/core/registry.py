"""FSM Registry — lookup and registration of domain FSMs.

Structure (Spec §3.2):
    app/
    ├── fsm/
    │   └── core/
    │       ├── base.py      # BaseFSM[T], TransitionResult, EventType
    │       └── registry.py  # FSM registration, lookup by domain
    └── domains/
        ├── orders/
        │   └── fsm.py       # OrderFSM(BaseFSM[OrderState, OrderEvent])
        ├── kitchen/
        │   └── fsm.py
        ...
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeVar

from app.fsm.core.base import BaseFSM

StateType = TypeVar("StateType", bound=Enum)
EventType = TypeVar("EventType", bound=Enum)


class FSMRegistry:
    """Central registry for all domain FSMs.

    Provides lookup by domain name. Each domain registers its FSM
    at application startup.
    """

    def __init__(self) -> None:
        self._fsms: dict[str, BaseFSM[Any, Any]] = {}

    def register(
        self,
        domain: str,
        fsm: BaseFSM[StateType, EventType],
    ) -> None:
        """Register an FSM for a domain.

        Args:
            domain: Domain name (e.g., 'orders', 'kitchen', 'delivery').
            fsm: The FSM instance to register.

        Raises:
            ValueError: If domain already registered.
        """
        if domain in self._fsms:
            raise ValueError(f"FSM for domain '{domain}' is already registered")
        self._fsms[domain] = fsm

    def get(self, domain: str) -> BaseFSM[Any, Any]:
        """Retrieve an FSM by domain name.

        Args:
            domain: Domain name.

        Returns:
            The registered BaseFSM instance.

        Raises:
            KeyError: If domain not found.
        """
        if domain not in self._fsms:
            raise KeyError(f"No FSM registered for domain '{domain}'")
        return self._fsms[domain]

    def list_domains(self) -> list[str]:
        """Return list of all registered domain names."""
        return list(self._fsms.keys())

    def __contains__(self, domain: str) -> bool:
        return domain in self._fsms


# Global singleton registry
_registry: FSMRegistry | None = None


def get_registry() -> FSMRegistry:
    """Return the global FSM registry, creating if necessary."""
    global _registry
    if _registry is None:
        _registry = FSMRegistry()
    return _registry


def register_fsm(domain: str, fsm: BaseFSM[StateType, EventType]) -> None:
    """Register an FSM in the global registry."""
    registry = get_registry()
    registry.register(domain, fsm)
