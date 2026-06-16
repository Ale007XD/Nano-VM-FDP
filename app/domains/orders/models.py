"""SQLAlchemy models for the orders domain.

State storage (Spec §3.2):
    - current_state stored in entity's primary table (orders).
    - NO separate fsm_instances table — this duplicates Trace.
    - Event history = Trace (M1: lightweight custom).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.trace.models import TraceEntry


class Order(Base):
    """Order entity — business state owner (PostgreSQL).

    The current_state column is the single source of truth for order state.
    All mutations go through terminal tools (ADR-001).
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # State — single source of truth (Spec §3.2)
    current_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        index=True,
    )

    # Totals
    total_amount: Mapped[int] = mapped_column(default=0)  # cents
    currency: Mapped[str] = mapped_column(String(3), default="RUB")

    # Payment
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cooking_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    packed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    courier_assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivering_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    trace_entries: Mapped[list[TraceEntry]] = relationship(
        "TraceEntry",
        back_populates="order",
        lazy="selectin",
    )


class OrderItem(Base):
    """Line item within an order."""

    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    order_id: Mapped[str] = mapped_column(
        String(36),
        # No ForeignKey — keep loose coupling for M1
        nullable=False,
        index=True,
    )
    menu_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[int] = mapped_column(nullable=False)  # cents
    total_price: Mapped[int] = mapped_column(nullable=False)  # cents

    # Relationship
    order: Mapped[Order] = relationship("Order", back_populates="items")
