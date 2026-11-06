"""
routers/tag_tasks.py — 标签任务配置（V1.1 双模式）

路由注册顺序很关键！/preview-sql、/validate-sql 必须在 /{task_id} 之前注册，
否则 FastAPI 会把它们当作 task_id 参数匹配。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.tag_task import (
    PreviewSQLRequest, TagTaskCreate, TagTaskUpdate, ValidateSQLRequest,
)
from app.services.tag_task_service import TagTaskService
from app.services.approval_service import ApprovalService  # V1.2 新增

router = APIRouter(prefix="/api/tag-tasks", tags=["tag_tasks"])


def _serialize(t) -> dict:
    return {
        "id": t.id, "task_name": t.task_name, "task_mode": t.task_mode,
        "theme_id": t.theme_id, "business_theme": t.business_theme,
        "main_table_id": t.main_table_id, "main_field_id": t.main_field_id,
        "tag_value_code": t.tag_value_code, "raw_sql": t.raw_sql,
        "field_config_json": t.field_config_json, "datasource_id": t.datasource_id,
        "generated_sql": t.generated_sql,
        "status": getattr(t, 'status', 'pending'),  # V1.2：审批状态
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    return ApiResponse(data=[_serialize(t) for t in svc.list_tasks()])


# ========== 预览 SQL (必须在 /{task_id} 之前注册!) ==========
@router.post("/preview-sql")
def preview_sql_post(req: PreviewSQLRequest, db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    sql = svc.preview_sql(
        main_table_id=req.main_table_id, main_field_id=req.main_field_id,
        tag_value_code=req.tag_value_code, task_mode=req.task_mode,
        theme_id=req.theme_id, raw_sql=req.raw_sql, field_config=req.field_config,
    )
    return ApiResponse(data={"sql": sql})


@router.get("/preview-sql")
def preview_sql(main_table_id: Optional[int] = None,
                main_field_id: Optional[int] = None,
                tag_value_code: Optional[str] = None,
                task_mode: str = "FIELD",
                theme_id: Optional[int] = None,
                raw_sql: Optional[str] = None,
                field_config_json: Optional[str] = None,
                db: Session = Depends(get_db)):
    field_config = None
    if field_config_json:
        try:
            field_config = json.loads(field_config_json)
        except (json.JSONDecodeError, TypeError):
            return ApiResponse(code=40001, message="field_config_json 不是合法 JSON")
    svc = TagTaskService(db)
    sql = svc.preview_sql(
        main_table_id=main_table_id, main_field_id=main_field_id,
        tag_value_code=tag_value_code, task_mode=task_mode,
        theme_id=theme_id, raw_sql=raw_sql, field_config=field_config,
    )
    return ApiResponse(data={"sql": sql})


# ========== SQL 校验 ==========
@router.post("/validate-sql")
def validate_sql(req: ValidateSQLRequest, db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    result = svc.validate_sql(req.sql, req.datasource_id)
    return ApiResponse(data=result)


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    task = svc.get_task(task_id)
    if not task:
        return ApiResponse(code=40400, message="标签任务不存在")
    return ApiResponse(data=_serialize(task))


@router.post("")
def create_task(req: TagTaskCreate,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    task = svc.create_task(
        task_name=req.task_name, business_theme=req.business_theme,
        main_table_id=req.main_table_id, main_field_id=req.main_field_id,
        tag_value_code=req.tag_value_code, datasource_id=req.datasource_id,
        created_by=current_user.id, task_mode=req.task_mode,
        theme_id=req.theme_id, raw_sql=req.raw_sql, field_config=req.field_config,
    )
    return ApiResponse(data={"id": task.id, "generated_sql": task.generated_sql})


@router.put("/{task_id}")
def update_task(task_id: int, req: TagTaskUpdate,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    svc.update_task(
        task_id=task_id, task_name=req.task_name,
        business_theme=req.business_theme, tag_value_code=req.tag_value_code,
        datasource_id=req.datasource_id, operator_id=current_user.id,
        raw_sql=req.raw_sql, field_config=req.field_config,
    )
    return ApiResponse()


@router.delete("/{task_id}")
def delete_task(task_id: int,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = TagTaskService(db)
    svc.delete_task(task_id=task_id, operator_id=current_user.id)
    return ApiResponse()


# V1.2 新增：提交标签任务审批
@router.post("/{task_id}/submit-approval")
def submit_task_approval(task_id: int, title: Optional[str] = None,
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    approval_svc = ApprovalService(db)
    ticket = approval_svc.submit_ticket(
        target_id=task_id, ticket_type="TAG_TASK",
        title=title, submitter_id=current_user.id,
    )
    return ApiResponse(data={"ticket_id": ticket.id, "ticket_no": ticket.ticket_no})
