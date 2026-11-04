"""
schemas/user.py — 用户 & 角色 & 登录
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ========== 登录 ==========
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class SwitchRequest(BaseModel):
    """演示身份切换（V1.1）"""
    username: str = Field(..., min_length=1, max_length=64)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ========== 用户 ==========
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: Optional[str] = None
    role_ids: Optional[List[int]] = []


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class UserOut(ORMModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: bool
    roles: List[RoleOut] = []


class UserRoleAssign(BaseModel):
    role_ids: List[int] = Field(default_factory=list)


# ========== 角色 ==========
class RoleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RoleOut(ORMModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    permissions: List[str] = []
