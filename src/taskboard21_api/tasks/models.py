"""Request and response models for tasks."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, StrictStr, field_validator

MAX_TITLE_LENGTH = 200
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskCreate(BaseModel):
    """Body of ``POST /tasks``."""

    title: StrictStr
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        if len(v) > MAX_TITLE_LENGTH:
            raise ValueError(f"title must be at most {MAX_TITLE_LENGTH} characters")
        if not v.strip():
            raise ValueError("title must not be blank")
        return v

    @field_validator("due_date", mode="before")
    @classmethod
    def _check_due_date(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, str) or not _ISO_DATE.match(v):
            raise ValueError("due_date must be a string in YYYY-MM-DD format")
        return date.fromisoformat(v)


class Task(BaseModel):
    """A stored task."""

    id: str
    title: str
    due_date: date | None
