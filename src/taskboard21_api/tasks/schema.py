"""Task schema: idempotent DDL applied by the store under an advisory lock."""

from __future__ import annotations

SCHEMA_LOCK_ID = 2002001

# Append new statements; never edit one that has been applied.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS tasks (
        seq        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        id         uuid        NOT NULL UNIQUE,
        title      text        NOT NULL,
        due_date   date,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
]
