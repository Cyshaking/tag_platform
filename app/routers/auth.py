"""
routers/auth.py — 登录鉴权
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.user import LoginRequest, LoginResponse, SwitchRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(req: LoginRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    result = svc.login(req.username, req.password)
    return ApiResponse(data=result)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = AuthService(db)
    return ApiResponse(data=svc._serialize_user(current_user))


@router.post("/switch")
def switch_identity(req: SwitchRequest,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """V1.1 演示身份切换：返回新 token + 目标用户信息"""
    svc = AuthService(db)
    return ApiResponse(data=svc.switch_identity(req.username, current_user.id))
