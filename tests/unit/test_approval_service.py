"""
tests/unit/test_approval_service.py — 审批状态机单元测试

V1.5: 元数据(META_DATA)不再需要审批，所有用例改用标签任务(TAG_TASK)
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.approval import ApprovalTicket, ApprovalLog
from app.db.models.tag_task import TagTask
from app.services.approval_service import ApprovalService, NODE_DATA, NODE_TECH, NODE_BIZ, NODE_PASSED, NODE_REJECTED
from app.utils.exceptions import BusinessException


class TestApprovalService:

    def test_submit_ticket(self, db: Session, sample_tag_task: TagTask):
        """提交工单成功 — TAG_TASK 类型"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(target_id=sample_tag_task.id, ticket_type="TAG_TASK", submitter_id=1)

        assert ticket.ticket_no.startswith("APP")  # V1.4.3: ticket_no 改成 APP+日期+序号
        assert ticket.current_node == NODE_DATA
        assert ticket.status == "in_progress"
        assert len(ticket.logs) >= 1
        assert ticket.logs[0].action == "SUBMIT"
        # V1.2: 提交后标签任务状态也变成审批中
        db.refresh(sample_tag_task)
        assert sample_tag_task.status == "in_progress"

    def test_submit_duplicate_rejected(self, db: Session, sample_tag_task: TagTask):
        """同一目标重复提交 → 拒绝"""
        svc = ApprovalService(db)
        svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)
        with pytest.raises(BusinessException) as exc:
            svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)
        assert "进行中" in exc.value.message

    def test_three_level_approve_flow(self, db: Session, sample_tag_task: TagTask):
        """三级审批全部通过 → PASSED"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)
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

        # V1.2: 联动 — 标签任务也变成 approved
        db.refresh(sample_tag_task)
        assert sample_tag_task.status == "approved"

    def test_reject_keeps_node(self, db: Session, sample_tag_task: TagTask):
        """驳回后停留在当前节点"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)

        # data_approver 驳回
        ticket = svc.reject(ticket.id, approver_id=2, comment="字段不全")
        assert ticket.current_node == NODE_DATA  # 节点不变
        assert ticket.status == "rejected"

        # V1.2: 联动 — 标签任务也变成 rejected
        db.refresh(sample_tag_task)
        assert sample_tag_task.status == "rejected"

    def test_wrong_role_cannot_approve(self, db: Session, sample_tag_task: TagTask):
        """非对应角色无法审批当前节点"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)

        # tech_approver 去审批 data 节点 → 被拒绝
        with pytest.raises(BusinessException) as exc:
            svc.approve(ticket.id, approver_id=3)  # tech_approver
        assert "角色" in exc.value.message

    def test_terminal_state_blocks(self, db: Session, sample_tag_task: TagTask):
        """已通过/已驳回后再审批 → 异常"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)
        ticket = svc.reject(ticket.id, approver_id=2)  # 驳回

        with pytest.raises(BusinessException) as exc:
            svc.approve(ticket.id, approver_id=2)
        # 已结束 或 rejected 不可审批
        assert "不可审批" in exc.value.message

    def test_list_my_pending(self, db: Session, sample_tag_task: TagTask):
        """我的待办只返回当前角色能审批的"""
        svc = ApprovalService(db)
        svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)

        # data_approver 有 1 条待办
        my = svc.list_tickets(current_user_id=2, show_my_pending=True)
        assert len(my) == 1

        # tech_approver 在 data 节点时无待办
        my2 = svc.list_tickets(current_user_id=3, show_my_pending=True)
        assert len(my2) == 0

    # ========== V1.5 新增 ==========
    def test_submit_metadata_rejected(self, db: Session, sample_table):
        """V1.5: META_DATA 提交直接被拒绝"""
        svc = ApprovalService(db)
        with pytest.raises(BusinessException) as exc:
            svc.submit_ticket(target_id=sample_table.id, ticket_type="META_DATA", submitter_id=1)
        assert "无需审批" in exc.value.message

    def test_delete_approved_ticket(self, db: Session, sample_tag_task: TagTask):
        """V1.5: 已结束工单可以删除"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)
        tid = ticket.id

        # 先驳回让它结束
        ticket = svc.reject(tid, approver_id=2, comment="驳回")
        assert ticket.status == "rejected"

        # 删除
        svc.delete_ticket(tid, operator_id=1)
        assert svc.get_ticket(tid) is None

    def test_delete_in_progress_blocked(self, db: Session, sample_tag_task: TagTask):
        """V1.5: 进行中的工单不可删除"""
        svc = ApprovalService(db)
        ticket = svc.submit_ticket(sample_tag_task.id, "TAG_TASK", submitter_id=1)

        with pytest.raises(BusinessException) as exc:
            svc.delete_ticket(ticket.id, operator_id=1)
        assert "不可删除" in exc.value.message
