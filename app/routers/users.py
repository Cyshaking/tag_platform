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


# V1.2.1 新增：权限目录接口（角色编辑可视化勾选面板用）
PERMISSION_CATALOG = {
    "metadata": {
        "module_name": "元数据",
        "permissions": [
            ("metadata:view", "查看元数据", "只读访问元数据表列表与详情"),
            ("metadata:manage", "管理元数据", "创建/编辑/删除元数据表与字段"),
            ("metadata:import", "Excel 导入", "从 Excel 批量导入元数据表定义"),
            ("metadata:export", "Excel 导出", "导出元数据表定义为 Excel"),
        ],
    },
    "relations": {
        "module_name": "表关系",
        "permissions": [
            ("relation:view", "查看表关系", "只读访问表关系列表"),
            ("relation:manage", "管理表关系", "创建/编辑/删除表关系"),
        ],
    },
    "enum": {
        "module_name": "枚举",
        "permissions": [
            ("enum:view", "查看枚举", "只读访问枚举选项"),
            ("enum:manage", "管理枚举", "创建/编辑/删除枚举选项"),
        ],
    },
    "datasource": {
        "module_name": "数据源",
        "permissions": [
            ("datasource:view", "查看数据源", "只读访问数据源列表"),
            ("datasource:manage", "管理数据源", "创建/编辑/删除数据源"),
        ],
    },
    "approval": {
        "module_name": "审批",
        "permissions": [
            ("approval:data_node", "数据接入审批节点", "审批流第一节点审批权限"),
            ("approval:tech_node", "技术审批节点", "审批流第二节点审批权限"),
            ("approval:biz_node", "业务审批节点", "审批流第三节点审批权限"),
            ("approval:reject", "驳回工单", "驳回任意审批节点"),
        ],
    },
    "tag_task": {
        "module_name": "标签任务",
        "permissions": [
            ("tag_task:view", "查看标签任务", "只读访问标签任务列表与详情"),
            ("tag_task:manage", "管理标签任务", "创建/编辑/删除标签任务"),
            ("tag_task:submit_approval", "提交审批", "把标签任务提交到审批流"),
        ],
    },
    "execution": {
        "module_name": "执行",
        "permissions": [
            ("execution:run", "执行 SQL", "提交执行任务到 SQL/Spark 引擎"),
            ("execution:view", "查看执行记录", "只读访问执行历史记录"),
        ],
    },
    "user": {
        "module_name": "用户与角色",
        "permissions": [
            ("user:manage", "管理用户与角色", "创建/编辑/删除用户与角色"),
            ("user:view", "查看用户与角色", "只读访问用户列表"),
        ],
    },
}


@router.get("/permissions/catalog")
def get_permission_catalog(current_user: User = Depends(get_current_user)):
    """返回权限码目录，用于角色编辑可视化勾选面板"""
    return ApiResponse(data={
        "modules": [
            {
                "module": module_key,
                "module_name": info["module_name"],
                "permissions": [
                    {"code": code, "name": name, "desc": desc}
                    for code, name, desc in info["permissions"]
                ],
            }
            for module_key, info in PERMISSION_CATALOG.items()
        ]
    })


def _parse_perms(perms_json: str) -> list:
    import json
    try:
        return json.loads(perms_json) if perms_json else []
    except Exception:
        return []
