"""
services/user_service.py — 用户 & 角色管理
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User, Role, UserRole
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_VALIDATION, ERR_NOT_FOUND, ERR_PERMISSION, ERR_BAD_REQUEST
from app.utils.security import hash_password


class UserService(BaseService):
    MODULE = "user"

    # ========== 用户 ==========
    def list_users(self) -> List[User]:
        return self.db.execute(select(User).order_by(User.id)).scalars().all()

    def get_user(self, user_id: int) -> Optional[User]:
        return self.db.get(User, user_id)

    def create_user(self, username: str, password: str, display_name: Optional[str] = None,
                    role_ids: Optional[List[int]] = None, operator_id: Optional[int] = None) -> User:
        # 检查用户名唯一
        existing = self.db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_VALIDATION, f"用户名 '{username}' 已存在")

        user = User(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()

        # 绑定角色
        if role_ids:
            for rid in role_ids:
                role = self.db.get(Role, rid)
                if role:
                    self.db.add(UserRole(user_id=user.id, role_id=role.id))

        self.db.commit()
        self._log_info(f"创建用户 {username}", operator_id)
        return user

    def update_user(self, user_id: int, display_name: Optional[str] = None, password: Optional[str] = None,
                    is_active: Optional[bool] = None, role_ids: Optional[List[int]] = None,
                    operator_id: Optional[int] = None) -> User:
        user = self.db.get(User, user_id)
        if not user:
            raise BusinessException(ERR_NOT_FOUND, f"用户 {user_id} 不存在")

        if display_name is not None:
            user.display_name = display_name
        if password is not None:
            user.password_hash = hash_password(password)
        if is_active is not None:
            user.is_active = is_active
        user.updated_at = datetime.utcnow()

        # 更新角色绑定（整体替换）
        if role_ids is not None:
            self.db.execute(select(UserRole).where(UserRole.user_id == user_id)).scalars().all()
            self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
            for rid in role_ids:
                role = self.db.get(Role, rid)
                if role:
                    self.db.add(UserRole(user_id=user.id, role_id=role.id))

        self.db.commit()
        self._log_info(f"更新用户 {user.username}", operator_id)
        return user

    def delete_user(self, user_id: int, operator_id: Optional[int] = None) -> None:
        user = self.db.get(User, user_id)
        if not user:
            raise BusinessException(ERR_NOT_FOUND, f"用户 {user_id} 不存在")
        # 不允许删除自己
        if user.id == operator_id:
            raise BusinessException(ERR_BAD_REQUEST, "不能删除当前登录用户")
        self.db.delete(user)
        self.db.commit()
        self._log_info(f"删除用户 {user.username}", operator_id)

    # ========== 角色 ==========
    def list_roles(self) -> List[Role]:
        return self.db.execute(select(Role).order_by(Role.id)).scalars().all()

    def get_role(self, role_id: int) -> Optional[Role]:
        return self.db.get(Role, role_id)

    def create_role(self, code: str, name: str, description: Optional[str] = None,
                    permissions: Optional[List[str]] = None, operator_id: Optional[int] = None) -> Role:
        existing = self.db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
        if existing:
            raise BusinessException(ERR_VALIDATION, f"角色编码 '{code}' 已存在")

        role = Role(
            code=code,
            name=name,
            description=description,
            permissions=json.dumps(permissions or [], ensure_ascii=False),
        )
        self.db.add(role)
        self.db.commit()
        self._log_info(f"创建角色 {code}", operator_id)
        return role

    def update_role(self, role_id: int, name: Optional[str] = None, description: Optional[str] = None,
                    permissions: Optional[List[str]] = None, operator_id: Optional[int] = None) -> Role:
        role = self.db.get(Role, role_id)
        if not role:
            raise BusinessException(ERR_NOT_FOUND, f"角色 {role_id} 不存在")

        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        if permissions is not None:
            role.permissions = json.dumps(permissions, ensure_ascii=False)

        self.db.commit()
        self._log_info(f"更新角色 {role.code}", operator_id)
        return role

    def delete_role(self, role_id: int, operator_id: Optional[int] = None) -> None:
        role = self.db.get(Role, role_id)
        if not role:
            raise BusinessException(ERR_NOT_FOUND, f"角色 {role_id} 不存在")

        # 预置角色不可删除
        preset_codes = ("admin", "data_approver", "tech_approver", "biz_approver", "user")
        if role.code in preset_codes:
            raise BusinessException(ERR_BAD_REQUEST, f"预置角色 '{role.code}' 不可删除")

        # 检查是否有用户在使用
        refs = self.db.execute(select(UserRole).where(UserRole.role_id == role_id)).scalars().all()
        if refs:
            raise BusinessException(ERR_BAD_REQUEST, f"角色 '{role.name}' 正在被用户使用，无法删除")

        self.db.delete(role)
        self.db.commit()
        self._log_info(f"删除角色 {role.code}", operator_id)
