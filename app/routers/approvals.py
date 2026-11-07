"""
routers/approvals.py — 审批工单（提交 / 列表 / 通过 / 驳回 / 统计）
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.approval import ApprovalTicket
from app.db.models.user import User, Role, UserRole
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.approval import ApprovalSubmitRequest, ApprovalActionRequest
from app.services.approval_service import ApprovalService, NODE_ROLE_MAP

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _serialize_ticket(t, db=None) -> dict:
    data = {
        "id": t.id, "ticket_no": t.ticket_no, "serial_no": t.serial_no, "ticket_type": t.ticket_type,
        "target_id": t.target_id, "title": t.title, "submitter_id": t.submitter_id,
        "current_node": t.current_node, "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "logs": [{
            "id": l.id, "node": l.node, "approver_id": l.approver_id,
            "action": l.action, "comment": l.comment,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in t.logs],
    }
    # V1.2.1: 补充目标详情
    if db is not None:
        try:
            if t.ticket_type == "TAG_TASK":
                from app.db.models.tag_task import TagTask
                task = db.get(TagTask, t.target_id)
                if task:
                    data["target_info"] = {
                        "task_name": task.task_name,
                        "task_mode": task.task_mode,
                        "business_theme": task.business_theme,
                        "tag_value_code": task.tag_value_code,
                        "status": task.status,
                        "generated_sql": task.generated_sql,
                    }
            elif t.ticket_type == "META_DATA":
                from app.db.models.metadata import MetaTable
                table = db.get(MetaTable, t.target_id)
                if table:
                    data["target_info"] = {
                        "table_name": table.table_name,
                        "table_comment": table.table_comment,
                        "status": table.status,
                        "field_count": len(table.fields) if table.fields else 0,
                    }
        except Exception:
            pass
    return data


@router.get("")
def list_tickets(status: Optional[str] = None, show_my_pending: bool = False,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    tickets = svc.list_tickets(status=status, current_user_id=current_user.id,
                               show_my_pending=show_my_pending)
    return ApiResponse(data=[_serialize_ticket(t, db) for t in tickets])


# V1.3 新增：/count 必须在 /{ticket_id} 之前，否则 "count" 会被当作 ticket_id
@router.get("/count")
def count_tickets(show_my_pending: bool = False,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Role.code).join(UserRole).where(UserRole.user_id == current_user.id)
    user_role_codes = [row[0] for row in db.execute(stmt).all()]
    is_admin = "admin" in user_role_codes

    total_stmt = select(func.count()).where(ApprovalTicket.status == "in_progress")
    total = db.execute(total_stmt).scalar() or 0

    if show_my_pending:
        if is_admin:
            pending = total
        else:
            allowed_nodes = [
                node for node, role in NODE_ROLE_MAP.items()
                if role in user_role_codes
            ]
            if allowed_nodes:
                pending_stmt = select(func.count()).where(
                    ApprovalTicket.status == "in_progress",
                    ApprovalTicket.current_node.in_(allowed_nodes),
                )
                pending = db.execute(pending_stmt).scalar() or 0
            else:
                pending = 0
    else:
        pending = total

    return ApiResponse(data={"pending": pending, "total": total})


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    ticket = svc.get_ticket(ticket_id)
    if not ticket:
        return ApiResponse(code=40400, message="工单不存在")
    return ApiResponse(data=_serialize_ticket(ticket, db))


@router.post("/submit")
def submit_ticket(req: ApprovalSubmitRequest,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    ticket = svc.submit_ticket(
        target_id=req.target_id, ticket_type=req.ticket_type,
        title=req.title, submitter_id=current_user.id,
    )
    return ApiResponse(data={"id": ticket.id, "ticket_no": ticket.ticket_no})


@router.post("/{ticket_id}/approve")
def approve(ticket_id: int, req: ApprovalActionRequest,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    ticket = svc.approve(ticket_id=ticket_id, approver_id=current_user.id, comment=req.comment)
    return ApiResponse(data={"current_node": ticket.current_node, "status": ticket.status})


@router.post("/{ticket_id}/reject")
def reject(ticket_id: int, req: ApprovalActionRequest,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    ticket = svc.reject(ticket_id=ticket_id, approver_id=current_user.id, comment=req.comment)
    return ApiResponse(data={"current_node": ticket.current_node, "status": ticket.status})


# V1.5: 删除审批记录（仅已结束工单可删）
@router.delete("/{ticket_id}")
def delete_ticket(ticket_id: int,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    svc.delete_ticket(ticket_id=ticket_id, operator_id=current_user.id)
    return ApiResponse()
