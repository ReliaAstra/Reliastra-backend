"""Shared pagination request and response contracts."""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: UUID | None = None
    sort: str = "-created_at"


class OffsetParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: UUID | None = None
    total: int | None = None
