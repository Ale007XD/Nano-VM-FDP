"""Trace service — read operations for trace entries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.trace.models import TraceEntry


class TraceService:
    """Service for reading and querying trace entries."""

    async def get_entries_for_order(
        self,
        session: AsyncSession,
        order_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TraceEntry]:
        """Get trace entries for a specific order.

        Args:
            session: Database session.
            order_id: Order identifier.
            limit: Maximum entries to return.
            offset: Pagination offset.

        Returns:
            List of trace entries ordered by creation time (newest first).
        """
        result = await session.execute(
            select(TraceEntry)
            .where(TraceEntry.order_id == order_id)
            .order_by(TraceEntry.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return list(result.scalars().all())

    async def get_entry(self, session: AsyncSession, entry_id: str) -> TraceEntry | None:
        """Get a single trace entry by ID."""
        result = await session.execute(
            select(TraceEntry).where(TraceEntry.id == entry_id),
        )
        return result.scalar_one_or_none()

    async def get_recent_entries(
        self,
        session: AsyncSession,
        *,
        limit: int = 50,
    ) -> list[TraceEntry]:
        """Get most recent trace entries across all entities."""
        result = await session.execute(
            select(TraceEntry).order_by(TraceEntry.created_at.desc()).limit(limit),
        )
        return list(result.scalars().all())
