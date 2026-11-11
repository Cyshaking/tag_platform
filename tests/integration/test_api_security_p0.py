"""
tests/integration/test_api_security_p0.py — V1.7 P0 安全整改验收

覆盖：
1. 查询接口匿名访问 → 401
2. 写接口按权限码校验 → 403
3. 身份切换仅 admin 可调用 + 默认关闭
4. 密钥/演示开关配置基线
5. SQLite 数据源路径白名单
6. 执行阶段二次只读校验
"""
import yaml
from pathlib import Path


class TestAnonymousAccessDenied:
    """11.1 查询接口必须登录"""

    def test_metadata_read_requires_login(self, anon_client):
        assert anon_client.get("/api/metadata/tables").status_code == 401
        assert anon_client.get("/api/metadata/tables/1").status_code == 401
        assert anon_client.get("/api/metadata/template").status_code == 401

    def test_datasource_read_requires_login(self, anon_client):
        assert anon_client.get("/api/datasources").status_code == 401
        assert anon_client.get("/api/datasources/enabled").status_code == 401
        assert anon_client.get("/api/datasources/1").status_code == 401

    def test_datasource_test_connection_requires_login(self, anon_client):
        r = anon_client.post("/api/datasources/test-connection", json={
            "ds_type": "sqlite", "config": {"db_path": ":memory:"},
        })
        assert r.status_code == 401

    def test_task_and_theme_read_requires_login(self, anon_client):
        assert anon_client.get("/api/tag-tasks").status_code == 401
        assert anon_client.get("/api/themes").status_code == 401
        assert anon_client.get("/api/relations").status_code == 401
        assert anon_client.get("/api/enums").status_code == 401

    def test_approval_and_execution_read_requires_login(self, anon_client):
        assert anon_client.get("/api/approvals").status_code == 401
        assert anon_client.get("/api/approvals/1").status_code == 401
        assert anon_client.get("/api/approvals/count").status_code == 401
        assert anon_client.get("/api/execution/records").status_code == 401
        assert anon_client.get("/api/execution/records/1").status_code == 401


class TestWriteRequiresPermission:
    """11.1 写接口按权限码校验（dap 无 tag_task/datasource/theme 写权限）"""

    def test_task_write_forbidden_without_permission(self, client, dap_headers):
        r = client.post("/api/tag-tasks", json={
            "task_name": "x", "business_theme": "x", "main_table_id": 1,
            "main_field_id": 1, "tag_value_code": "X", "datasource_id": 1,
        }, headers=dap_headers)
        assert r.status_code == 403

    def test_datasource_write_forbidden_without_permission(self, client, dap_headers):
        r = client.post("/api/datasources", json={
            "name": "dap_ds", "ds_type": "sqlite", "config": {"db_path": ":memory:"},
        }, headers=dap_headers)
        assert r.status_code == 403


class TestIdentitySwitch:
    """11.2 身份切换收敛"""

    def test_non_admin_switch_forbidden(self, client, dap_headers):
        r = client.post("/api/auth/switch", json={"username": "admin"}, headers=dap_headers)
        assert r.status_code == 403

    def test_admin_switch_allowed(self, client, auth_headers):
        r = client.post("/api/auth/switch", json={"username": "dap"}, headers=auth_headers)
        assert r.json()["code"] == 0

    def test_demo_switch_disabled_by_default_in_config(self):
        """config.yaml 生产基线：demo_switch.enabled 必须为 false"""
        raw = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
        assert raw["demo_switch"]["enabled"] is False

    def test_switch_rejected_when_disabled(self, client, auth_headers, monkeypatch):
        from app.config import DemoSwitchConfig
        monkeypatch.setattr(DemoSwitchConfig, "enabled", False)
        r = client.post("/api/auth/switch", json={"username": "dap"}, headers=auth_headers)
        assert r.json()["code"] != 0


class TestConfigSecurity:
    """11.3 配置与口令安全"""

    def test_secret_key_not_placeholder(self):
        """占位密钥会被替换为进程内随机密钥，长度必然 >= 32"""
        from app.config import AppConfig
        assert len(AppConfig.secret_key) >= 32
        assert "change-me" not in AppConfig.secret_key.lower()


class TestSqlitePathWhitelist:
    """11.4 SQLite 数据源路径白名单"""

    def test_platform_db_rejected(self, client, auth_headers):
        r = client.post("/api/datasources", json={
            "name": "evil_main_db", "ds_type": "sqlite",
            "config": {"db_path": "data/tag_platform.db"},
        }, headers=auth_headers)
        assert r.json()["code"] != 0

    def test_outside_data_dir_rejected(self, client, auth_headers):
        r = client.post("/api/datasources", json={
            "name": "evil_tmp_db", "ds_type": "sqlite",
            "config": {"db_path": "/tmp/evil.db"},
        }, headers=auth_headers)
        assert r.json()["code"] != 0

    def test_test_connection_outside_rejected(self, client, auth_headers):
        r = client.post("/api/datasources/test-connection", json={
            "ds_type": "sqlite", "config": {"db_path": "/tmp/evil.db"},
        }, headers=auth_headers)
        assert r.json()["data"]["success"] is False


class TestExecutionReadonlyGuard:
    """11.4 执行阶段二次只读校验"""

    def _make_approved_task_with_sql(self, client, auth_headers, sql: str) -> int:
        """直接落库构造一个 approved 的标签任务，绕过生成 SQL 的路径"""
        from app.db.database import get_session_factory
        from app.db.models.tag_task import TagTask

        session = get_session_factory()()
        try:
            task = TagTask(
                task_name="p0_guard_task",
                task_mode="SQL",
                business_theme="p0_guard",
                main_table_id=1,
                main_field_id=1,
                tag_value_code="X",
                raw_sql=sql,
                generated_sql=sql,
                status="approved",
                datasource_id=1,
            )
            task.serial_no = "TASK-P0-GUARD"
            session.add(task)
            session.commit()
            session.refresh(task)
            return task.id
        finally:
            session.close()

    def test_write_sql_rejected_at_execution(self, client, auth_headers):
        # 先建一个 sqlite 数据源（内存库）供任务引用
        r = client.post("/api/datasources", json={
            "name": "p0_exec_ds", "ds_type": "sqlite",
            "config": {"db_path": ":memory:"},
        }, headers=auth_headers)
        ds_id = r.json()["data"]["id"]

        task_id = self._make_approved_task_with_sql(
            client, auth_headers, "DELETE FROM policy"
        )
        r = client.post("/api/execution/submit", json={
            "tag_task_id": task_id, "datasource_id": ds_id,
        }, headers=auth_headers)
        assert r.json()["code"] != 0
        assert "只读" in r.json().get("message", "") or "禁止" in r.json().get("message", "")
