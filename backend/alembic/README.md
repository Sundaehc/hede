# Alembic migrations

Common commands, run from `backend/`:

```bash
alembic current
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic stamp head
```

Existing databases that already match the baseline should be stamped once:

```bash
alembic stamp head
```
