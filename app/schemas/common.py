"""
schemas/common.py — 通用响应封装
"""
from typing import Any, Optional, TypeVar, Generic

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构"""
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class PaginatedResponse(ApiResponse, Generic[T]):
    data: Optional[PaginatedData[T]] = None


# --------- 通用序列化基类 ---------
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IdResponse(BaseModel):
    id: int
