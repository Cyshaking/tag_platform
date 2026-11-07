"""
services/auth_service.py — 登录认证 + Token + 权限校验
"""
from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User, Role, UserRole
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_AUTH, ERR_PERMISSION, ERR_NOT_FOUND
from app.utils.security import verify_password, create_access_token


class AuthService(BaseService):
    MODULE = "auth"

    def login(self, username: str, password: str) -> dict:
        """登录：验证密码 → 生成 token → 返回用户 + token"""
        stmt = select(User).where(User.username == username)
        user = self.db.execute(stmt).scalar_one_or_none()

        if not user:
            raise BusinessException(ERR_AUTH, "用户名或密码错误")
        if not user.is_active:
            raise BusinessException(ERR_AUTH, "用户已被禁用")
        if not verify_password(password, user.password_hash):
            raise BusinessException(ERR_AUTH, "用户名或密码错误")

        token = create_access_token(user.id)
        self._log_info(f"用户 {username} 登录成功", user.id)
        self._log_action("LOGIN", "AUTH", user.id, username, user_id=user.id)
        self.db.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": self._serialize_user(user),
        }

    def switch_identity(self, username: str, operator_id: int) -> dict:
        """
        V1.1 演示身份切换：免密切换到 demo_switch 白名单用户。

        仅演示环境使用；config.yaml demo_switch.enabled=false 时拒绝。
        """
        from app.config import demo_switch as switch_cfg

        if not switch_cfg.enabled:
            raise BusinessException(ERR_PERMISSION, "演示身份切换已关闭（demo_switch.enabled=false）")
        if username not in switch_cfg.users:
            raise BusinessException(
                ERR_PERMISSION, f"用户 '{username}' 不在演示身份白名单中"
            )

        stmt = select(User).where(User.username == username)
        user = self.db.execute(stmt).scalar_one_or_none()
        if not user:
            raise BusinessException(ERR_NOT_FOUND, f"用户 '{username}' 不存在")
        if not user.is_active:
            raise BusinessException(ERR_AUTH, f"用户 '{username}' 已被禁用")

        token = create_access_token(user.id)

        old_user = self.db.get(User, operator_id)
        old_name = old_user.username if old_user else f"#{operator_id}"
        self._log_info(f"[switch_identity] {old_name} → {username}", user.id)
        self._log_action("SWITCH", "AUTH", user.id, username,
                         detail=f"from={old_name}", user_id=user.id)
        self._log_action("LOGIN", "AUTH", user.id, username, user_id=user.id)
        self.db.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": self._serialize_user(user),
        }

    def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户合并后的所有权限码（取所有角色权限的并集）"""
        stmt = (
            select(Role.permissions)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        rows = self.db.execute(stmt).all()

        perms: List[str] = []
        for row in rows:
            try:
                list_data = json.loads(row[0]) if row[0] else []
                perms.extend(list_data)
            except (json.JSONDecodeError, TypeError):
                continue
        return perms

    def has_permission(self, user_id: int, permission_code: str) -> bool:
        """判断用户是否有指定权限。'*' 通配所有"""
        perms = self.get_user_permissions(user_id)
        return "*" in perms or permission_code in perms

    def require_permission(self, user_id: int, permission_code: str) -> None:
        """强制校验，无权限抛异常"""
        if not self.has_permission(user_id, permission_code):
            raise BusinessException(
                ERR_PERMISSION,
                f"缺少权限: {permission_code}",
            )

    def _serialize_user(self, user: User) -> dict:
        """序列化用户（含角色）"""
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "is_active": user.is_active,
            "roles": [
                {"id": r.id, "code": r.code, "name": r.name}
                for r in user.roles
            ],
        }
