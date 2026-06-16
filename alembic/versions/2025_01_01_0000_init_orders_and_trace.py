"""init orders and trace

Revision ID: 000000000001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "000000000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── orders ───
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(36), nullable=False, index=True),
        sa.Column("customer_phone", sa.String(20), nullable=True),
        sa.Column("customer_address", sa.String(500), nullable=True),
        sa.Column("current_state", sa.String(32), nullable=False, default="DRAFT", index=True),
        sa.Column("total_amount", sa.Integer, nullable=False, default=0),
        sa.Column("currency", sa.String(3), nullable=False, default="RUB"),
        sa.Column("payment_method", sa.String(32), nullable=True),
        sa.Column("payment_external_id", sa.String(128), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column("paid_at", sa.DateTime, nullable=True),
        sa.Column("cooking_started_at", sa.DateTime, nullable=True),
        sa.Column("packed_at", sa.DateTime, nullable=True),
        sa.Column("courier_assigned_at", sa.DateTime, nullable=True),
        sa.Column("delivering_started_at", sa.DateTime, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
    )

    # ─── order_items ───
    op.create_table(
        "order_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), nullable=False, index=True),
        sa.Column("menu_item_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, default=1),
        sa.Column("unit_price", sa.Integer, nullable=False),
        sa.Column("total_price", sa.Integer, nullable=False),
    )

    # ─── trace_entries ───
    op.create_table(
        "trace_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), nullable=False, index=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False, index=True),
        sa.Column("event", sa.String(64), nullable=False, index=True),
        sa.Column("from_state", sa.String(32), nullable=False),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("trace_entries")
    op.drop_table("order_items")
    op.drop_table("orders")
