"""
schemas/theme.py — 业务主题（V1.1）
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ThemeCreate(BaseModel):
    theme_code: str = Field(..., min_length=2, max_length=64)
    theme_name: str = Field(..., min_length=1, max_length=128)
    main_table_id: int
    description: Optional[str] = None
    is_enabled: bool = True


class ThemeUpdate(BaseModel):
    theme_name: Optional[str] = None
    main_table_id: Optional[int] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None


class ThemeOut(ORMModel):
    id: int
    theme_code: str
    theme_name: str
    main_table_id: int
    description: Optional[str] = None
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class ThemeFieldOut(BaseModel):
    id: int
    field_name: str
    field_type: str
    field_comment: Optional[str] = None
    is_primary_key: bool
    ordinal_position: int


class ThemeTableOut(BaseModel):
    table_id: int
    table_name: str
    table_comment: Optional[str] = None
    fields: List[ThemeFieldOut] = []
