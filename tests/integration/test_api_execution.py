"""
tests/integration/test_api_execution.py — 标签任务 + 执行引擎 API
"""


class TestExecutionAPI:

    def test_tagtask_create_and_execute(self, client, auth_headers):
        """创建标签任务 → 执行 sqlite 引擎"""
        # 先准备元数据
        r = client.post("/api/metadata/tables", json={
            "table_name": "exec_t1",
            "fields": [
                {"field_name": "id", "field_type": "INT", "is_primary_key": True, "ordinal_position": 1},
                {"field_name": "label", "field_type": "VARCHAR(16)", "ordinal_position": 2},
            ],
        }, headers=auth_headers)
        table_id = r.json()["data"]["id"]

        # 取该表主键字段 ID（种子数据会占用更早的字段 ID，不能硬编码）
        r = client.get("/api/metadata/tables", headers=auth_headers)
        table = next(t for t in r.json()["data"] if t["id"] == table_id)
        field_id = next(f["id"] for f in table["fields"] if f["field_name"] == "id")

        # 再准备数据源
        r = client.post("/api/datasources", json={
            "name": "exec_sqlite", "ds_type": "sqlite",
            "config": {"db_path": ":memory:"}, "is_enabled": True,
        }, headers=auth_headers)
        ds_id = r.json()["data"]["id"]

        # 预览 SQL
        r = client.get(f"/api/tag-tasks/preview-sql?main_table_id={table_id}&main_field_id={field_id}&tag_value_code=X", headers=auth_headers)
        assert r.json()["code"] == 0
        assert "tag_value_code" in r.json()["data"]["sql"]

        # 创建标签任务
        r = client.post("/api/tag-tasks", json={
            "task_name": "exec_test", "business_theme": "test",
            "main_table_id": table_id, "main_field_id": field_id,
            "tag_value_code": "X", "datasource_id": ds_id,
        }, headers=auth_headers)
        assert r.json()["code"] == 0
        assert r.json()["data"]["generated_sql"]
        task_id = r.json()["data"]["id"]

        # V1.2：执行前需要审批通过
        # 提交审批
        r = client.post(f"/api/tag-tasks/{task_id}/submit-approval", headers=auth_headers)
        assert r.json()["code"] == 0
        ticket_id = r.json()["data"]["ticket_id"]

        # 三级审批：切换角色依次通过
        for role in ["dap", "tap", "bap"]:
            r = client.post("/api/auth/switch", headers=auth_headers, json={"username": role})
            token = r.json()["data"]["access_token"]
            role_headers = {"Authorization": f"Bearer {token}"}
            r = client.post(f"/api/approvals/{ticket_id}/approve", headers=role_headers, json={"comment": "ok"})
            assert r.json()["code"] == 0

        # 切回 admin（V1.7：身份切换仅允许 admin 发起，使用 admin 自身 token）
        r = client.post("/api/auth/switch", headers=auth_headers, json={"username": "admin"})
        token = r.json()["data"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 执行（sqlite :memory: 里表不存在 → 失败是预期）
        r = client.post("/api/execution/submit", json={"tag_task_id": task_id}, headers=auth_headers)
        assert r.json()["code"] == 0
        rec_id = r.json()["data"]["id"]

        # 查执行记录
        r = client.get(f"/api/execution/records/{rec_id}", headers=auth_headers)
        assert r.json()["code"] == 0
        assert r.json()["data"]["status"] in ("success", "failed")

    def test_execution_record_list(self, client, auth_headers):
        r = client.get("/api/execution/records", headers=auth_headers)
        assert r.json()["code"] == 0
        assert isinstance(r.json()["data"], list)
