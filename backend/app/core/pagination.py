from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

T = TypeVar("T")

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100


class PaginationMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = DEFAULT_PAGE_LIMIT


class PaginatedResponse(BaseModel, Generic[T]):
    """Canonical list envelope. Also exposes legacy ``items`` / ``total``."""

    model_config = ConfigDict(from_attributes=True)

    data: list[T] = Field(default_factory=list)
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)
    total: int | None = None
    page: int | None = None
    size: int | None = None
    pages: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_kwargs(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        if "items" in values and "data" not in values:
            values["data"] = values["items"]
        items = values.get("data") or values.get("items") or []
        limit = values.get("size") or values.get("limit") or DEFAULT_PAGE_LIMIT
        page = values.get("page")
        pages = values.get("pages")
        next_cursor = values.get("next_cursor")
        has_more = values.get("has_more")
        if has_more is None and pages is not None and page is not None:
            has_more = page < pages
        if "pagination" not in values:
            values["pagination"] = {
                "next_cursor": str(next_cursor) if next_cursor is not None else None,
                "has_more": bool(has_more),
                "limit": int(limit),
            }
        values.setdefault("data", items)
        return values

    @computed_field  # type: ignore[prop-decorator]
    @property
    def items(self) -> list[T]:
        return self.data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def next_cursor(self) -> str | None:
        return self.pagination.next_cursor

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_more(self) -> bool:
        return self.pagination.has_more


CursorPagination = PaginatedResponse
OffsetPagination = PaginatedResponse


def paginated(
    items: list[T],
    *,
    limit: int,
    has_more: bool,
    next_cursor: str | None,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            next_cursor=next_cursor,
            has_more=has_more,
            limit=limit,
        ),
    )


def slice_page(rows: list[T], limit: int, cursor_attr: str = "id") -> PaginatedResponse[T]:
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        value = getattr(items[-1], cursor_attr, None)
        next_cursor = str(value) if value is not None else None
    return paginated(items, limit=limit, has_more=has_more, next_cursor=next_cursor)
