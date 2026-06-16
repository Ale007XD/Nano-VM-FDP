"""Trace models — event history storage.

Architecture (Spec §3.2):
    - Event history = Trace (M1: lightweight custom; M3: nano-vm Trace).
    - Stored in PostgreSQL alongside business entities.
    - Each entry records a single state transition event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.domains.orders.models import Order


class TraceEntry(Base):
    """Single trace entry recording a state transition.

    This is the M1 lightweight custom trace. In M3 this will be
    superseded by nano-vm Trace, but the schema will remain compatible.
    """

    __tablename__ = "trace_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Link to order
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Entity reference
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Transition details
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)

    # Execution metadata
    context: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)

    # Relationship
    order: Mapped[Order] = relationship("Order", back_populates="trace_entries")
