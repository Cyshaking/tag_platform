"""
tests/integration/test_api_approvals.py — 审批流程端到端测试

V1.5: 元数据(META_DATA)不再需要审批，所有用例改用标签任务(TAG_TASK)
复用 _ensure_default_data() 种子数据（policy 主题 + sqlite 数据源）
"""


def _themes(client) -> dict:
    return {t["theme_code"]: t for t in client.get("/api/themes").json()["data"]}


def _enabled_ds(client) -> dict:
    return {d["ds_type"]: d for d in client.get("/api/datasources/enabled").json()["data"]}


def _create_tag_task_and_submit(client, auth_headers) -> int:
    """用种子 policy 主题 + sqlite 数据源 → 建字段配置标签任务 → 提交 TAG_TASK 审批"""
    themes = _themes(client)
    ds_map = _enabled_ds(client)

    # 用种子数据里的 policy 主题 + sqlite 数据源
    theme = themes.get("POLICY_THEME")
    ds = ds_map.get("sqlite")
    assert theme is not None, "种子数据未创建 POLICY_THEME"
    assert ds is not None, "种子数据未创建 sqlite 数据源"

    # 建字段配置标签任务（FIELD 模式，直接复用 policy 主题）
    r = client.post("/api/tag-tasks", json={
        "task_name": "approval_test_task",
        "task_mode": "FIELD",
        "theme_id": theme["id"],
        "tag_value_code": "APPR_TEST",
        "datasource_id": ds["id"],
        "field_config": {
            "config_tables": [theme["main_table_id"]],
            "conditions": [],
            "tag_value_code": "APPR_TEST",
        },
    }, headers=auth_headers)
    assert r.json()["code"] == 0, f"建标签任务失败: {r.json()}"
    task_id = r.json()["data"]["id"]

    # 提交审批（V1.5: META_DATA 已不可用）
    r = client.post("/api/approvals/submit", json={
        "target_id": task_id, "ticket_type": "TAG_TASK",
    }, headers=auth_headers)
    assert r.json()["code"] == 0, f"提交审批失败: {r.json()}"
    return r.json()["data"]["id"]


class TestApprovalAPI:

    def test_full_approval_flow(self, client, auth_headers, dap_headers, tap_headers, bap_headers):
        """三级审批全部通过"""
        ticket_id = _create_tag_task_and_submit(client, auth_headers)

        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK1"}, headers=dap_headers)
        assert r.json()["code"] == 0
        assert r.json()["data"]["current_node"] == "TECH_APPROVAL"

        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK2"}, headers=tap_headers)
        assert r.json()["data"]["current_node"] == "BIZ_APPROVAL"

        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "OK3"}, headers=bap_headers)
        assert r.json()["data"]["current_node"] == "PASSED"
        assert r.json()["data"]["status"] == "approved"

    def test_reject_flow(self, client, auth_headers, dap_headers):
        """驳回停留在当前节点"""
        ticket_id = _create_tag_task_and_submit(client, auth_headers)

        r = client.post(f"/api/approvals/{ticket_id}/reject",
                        json={"comment": "字段不全"}, headers=dap_headers)
        assert r.json()["data"]["current_node"] == "DATA_APPROVAL"
        assert r.json()["data"]["status"] == "rejected"

    def test_wrong_role_blocked(self, client, auth_headers, tap_headers):
        """错误角色 → 拒绝"""
        ticket_id = _create_tag_task_and_submit(client, auth_headers)

        r = client.post(f"/api/approvals/{ticket_id}/approve",
                        json={"comment": "x"}, headers=tap_headers)
        assert r.json()["code"] != 0  # 业务错误码

    def test_list_my_pending(self, client, auth_headers, dap_headers):
        """我的待办"""
        _create_tag_task_and_submit(client, auth_headers)
        r = client.get("/api/approvals?show_my_pending=true", headers=dap_headers)
        assert r.json()["code"] == 0
        assert len(r.json()["data"]) == 1

    # ========== V1.5 新增 ==========
    def test_metadata_submit_rejected(self, client, auth_headers):
        """V1.5: META_DATA 类型提交被直接拒绝"""
        # 用种子数据里已存在的表
        r = client.get("/api/metadata/tables", headers=auth_headers)
        tables = r.json()["data"]
        assert len(tables) > 0
        tid = tables[0]["id"]

        r = client.post("/api/approvals/submit", json={
            "target_id": tid, "ticket_type": "META_DATA",
        }, headers=auth_headers)
        assert r.json()["code"] != 0
        assert "无需审批" in r.json()["message"]

    def test_delete_approved_ticket(self, client, auth_headers, dap_headers, tap_headers, bap_headers):
        """V1.5: 已结束工单可以删除"""
        ticket_id = _create_tag_task_and_submit(client, auth_headers)

        # 走完三级审批 → approved
        client.post(f"/api/approvals/{ticket_id}/approve",
                    json={"comment": "ok"}, headers=dap_headers)
        client.post(f"/api/approvals/{ticket_id}/approve",
                    json={"comment": "ok"}, headers=tap_headers)
        client.post(f"/api/approvals/{ticket_id}/approve",
                    json={"comment": "ok"}, headers=bap_headers)

        # 删除
        r = client.delete(f"/api/approvals/{ticket_id}", headers=auth_headers)
        assert r.json()["code"] == 0

        # 已删除 → 查不到
        r = client.get(f"/api/approvals/{ticket_id}", headers=auth_headers)
        assert r.json()["code"] != 0

    def test_delete_in_progress_blocked(self, client, auth_headers):
        """V1.5: 进行中的工单不可删除"""
        ticket_id = _create_tag_task_and_submit(client, auth_headers)

        r = client.delete(f"/api/approvals/{ticket_id}", headers=auth_headers)
        assert r.json()["code"] != 0
        assert "不可删除" in r.json()["message"]
