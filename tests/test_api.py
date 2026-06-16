"""API integration tests.

These tests use the database. Run with:
    pytest tests/test_api.py -v

Requires PostgreSQL running (see docker-compose.yml).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

# Test database
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/food_delivery_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Create an HTTP client with overridden DB dependency."""

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ─── Health ───


@pytest.mark.asyncio
class TestHealth:
    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/admin/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "ok"
        assert data["milestone"] == "M1"


# ─── Orders CRUD ───


@pytest.mark.asyncio
class TestOrderCRUD:
    async def test_create_order(self, client: AsyncClient) -> None:
        payload = {
            "customer_id": str(uuid.uuid4()),
            "customer_phone": "+79001234567",
            "customer_address": "Moscow, Red Square 1",
            "items": [
                {"menu_item_id": "item-1", "name": "Pizza", "quantity": 2, "unit_price": 50000},
                {"menu_item_id": "item-2", "name": "Cola", "quantity": 1, "unit_price": 15000},
            ],
            "currency": "RUB",
        }
        response = await client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["current_state"] == "DRAFT"
        assert data["total_amount"] == 115000  # 2*50000 + 1*15000
        assert len(data["items"]) == 2
        assert data["currency"] == "RUB"

    async def test_get_order(self, client: AsyncClient) -> None:
        # Create
        payload = {
            "customer_id": str(uuid.uuid4()),
            "items": [
                {"menu_item_id": "item-1", "name": "Burger", "quantity": 1, "unit_price": 30000},
            ],
        }
        create_resp = await client.post("/orders", json=payload)
        order_id = create_resp.json()["id"]

        # Get
        get_resp = await client.get(f"/orders/{order_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == order_id
        assert data["current_state"] == "DRAFT"

    async def test_get_order_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/orders/non-existent-id")
        assert response.status_code == 404

    async def test_list_orders(self, client: AsyncClient) -> None:
        # Create two orders
        for i in range(2):
            payload = {
                "customer_id": str(uuid.uuid4()),
                "items": [
                    {
                        "menu_item_id": f"item-{i}",
                        "name": f"Item {i}",
                        "quantity": 1,
                        "unit_price": 100,
                    },
                ],
            }
            await client.post("/orders", json=payload)

        response = await client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_orders_filter_by_state(self, client: AsyncClient) -> None:
        # Create order (starts as DRAFT)
        payload = {
            "customer_id": str(uuid.uuid4()),
            "items": [
                {"menu_item_id": "item-1", "name": "Test", "quantity": 1, "unit_price": 100},
            ],
        }
        await client.post("/orders", json=payload)

        response = await client.get("/orders?state=DRAFT")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        response = await client.get("/orders?state=PAID")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


# ─── Transitions ───


@pytest.mark.asyncio
class TestOrderTransitions:
    async def _create_order(self, client: AsyncClient) -> str:
        """Helper: create and return order ID."""
        payload = {
            "customer_id": str(uuid.uuid4()),
            "items": [
                {"menu_item_id": "item-1", "name": "Pizza", "quantity": 1, "unit_price": 50000},
            ],
        }
        resp = await client.post("/orders", json=payload)
        result: str = resp.json()["id"]
        return result

    async def test_confirm_order(self, client: AsyncClient) -> None:
        order_id = await self._create_order(client)

        response = await client.post(
            f"/orders/{order_id}/transition",
            json={"event": "CONFIRM"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_state"] == "CONFIRMED"
        assert data["previous_state"] == "DRAFT"

    async def test_full_lifecycle(self, client: AsyncClient) -> None:
        order_id = await self._create_order(client)

        transitions = [
            ("CONFIRM", "CONFIRMED"),
            ("INITIATE_PAYMENT", "PAYMENT_PENDING"),
            ("PAYMENT_CONFIRMED", "PAID"),
            ("START_COOKING", "COOKING"),
            ("FINISH_COOKING", "PACKING"),
            ("REQUEST_COURIER", "COURIER_ASSIGNED"),
            ("COURIER_PICKED_UP", "DELIVERING"),
            ("DELIVERY_COMPLETE", "DELIVERED"),
            ("CLOSE_ORDER", "CLOSED"),
        ]

        for event, expected_state in transitions:
            response = await client.post(
                f"/orders/{order_id}/transition",
                json={"event": event},
            )
            assert response.status_code == 200, f"Failed at {event}: {response.text}"
            data = response.json()
            assert data["success"] is True, f"Transition {event} failed: {data.get('reason')}"
            assert data["new_state"] == expected_state, (
                f"Expected {expected_state}, got {data['new_state']}"
            )

    async def test_invalid_transition(self, client: AsyncClient) -> None:
        order_id = await self._create_order(client)

        # Try to START_COOKING from DRAFT (not allowed)
        response = await client.post(
            f"/orders/{order_id}/transition",
            json={"event": "START_COOKING"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["new_state"] is None
        assert "START_COOKING" in data["reason"]

    async def test_cancel_order(self, client: AsyncClient) -> None:
        order_id = await self._create_order(client)

        response = await client.post(
            f"/orders/{order_id}/transition",
            json={"event": "CANCEL"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_state"] == "CLOSED"

    async def test_get_state_info(self, client: AsyncClient) -> None:
        order_id = await self._create_order(client)

        response = await client.get(f"/orders/{order_id}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["current_state"] == "DRAFT"
        assert "CONFIRM" in data["allowed_events"]
        assert "CANCEL" in data["allowed_events"]


# ─── Trace ───


@pytest.mark.asyncio
class TestTrace:
    async def test_order_has_trace_after_creation(self, client: AsyncClient) -> None:
        payload = {
            "customer_id": str(uuid.uuid4()),
            "items": [
                {"menu_item_id": "item-1", "name": "Pizza", "quantity": 1, "unit_price": 50000},
            ],
        }
        resp = await client.post("/orders", json=payload)
        order_id = resp.json()["id"]

        response = await client.get(f"/orders/{order_id}/trace")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["event"] == "ORDER_CREATED"
        assert data[0]["to_state"] == "DRAFT"

    async def test_trace_after_transition(self, client: AsyncClient) -> None:
        payload = {
            "customer_id": str(uuid.uuid4()),
            "items": [
                {"menu_item_id": "item-1", "name": "Pizza", "quantity": 1, "unit_price": 50000},
            ],
        }
        resp = await client.post("/orders", json=payload)
        order_id = resp.json()["id"]

        # Do a transition
        await client.post(
            f"/orders/{order_id}/transition",
            json={"event": "CONFIRM"},
        )

        response = await client.get(f"/orders/{order_id}/trace")
        data = response.json()
        events = [e["event"] for e in data]
        assert "CONFIRM" in events
        assert "ORDER_CREATED" in events


# ─── Admin ───


@pytest.mark.asyncio
class TestAdmin:
    async def test_fsm_graph(self, client: AsyncClient) -> None:
        response = await client.get(
            "/admin/fsm/orders",
            headers={"Authorization": "Bearer dev-admin-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["fsm_name"] == "OrderFSM"
        assert "DRAFT" in data["states"]
        assert "CLOSED" in data["states"]
        assert "CLOSED" in data["terminal_states"]
        assert "CONFIRM" in data["transitions"]["DRAFT"]

    async def test_fsm_graph_no_auth(self, client: AsyncClient) -> None:
        response = await client.get("/admin/fsm/orders")
        assert response.status_code == 401

    async def test_config_endpoint(self, client: AsyncClient) -> None:
        response = await client.get(
            "/admin/config",
            headers={"Authorization": "Bearer dev-admin-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "app_env" in data
        assert "app_port" in data
