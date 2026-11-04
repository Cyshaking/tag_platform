"""
routers/approvals.py — 审批工单（提交 / 列表 / 通过 / 驳回）
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.approval import ApprovalSubmitRequest, ApprovalActionRequest
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _serialize_ticket(t) -> dict:
    return {
        "id": t.id, "ticket_no": t.ticket_no, "ticket_type": t.ticket_type,
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


@router.get("")
def list_tickets(status: Optional[str] = None, show_my_pending: bool = False,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    tickets = svc.list_tickets(status=status, current_user_id=current_user.id,
                               show_my_pending=show_my_pending)
    return ApiResponse(data=[_serialize_ticket(t) for t in tickets])


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    ticket = svc.get_ticket(ticket_id)
    if not ticket:
        return ApiResponse(code=40400, message="工单不存在")
    return ApiResponse(data=_serialize_ticket(ticket))


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
