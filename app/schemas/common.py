from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    detail: str


class PaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ListResponse(BaseModel, Generic[T]):
    items: list[T]  # type: ignore[valid-type]
    total: int
    skip: int
    limit: int
