"""
routers/users.py — 用户 & 角色管理
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse
from app.schemas.user import UserCreate, UserUpdate, UserOut, RoleCreate, RoleUpdate, RoleOut, UserRoleAssign
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


# ========== 用户 ==========
@router.get("", dependencies=[Depends(require_permission("user:manage"))])
def list_users(db: Session = Depends(get_db)):
    svc = UserService(db)
    users = svc.list_users()
    return ApiResponse(data=[
        {
            "id": u.id, "username": u.username, "display_name": u.display_name,
            "is_active": u.is_active,
            "roles": [{"id": r.id, "code": r.code, "name": r.name} for r in u.roles],
        } for u in users
    ])


@router.post("", dependencies=[Depends(require_permission("user:manage"))])
def create_user(req: UserCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    user = svc.create_user(
        username=req.username, password=req.password,
        display_name=req.display_name, role_ids=req.role_ids,
        operator_id=current_user.id,
    )
    return ApiResponse(data={"id": user.id})


@router.put("/{user_id}", dependencies=[Depends(require_permission("user:manage"))])
def update_user(user_id: int, req: UserUpdate,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    svc.update_user(
        user_id=user_id,
        display_name=req.display_name, password=req.password,
        is_active=req.is_active, role_ids=req.role_ids,
        operator_id=current_user.id,
    )
    return ApiResponse()


@router.delete("/{user_id}", dependencies=[Depends(require_permission("user:manage"))])
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    svc.delete_user(user_id=user_id, operator_id=current_user.id)
    return ApiResponse()


# ========== 角色 ==========
@router.get("/roles", dependencies=[Depends(require_permission("user:manage"))])
def list_roles(db: Session = Depends(get_db)):
    svc = UserService(db)
    roles = svc.list_roles()
    return ApiResponse(data=[
        {
            "id": r.id, "code": r.code, "name": r.name,
            "description": r.description, "permissions": _parse_perms(r.permissions),
        } for r in roles
    ])


@router.post("/roles", dependencies=[Depends(require_permission("user:manage"))])
def create_role(req: RoleCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    role = svc.create_role(code=req.code, name=req.name, description=req.description,
                           permissions=req.permissions, operator_id=current_user.id)
    return ApiResponse(data={"id": role.id})


@router.put("/roles/{role_id}", dependencies=[Depends(require_permission("user:manage"))])
def update_role(role_id: int, req: RoleUpdate,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    svc.update_role(role_id=role_id, name=req.name, description=req.description,
                    permissions=req.permissions, operator_id=current_user.id)
    return ApiResponse()


@router.delete("/roles/{role_id}", dependencies=[Depends(require_permission("user:manage"))])
def delete_role(role_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = UserService(db)
    svc.delete_role(role_id=role_id, operator_id=current_user.id)
    return ApiResponse()


def _parse_perms(perms_json: str) -> list:
    import json
    try:
        return json.loads(perms_json) if perms_json else []
    except Exception:
        return []
