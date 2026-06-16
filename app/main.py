"""FastAPI application entry point.

M1 Foundation deliverables (Spec §5):
    - PostgreSQL schema + Alembic
    - FastAPI skeleton
    - Order FSM (custom, nano-vm-compatible at method signature level)
    - Basic Trace (custom)
    - Basic Admin

Anti-patterns enforced (Spec §7):
    - Direct state mutation: blocked by architecture
    - fsm_instances table: NOT used
    - GovernanceEnvelope stub: NOT created
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.domains.orders.fsm import get_order_fsm
from app.domains.orders.router import router as orders_router
from app.fsm.core.registry import register_fsm


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    """Application lifespan — register FSMs on startup."""
    # Startup: register all domain FSMs
    register_fsm("orders", get_order_fsm())

    yield

    # Shutdown: cleanup if needed


app = FastAPI(
    title="Food Delivery Platform",
    description="nano-vm Ecosystem Edition — M1 Foundation",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(orders_router)
app.include_router(admin_router)


@app.get("/", tags=["root"])
async def root() -> dict[str, Any]:
    """Root endpoint."""
    return {
        "name": "Food Delivery Platform",
        "version": "0.1.0",
        "milestone": "M1",
        "status": "Foundation",
    }
