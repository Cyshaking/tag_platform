"""
routers/system_logs.py — V1.4.3 新增：系统日志查询接口

GET /api/system-logs  — admin-only，按 level/module/user/时间筛选，分页返回
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.system_log import SystemLog
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/api/system-logs", tags=["system-logs"])


def _serialize(log: SystemLog) -> dict:
    return {
        "id": log.id,
        "level": log.level,
        "module": log.module,
        "message": log.message,
        "user_id": log.user_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("")
def list_system_logs(
    level: Optional[str] = Query(None, description="日志级别：DEBUG/INFO/WARN/ERROR"),
    module: Optional[str] = Query(None, description="模块名模糊匹配"),
    user_id: Optional[int] = Query(None, description="操作人 user_id"),
    start_time: Optional[str] = Query(None, description="开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    current_user: User = Depends(get_current_user),
    _admin: None = Depends(require_permission("*")),  # admin 通配权限
    db: Session = Depends(get_db),
):
    """查询系统日志（仅 admin 可访问）"""
    conditions = []
    if level:
        conditions.append(SystemLog.level == level)
    if module:
        conditions.append(SystemLog.module.like(f"%{module}%"))
    if user_id is not None:
        conditions.append(SystemLog.user_id == user_id)
    if start_time:
        conditions.append(SystemLog.created_at >= start_time)
    if end_time:
        conditions.append(SystemLog.created_at <= end_time)

    # count：显式 conditions + select(func.count())，V1.6 修复 _where_criteria 导致的 500 异常
    count_stmt = select(func.count()).select_from(SystemLog)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = db.execute(count_stmt).scalar() or 0

    # items
    stmt = select(SystemLog)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(desc(SystemLog.created_at))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()

    return ApiResponse(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize(r) for r in rows],
    })
