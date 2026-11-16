# Architecture decision records

| ADR | Decision |
|---|---|
| [001](001-postgres-task-storage.md) | Tasks are stored in Postgres through psycopg 3; the service owns its schema and applies it idempotently under an advisory lock, without Alembic |
