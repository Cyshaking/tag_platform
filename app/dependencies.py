"""
dependencies.py — FastAPI 依赖注入
- get_db: 获取数据库 Session
- get_current_user: 从 JWT 解析当前登录用户
- require_permission: 权限码校验
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.utils.security import decode_access_token


def _get_token(request: Request) -> Optional[str]:
    """从 Authorization: Bearer <token> 提取 token"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """依赖：当前登录用户。无 token 或无效则 401"""
    token = _get_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 Token 过期")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效或已过期")

    user_id = int(payload.get("sub", "0"))
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """依赖：当前用户（可选，未登录不报错）"""
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def require_permission(permission_code: str):
    """
    依赖工厂：需要指定权限码才能访问
    使用方式：
        @router.get("/admin", dependencies=[Depends(require_permission("user:manage"))])
    """
    def _check(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
        from app.services.auth_service import AuthService
        svc = AuthService(db)
        if not svc.has_permission(user.id, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_code}",
            )
    return _check
