"""
services/approval_service.py — 三级审批工单状态机

流程：DATA_APPROVAL → TECH_APPROVAL → BIZ_APPROVAL → PASSED
驳回：停留在当前节点，记录审批意见
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.approval import ApprovalTicket, ApprovalLog
from app.db.models.user import User, Role, UserRole
from app.db.models.metadata import MetaTable
from app.db.models.tag_task import TagTask  # V1.2 新增
from app.services.base import BaseService
from app.utils.exceptions import BusinessException, ERR_NOT_FOUND, ERR_APPROVE_STATE, ERR_APPROVE_ROLE


# 节点常量
NODE_DATA = "DATA_APPROVAL"
NODE_TECH = "TECH_APPROVAL"
NODE_BIZ = "BIZ_APPROVAL"
NODE_PASSED = "PASSED"
NODE_REJECTED = "REJECTED"

# 节点 → 需要的角色编码
NODE_ROLE_MAP = {
    NODE_DATA: "data_approver",
    NODE_TECH: "tech_approver",
    NODE_BIZ: "biz_approver",
}

# 审批顺序（最后一个是 PASSED）
NODE_ORDER = [NODE_DATA, NODE_TECH, NODE_BIZ]


class ApprovalService(BaseService):
    MODULE = "approval"

    # ======================================================================
    # 查询
    # ======================================================================
    def list_tickets(self, status: Optional[str] = None,
                     current_user_id: Optional[int] = None,
                     show_my_pending: bool = False) -> List[ApprovalTicket]:
        stmt = select(ApprovalTicket).order_by(ApprovalTicket.created_at.desc())
        if status:
            stmt = stmt.where(ApprovalTicket.status == status)

        if show_my_pending and current_user_id is not None:
            # 只看当前用户能审批的工单（根据用户角色匹配节点）
            user_role_codes = self._get_user_role_codes(current_user_id)
            allowed_nodes = [node for node, role in NODE_ROLE_MAP.items() if role in user_role_codes]
            stmt = stmt.where(
                ApprovalTicket.current_node.in_(allowed_nodes),
                ApprovalTicket.status == "in_progress",
            )
        return self.db.execute(stmt).scalars().all()

    def get_ticket(self, ticket_id: int) -> Optional[ApprovalTicket]:
        return self.db.get(ApprovalTicket, ticket_id)

    # ======================================================================
    # 提交工单
    # ======================================================================
    def submit_ticket(self, target_id: int, ticket_type: str = "META_DATA",
                      title: Optional[str] = None, submitter_id: Optional[int] = None) -> ApprovalTicket:
        # 校验目标
        if ticket_type == "META_DATA":
            table = self.db.get(MetaTable, target_id)
            if not table:
                raise BusinessException(ERR_NOT_FOUND, f"目标表 {target_id} 不存在")
            # 不允许重复提交
            existing = self.db.execute(
                select(ApprovalTicket).where(
                    ApprovalTicket.ticket_type == "META_DATA",
                    ApprovalTicket.target_id == target_id,
                    ApprovalTicket.status.in_(["pending", "in_progress"]),
                )
            ).scalar_one_or_none()
            if existing:
                raise BusinessException(ERR_APPROVE_STATE, f"该表已有进行中的工单 #{existing.ticket_no}")

            auto_title = title or f"元数据接入审批：{table.table_name}"

        elif ticket_type == "TAG_TASK":  # V1.2 新增
            task = self.db.get(TagTask, target_id)
            if not task:
                raise BusinessException(ERR_NOT_FOUND, f"标签任务 {target_id} 不存在")
            # 不允许重复提交
            existing = self.db.execute(
                select(ApprovalTicket).where(
                    ApprovalTicket.ticket_type == "TAG_TASK",
                    ApprovalTicket.target_id == target_id,
                    ApprovalTicket.status.in_(["pending", "in_progress"]),
                )
            ).scalar_one_or_none()
            if existing:
                raise BusinessException(ERR_APPROVE_STATE, f"该标签任务已有进行中的工单 #{existing.ticket_no}")

            auto_title = title or f"标签任务审批：{task.task_name}"
            # 提交审批时把 tag_task 状态置为审批中
            task.status = "in_progress"

        else:
            raise BusinessException(ERR_APPROVE_STATE, f"不支持的工单类型: {ticket_type}")

        ticket_no = self._gen_ticket_no()
        ticket = ApprovalTicket(
            ticket_no=ticket_no,
            serial_no=ticket_no,  # V1.4.3: 同步 serial_no
            ticket_type=ticket_type,
            target_id=target_id,
            title=auto_title,
            submitter_id=submitter_id,
            current_node=NODE_DATA,  # 从第一个节点开始
            status="in_progress",
        )
        self.db.add(ticket)
        self.db.flush()

        # 记录 SUBMIT 日志
        self.db.add(ApprovalLog(
            ticket_id=ticket.id,
            node=NODE_DATA,
            approver_id=submitter_id,
            action="SUBMIT",
            comment=f"提交审批：{auto_title}",
        ))

        self.db.commit()
        self._log_info(f"提交工单 #{ticket_no}", submitter_id)
        return ticket

    # ======================================================================
    # 审批（通过 / 驳回）— 核心状态机
    # ======================================================================
    def approve(self, ticket_id: int, approver_id: int,
                comment: Optional[str] = None) -> ApprovalTicket:
        return self.transition(ticket_id, approver_id, action="approve", comment=comment)

    def reject(self, ticket_id: int, approver_id: int,
               comment: Optional[str] = None) -> ApprovalTicket:
        return self.transition(ticket_id, approver_id, action="reject", comment=comment)

    def transition(self, ticket_id: int, approver_id: int,
                   action: str, comment: Optional[str] = None) -> ApprovalTicket:
        """
        集中式状态机 —— 所有审批动作都通过此方法

        action: "approve" / "reject"
        """
        ticket = self.db.get(ApprovalTicket, ticket_id)
        if not ticket:
            raise BusinessException(ERR_NOT_FOUND, f"工单 {ticket_id} 不存在")

        if ticket.status not in ("in_progress",):
            raise BusinessException(ERR_APPROVE_STATE, f"工单当前状态 '{ticket.status}' 不可审批")

        current_node = ticket.current_node

        # 终态（PASSED / REJECTED）不可再审批
        if current_node in (NODE_PASSED, NODE_REJECTED):
            raise BusinessException(ERR_APPROVE_STATE, "工单已结束，不可再审批")

        # 角色权限校验（V1.3：admin 角色在所有节点都允许审批）
        required_role = NODE_ROLE_MAP.get(current_node)
        if required_role:
            user_role_codes = self._get_user_role_codes(approver_id)
            # admin 角色通吃所有节点审批
            is_admin = "admin" in user_role_codes
            has_node_role = required_role in user_role_codes
            if not is_admin and not has_node_role:
                raise BusinessException(
                    ERR_APPROVE_ROLE,
                    f"当前节点需要角色 '{required_role}' 才能审批",
                )

        # ---------- 状态流转 ----------
        if action == "approve":
            # 推进到下一个节点
            try:
                idx = NODE_ORDER.index(current_node)
            except ValueError:
                raise BusinessException(ERR_APPROVE_STATE, f"非法节点: {current_node}")

            if idx + 1 < len(NODE_ORDER):
                ticket.current_node = NODE_ORDER[idx + 1]
            else:
                # 已是最后一个节点 → PASSED
                ticket.current_node = NODE_PASSED
                ticket.status = "approved"

                # V1.2：联动更新关联对象状态
                if ticket.ticket_type == "META_DATA":
                    meta_service = None  # 避免循环 import
                    from app.services.metadata_service import MetadataService
                    meta_svc = MetadataService(self.db)
                    try:
                        meta_svc.set_table_status(ticket.target_id, "approved")
                    except Exception:
                        pass
                elif ticket.ticket_type == "TAG_TASK":
                    # 审批通过 → 标签任务可执行
                    task = self.db.get(TagTask, ticket.target_id)
                    if task:
                        task.status = "approved"

        elif action == "reject":
            # 驳回：停留在当前节点，工单状态置 rejected
            ticket.status = "rejected"
            # 节点不变（停留在当前）

            # V1.4.3 例外 (b)：元数据任务驳回时，meta_tables 置 rejected
            if ticket.ticket_type == "META_DATA":
                from app.services.metadata_service import MetadataService
                meta_svc = MetadataService(self.db)
                try:
                    meta_svc.set_table_status(ticket.target_id, "rejected")
                except Exception:
                    pass

            # V1.2：TAG_TASK 驳回 → 置为 rejected 不可执行
            if ticket.ticket_type == "TAG_TASK":
                task = self.db.get(TagTask, ticket.target_id)
                if task:
                    task.status = "rejected"

        else:
            raise BusinessException(ERR_APPROVE_STATE, f"非法审批动作: {action}")

        ticket.updated_at = datetime.utcnow()

        # 写审批日志
        self.db.add(ApprovalLog(
            ticket_id=ticket.id,
            node=current_node,  # 日志记录动作发生时的节点
            approver_id=approver_id,
            action=action.upper(),
            comment=comment or (f"{action} by approver"),
        ))

        self.db.commit()
        self._log_info(f"工单 #{ticket.ticket_no}: {action}@{current_node}", approver_id)
        return ticket

    # ======================================================================
    # 辅助
    # ======================================================================
    def _get_user_role_codes(self, user_id: int) -> List[str]:
        stmt = select(Role.code).join(UserRole).where(UserRole.user_id == user_id)
        return [row[0] for row in self.db.execute(stmt).all()]

    def _gen_ticket_no(self) -> str:
        """生成工单号：前缀 APP + YYYYMMDD + 001 递增 (V1.4.3)"""
        return self._gen_serial_no(ApprovalTicket, "APP")
