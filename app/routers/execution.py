"""
routers/execution.py — SQL 执行引擎调度 + 执行记录查询
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.execution import ExecutionSubmitRequest
from app.services.execution_service import ExecutionService

router = APIRouter(prefix="/api/execution", tags=["execution"])


def _serialize_record(r) -> dict:
    return {
        "id": r.id, "tag_task_id": r.tag_task_id, "datasource_id": r.datasource_id,
        "submitted_sql": r.submitted_sql, "ds_type": r.ds_type,
        "external_task_id": r.external_task_id, "status": r.status,
        "execute_log": r.execute_log, "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/submit")
def submit(req: ExecutionSubmitRequest,
           background_tasks: BackgroundTasks,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ExecutionService(db)
    record = svc.submit(
        tag_task_id=req.tag_task_id, datasource_id=req.datasource_id,
        background_tasks=background_tasks, operator_id=current_user.id,
    )
    return ApiResponse(data=_serialize_record(record))


@router.get("/records")
def list_records(tag_task_id: Optional[int] = None, status: Optional[str] = None,
                  limit: int = 100, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    svc = ExecutionService(db)
    records = svc.list_records(tag_task_id=tag_task_id, status=status, limit=limit)
    return ApiResponse(data=[_serialize_record(r) for r in records])


@router.get("/records/{record_id}")
def get_record(record_id: int, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    svc = ExecutionService(db)
    record = svc.get_record(record_id)
    if not record:
        return ApiResponse(code=40400, message="执行记录不存在")
    return ApiResponse(data=_serialize_record(record))
