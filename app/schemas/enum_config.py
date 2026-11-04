"""
schemas/enum_config.py — 字段枚举
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EnumCreate(BaseModel):
    table_id: int
    field_id: int
    enum_code: str = Field(..., min_length=1, max_length=64)
    enum_label: str = Field(..., min_length=1, max_length=128)
    ordinal: int = 0


class EnumBatchCreate(BaseModel):
    """一次保存某字段下所有枚举（整体替换）"""
    table_id: int
    field_id: int
    enums: List[EnumCreate] = Field(default_factory=list)


class EnumOut(ORMModel):
    id: int
    table_id: int
    field_id: int
    enum_code: str
    enum_label: str
    ordinal: int
