"""
approval.py — 审批工单 + 审批日志
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class ApprovalTicket(Base):
    """审批工单"""
    __tablename__ = "approval_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(64), unique=True, nullable=False, index=True)
    serial_no = Column(String(20), unique=True, nullable=True, index=True)  # V1.4.3
    ticket_type = Column(String(32), nullable=False)  # META_DATA
    target_id = Column(Integer, nullable=False, index=True)  # meta_tables.id
    title = Column(String(256), nullable=False)
    submitter_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    current_node = Column(String(32), nullable=False)  # DATA_APPROVAL/TECH_APPROVAL/BIZ_APPROVAL/PASSED/REJECTED
    status = Column(String(32), default="pending", nullable=False)  # pending/in_progress/approved/rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    submitter = relationship("User", foreign_keys=[submitter_id])
    logs = relationship("ApprovalLog", back_populates="ticket", cascade="all, delete-orphan",
                        order_by="ApprovalLog.created_at")


class ApprovalLog(Base):
    """审批日志"""
    __tablename__ = "approval_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("approval_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    node = Column(String(32), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(16), nullable=False)  # SUBMIT/APPROVE/REJECT
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("ApprovalTicket", back_populates="logs")
