"""
tests/unit/test_approval_service.py — 审批状态机单元测试
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.approval import ApprovalTicket, ApprovalLog
from app.db.models.metadata import MetaTable
from app.services.approval_service import ApprovalService, NODE_DATA, NODE_TECH, NODE_BIZ, NODE_PASSED, NODE_REJECTED
from app.utils.exceptions import BusinessException


class TestApprovalService:

    def test_submit_ticket(self, db: Session, sample_table):
        """提交工单成功"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(target_id=sample_table.id, ticket_type="META_DATA", submitter_id=1)

        assert ticket.ticket_no.startswith("TK")
        assert ticket.current_node == NODE_DATA
        assert ticket.status == "in_progress"
        assert len(ticket.logs) >= 1
        assert ticket.logs[0].action == "SUBMIT"

    def test_submit_duplicate_rejected(self, db: Session, sample_table):
        """同一目标重复提交 → 拒绝"""
        svc = ApprovalService(db)
        svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)
        with pytest.raises(BusinessException) as exc:
            svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)
        assert "进行中" in exc.value.message

    def test_three_level_approve_flow(self, db: Session, sample_table):
        """三级审批全部通过 → PASSED"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)
        tid = ticket.id

        # data_approver 过
        ticket = svc.approve(tid, approver_id=2, comment="OK")  # dap 的 role
        assert ticket.current_node == NODE_TECH

        # tech_approver 过
        ticket = svc.approve(tid, approver_id=3, comment="技术上OK")
        assert ticket.current_node == NODE_BIZ

        # biz_approver 过
        ticket = svc.approve(tid, approver_id=4, comment="业务OK")
        assert ticket.current_node == NODE_PASSED
        assert ticket.status == "approved"

    def test_reject_keeps_node(self, db: Session, sample_table):
        """驳回后停留在当前节点"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)

        # data_approver 驳回
        ticket = svc.reject(ticket.id, approver_id=2, comment="字段不全")
        assert ticket.current_node == NODE_DATA  # 节点不变
        assert ticket.status == "rejected"

    def test_wrong_role_cannot_approve(self, db: Session, sample_table):
        """非对应角色无法审批当前节点"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)

        # tech_approver 去审批 data 节点 → 被拒绝
        with pytest.raises(BusinessException) as exc:
            svc.approve(ticket.id, approver_id=3)  # tech_approver
        assert "角色" in exc.value.message

    def test_terminal_state_blocks(self, db: Session, sample_table):
        """已通过/已驳回后再审批 → 异常"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)
        ticket = svc.reject(ticket.id, approver_id=2)  # 驳回

        with pytest.raises(BusinessException) as exc:
            svc.approve(ticket.id, approver_id=2)
        # 已结束 或 rejected 不可审批
        assert "不可审批" in exc.value.message

    def test_list_my_pending(self, db: Session, sample_table):
        """我的待办只返回当前角色能审批的"""
        svc = ApprovalService(db)
        svc.submit_ticket(sample_table.id, "META_DATA", submitter_id=1)

        # data_approver 有 1 条待办
        my = svc.list_tickets(current_user_id=2, show_my_pending=True)
        assert len(my) == 1

        # tech_approver 在 data 节点时无待办
        my2 = svc.list_tickets(current_user_id=3, show_my_pending=True)
        assert len(my2) == 0
