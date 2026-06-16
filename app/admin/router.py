"""Admin router — basic admin endpoints for M1.

Provides health checks, system status, and FSM inspection.
Protected by API key authentication.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.domains.orders.fsm import OrderEvent, OrderFSM, OrderState, get_order_fsm
from app.fsm.core.registry import get_registry

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer(auto_error=False)


def verify_admin_key(credentials: HTTPAuthorizationCredentials | None = None) -> bool:
    """Verify admin API key from Authorization header."""
    settings = get_settings()
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required",
        )
    token = credentials.credentials
    # Support "Bearer <key>" or plain key
    if token.startswith("Bearer "):
        token = token[7:]
    if token != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )
    return True


@router.get(
    "/health",
    summary="Health check",
)
async def health_check(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check database connectivity and return system status."""
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e!s}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "database": db_status,
        "version": "0.1.0",
        "milestone": "M1",
    }


@router.get(
    "/fsm/orders",
    summary="Get OrderFSM graph definition",
    dependencies=[Depends(verify_admin_key)],
)
async def get_order_fsm_graph(
    fsm: OrderFSM = Depends(get_order_fsm),
) -> dict[str, Any]:
    """Return the full OrderFSM transition graph.

    Useful for debugging and client-side state machine visualization.
    """
    transitions: dict[str, dict[str, str]] = {}

    for state in OrderState:
        allowed = fsm.get_allowed_events(state)
        transitions[state.value] = {}
        for event in allowed:
            next_state = fsm.get_next_state(state, event)
            if next_state:
                transitions[state.value][event.value] = next_state.value

    return {
        "fsm_name": fsm.name,
        "states": [s.value for s in OrderState],
        "events": [e.value for e in OrderEvent],
        "transitions": transitions,
        "terminal_states": [OrderState.CLOSED.value],
    }


@router.get(
    "/fsm/registry",
    summary="List registered FSMs",
    dependencies=[Depends(verify_admin_key)],
)
async def list_fsms() -> dict[str, Any]:
    """List all registered FSM domains."""
    registry = get_registry()
    return {
        "registered_domains": registry.list_domains(),
    }


@router.get(
    "/config",
    summary="Get runtime configuration (safe)",
    dependencies=[Depends(verify_admin_key)],
)
async def get_config() -> dict[str, Any]:
    """Return sanitized runtime configuration."""
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "app_debug": settings.app_debug,
        "app_host": settings.app_host,
        "app_port": settings.app_port,
        "log_level": settings.log_level,
        "log_format": settings.log_format,
    }
