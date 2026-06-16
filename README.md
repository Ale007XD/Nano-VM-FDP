# Food Delivery Platform

**nano-vm Ecosystem Edition — M1 Foundation**

Событийно-ориентированная платформа доставки еды на FastAPI + PostgreSQL с FSM (Finite State Machine) архитектурой, совместимой с nano-vm.

## Архитектура

### Core Invariant
```
nano-vm = transition executor
NOT entity lifecycle container
Business state owner = PostgreSQL
Execution state owner = nano-vm Trace + StateContext
```

### Ключевые принципы
- **Event-driven transitions**: `fsm.transition(order_id, event="PAYMENT_CONFIRMED")` — только события, никогда целевое состояние
- **Terminal tool**: единственная точка записи состояния в PostgreSQL
- **FSM is graph-only**: нет бизнес-логики в FSM, только граф переходов
- **Trace**: полная история событий (M1: lightweight custom)

### Order FSM Graph
```
DRAFT → CONFIRMED → PAYMENT_PENDING → PAID → COOKING → PACKING
  ↓                                              ↓
CLOSED ← ... ← DELIVERED ← DELIVERING ← COURIER_ASSIGNED
```

## Стек

| Компонент | Технология |
|-----------|-----------|
| API Framework | FastAPI |
| Database | PostgreSQL 17 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Type Check | mypy |

## Быстрый старт

### Docker (рекомендуется)

```bash
# Клонировать репозиторий
git clone <repo-url>
cd food-delivery-platform

# Запуск PostgreSQL + App
docker-compose up -d

# Применить миграции
docker-compose exec app alembic upgrade head

# API доступен на http://localhost:8000
# Документация: http://localhost:8000/docs
```

### Локальная разработка

```bash
# Python 3.11+
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# Установка
pip install -e ".[dev]"

# PostgreSQL (должен быть запущен)
createdb food_delivery

# Настройка окружения
cp .env.example .env
# Отредактировать DATABASE_URL при необходимости

# Миграции
alembic upgrade head

# Запуск
uvicorn app.main:app --reload
```

## API Endpoints

### Orders
| Method | Path | Описание |
|--------|------|----------|
| POST | `/orders` | Создать заказ (DRAFT) |
| GET | `/orders` | Список заказов |
| GET | `/orders/{id}` | Получить заказ |
| POST | `/orders/{id}/transition` | Выполнить переход по событию |
| GET | `/orders/{id}/state` | Состояние + доступные события |
| GET | `/orders/{id}/trace` | История событий |

### Admin
| Method | Path | Описание |
|--------|------|----------|
| GET | `/admin/health` | Health check |
| GET | `/admin/fsm/orders` | Граф OrderFSM |
| GET | `/admin/fsm/registry` | Список FSM |
| GET | `/admin/config` | Конфигурация |

### Примеры

```bash
# Создать заказ
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust-123",
    "customer_phone": "+79001234567",
    "items": [
      {"menu_item_id": "pizza-1", "name": "Pepperoni", "quantity": 1, "unit_price": 50000}
    ]
  }'

# Подтвердить заказ
curl -X POST http://localhost:8000/orders/{id}/transition \
  -H "Content-Type: application/json" \
  -d '{"event": "CONFIRM"}'

# Полная цепочка
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "INITIATE_PAYMENT"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "PAYMENT_CONFIRMED"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "START_COOKING"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "FINISH_COOKING"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "REQUEST_COURIER"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "COURIER_PICKED_UP"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "DELIVERY_COMPLETE"}'
curl -X POST http://localhost:8000/orders/{id}/transition -d '{"event": "CLOSE_ORDER"}'
```

## Структура проекта

```
food-delivery-platform/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # SQLAlchemy engine + session
│   ├── fsm/
│   │   └── core/
│   │       ├── base.py         # BaseFSM, TransitionResult
│   │       └── registry.py     # FSMRegistry
│   ├── domains/
│   │   └── orders/
│   │       ├── fsm.py          # OrderFSM (10 states)
│   │       ├── models.py       # SQLAlchemy models
│   │       ├── schemas.py      # Pydantic schemas
│   │       ├── terminal_tools.py  # Atomic state writes
│   │       └── router.py       # FastAPI endpoints
│   ├── trace/
│   │   ├── models.py           # TraceEntry model
│   │   └── service.py          # Trace read operations
│   └── admin/
│       └── router.py           # Health, FSM graph, config
├── alembic/                    # Database migrations
├── tests/
│   ├── test_fsm.py             # FSM unit tests
│   └── test_api.py             # API integration tests
├── .github/workflows/ci.yml    # GitHub Actions CI
├── pyproject.toml              # Project config + tools
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## CI/CD

GitHub Actions запускает:
1. **Ruff lint** — проверка кода
2. **Ruff format check** — проверка форматирования
3. **MyPy** — статический анализ типов
4. **pytest** — unit + integration тесты с PostgreSQL

## Разработка

```bash
# Линтинг
ruff check app tests
ruff format app tests

# Типы
mypy app tests

# Тесты (нужен PostgreSQL)
pytest tests/ -v

# Только FSM тесты (без БД)
pytest tests/test_fsm.py -v
```

## Миграционные ворота (Migration Gate)

Перед переходом к M3 все M1/M2 код должен пройти:
```bash
grep -r 'status = ' --include='*.py' app/
# → ноль результатов вне terminal tools
```

## Майлстоуны

| Этап | Статус | Описание |
|------|--------|----------|
| M1 Foundation | **В разработке** | PostgreSQL, FastAPI, OrderFSM, Trace, Admin |
| M2 Business Operations | Запланирован | Kitchen, Delivery, Inventory, YooKassa |
| M3 nano-vm Integration | Запланирован | ExecutionVM, nano-vm-mcp, ExecutionReceipt |
| M4 AI Layer | Запланирован | Агенты, NarrativeReceipt |
| M5 Observability | Запланирован | OTel, метрики |

## Лицензия

MIT
