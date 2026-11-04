"""
tests/integration/test_api_approvals.py — 审批流程端到端测试
"""


class TestApprovalAPI:

    def _create_table_and_submit(self, client, auth_headers):
        # 创建表
        r = client.post("/api/metadata/tables", json={
            "table_name": "for_approval",
            "fields": [{"field_name": "id", "field_type": "INT", "is_primary_key": True}],
        }, headers=auth_headers)
        tid = r.json()["data"]["id"]

        # 提交工单
        r = client.post("/api/approvals/submit", json={"target_id": tid}, headers=auth_headers)
        return r.json()["data"]["id"]

    def test_full_approval_flow(self, client, auth_headers, dap_headers, tap_headers, bap_headers):
        """三级审批全部通过"""
        ticket_id = self._create_table_and_submit(client, auth_headers)

        # data 审批人 → 通过
        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK1"}, headers=dap_headers)
        assert r.json()["code"] == 0
        assert r.json()["data"]["current_node"] == "TECH_APPROVAL"

        # tech 审批人 → 通过
        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK2"}, headers=tap_headers)
        assert r.json()["data"]["current_node"] == "BIZ_APPROVAL"

        # biz 审批人 → 通过 → PASSED
        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK3"}, headers=bap_headers)
        assert r.json()["data"]["current_node"] == "PASSED"
        assert r.json()["data"]["status"] == "approved"

    def test_reject_flow(self, client, auth_headers, dap_headers):
        """驳回停留在当前节点"""
        ticket_id = self._create_table_and_submit(client, auth_headers)

        r = client.post(f"/api/approvals/{ticket_id}/reject",
                        json={"comment": "字段不全"}, headers=dap_headers)
        assert r.json()["data"]["current_node"] == "DATA_APPROVAL"
        assert r.json()["data"]["status"] == "rejected"

    def test_wrong_role_blocked(self, client, auth_headers, tap_headers):
        """错误角色 → 拒绝"""
        ticket_id = self._create_table_and_submit(client, auth_headers)

        # 技术审批人去审批 data 节点 → 拒绝
        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "x"}, headers=tap_headers)
        assert r.json()["code"] != 0  # 业务错误码

    def test_list_my_pending(self, client, auth_headers, dap_headers):
        """我的待办"""
        self._create_table_and_submit(client, auth_headers)
        r = client.get("/api/approvals?show_my_pending=true", headers=dap_headers)
        assert r.json()["code"] == 0
        assert len(r.json()["data"]) == 1
