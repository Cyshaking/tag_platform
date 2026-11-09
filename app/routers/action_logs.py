"""
routers/action_logs.py — V1.6 新增：用户操作日志查询接口

GET /api/action-logs — admin-only，按 user_id/module/action/target_type/时间筛选，分页返回
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.action_log import ActionLog
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/api/action-logs", tags=["action-logs"])


def _serialize(log: ActionLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "username": log.username,
        "module": log.module,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "target_name": log.target_name,
        "detail": log.detail,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("")
def list_action_logs(
    user_id: Optional[int] = Query(None, description="操作人 user_id"),
    username: Optional[str] = Query(None, description="操作人用户名（模糊匹配）"),
    module: Optional[str] = Query(None, description="模块名模糊匹配（metadata/tag_task/approval/...）"),
    action: Optional[str] = Query(None, description="动作（CREATE/UPDATE/DELETE/SUBMIT_APPROVAL/APPROVE/REJECT/EXECUTE/LOGIN/SWITCH/TEST）"),
    target_type: Optional[str] = Query(None, description="对象类型（META_TABLE/TAG_TASK/...）"),
    start_time: Optional[str] = Query(None, description="开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    _current_user: User = Depends(get_current_user),
    _admin: None = Depends(require_permission("*")),  # admin 通配权限
    db: Session = Depends(get_db),
):
    """查询用户操作日志（仅 admin 可访问）"""
    conditions = []
    if user_id is not None:
        conditions.append(ActionLog.user_id == user_id)
    if username:
        conditions.append(ActionLog.username.like(f"%{username}%"))
    if module:
        conditions.append(ActionLog.module.like(f"%{module}%"))
    if action:
        conditions.append(ActionLog.action == action)
    if target_type:
        conditions.append(ActionLog.target_type == target_type)
    if start_time:
        conditions.append(ActionLog.created_at >= start_time)
    if end_time:
        conditions.append(ActionLog.created_at <= end_time)

    # count：显式 conditions 列表 + select(func.count())，保证 total 与 items 同步
    count_stmt = select(func.count()).select_from(ActionLog)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = db.execute(count_stmt).scalar() or 0

    # items
    stmt = select(ActionLog)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(desc(ActionLog.created_at))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()

    return ApiResponse(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize(r) for r in rows],
    })
