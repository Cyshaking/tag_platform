"""
schemas/approval.py — 审批工单
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ApprovalSubmitRequest(BaseModel):
    target_id: int  # meta_tables.id
    ticket_type: str = "META_DATA"
    title: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    """approve / reject 通用"""
    comment: Optional[str] = None


class ApprovalLogOut(ORMModel):
    id: int
    ticket_id: int
    node: str
    approver_id: Optional[int] = None
    action: str
    comment: Optional[str] = None
    created_at: datetime


class ApprovalTicketOut(ORMModel):
    id: int
    ticket_no: str
    ticket_type: str
    target_id: int
    title: str
    submitter_id: int
    current_node: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    logs: List[ApprovalLogOut] = []
