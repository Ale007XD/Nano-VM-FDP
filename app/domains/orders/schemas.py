"""Pydantic schemas for the orders domain."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.orders.fsm import OrderEvent, OrderState

# ─── Shared ───


class OrderItemCreate(BaseModel):
    """Schema for creating an order item."""

    menu_item_id: str
    name: str
    quantity: int = Field(default=1, ge=1)
    unit_price: int = Field(..., ge=0)  # cents


class OrderItemRead(BaseModel):
    """Schema for reading an order item."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    menu_item_id: str
    name: str
    quantity: int
    unit_price: int
    total_price: int


# ─── Create ───


class OrderCreate(BaseModel):
    """Schema for creating a new order."""

    customer_id: str
    customer_phone: str | None = None
    customer_address: str | None = None
    items: list[OrderItemCreate] = Field(default_factory=list, min_length=1)
    currency: Literal["RUB", "USD", "EUR"] = "RUB"


# ─── Read ───


class OrderRead(BaseModel):
    """Schema for reading an order."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    customer_phone: str | None
    customer_address: str | None
    current_state: str
    total_amount: int
    currency: str
    payment_method: str | None
    payment_external_id: str | None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    paid_at: datetime | None
    cooking_started_at: datetime | None
    packed_at: datetime | None
    courier_assigned_at: datetime | None
    delivering_started_at: datetime | None
    delivered_at: datetime | None
    closed_at: datetime | None
    items: list[OrderItemRead]


# ─── Transition ───


class OrderTransitionRequest(BaseModel):
    """Request schema for order state transition.

    Core invariant (Spec §1.2):
        Accepts EVENT, never new_state.
    """

    event: OrderEvent
    metadata: dict[str, object] = Field(default_factory=dict)


class OrderTransitionResponse(BaseModel):
    """Response schema for order state transition."""

    success: bool
    order_id: str
    previous_state: str
    new_state: str | None
    event: str
    reason: str | None = None
    trace_id: str | None = None


# ─── State Query ───


class OrderStateInfo(BaseModel):
    """Schema for order state information."""

    order_id: str
    current_state: OrderState
    allowed_events: list[str]


# ─── List ───


class OrderListParams(BaseModel):
    """Query parameters for listing orders."""

    state: OrderState | None = None
    customer_id: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
