"""
tests/integration/test_api_tag_tasks_v11.py — 标签任务双模式接口（V1.1 #2）

覆盖：
- FIELD 模式：以主题表为主表 + 按表关系 JOIN + 条件算子生成 SQL
- SQL 直配模式：只读校验（sqlite 真实库 / spark mock）、创建与执行
- 非法输入：缺主题、空字段配置、非法模式、未知数据源
"""
import json

import pytest


def _themes(client) -> dict:
    return {t["theme_code"]: t for t in client.get("/api/themes").json()["data"]}


def _tables(client, headers) -> dict:
    return {t["table_name"]: t for t in
            client.get("/api/metadata/tables", headers=headers).json()["data"]}


def _field_ids(tables: dict) -> dict:
    return {(tname, f["field_name"]): f["id"]
            for tname, t in tables.items() for f in t["fields"]}


def _enabled_ds(client) -> dict:
    return {d["ds_type"]: d for d in client.get("/api/datasources/enabled").json()["data"]}


def _policy_field_config(client, headers) -> dict:
    """
    新结构：选 policy + person_customer 两张配置表，
    条件：policy.policy_status = EFFECTIVE
    """
    tmap = _tables(client, headers)
    fmap = _field_ids(tmap)
    return {
        "config_tables": [tmap["policy"]["id"], tmap["person_customer"]["id"]],
        "conditions": [
            {"logic": None,
             "field_id": fmap[("policy", "policy_status")],
             "operator": "EQ", "value": "EFFECTIVE"},
        ],
    }


class TestFieldMode:

    def test_create_uses_theme_table_and_join(self, client, auth_headers):
        theme = _themes(client)["POLICY_THEME"]
        ds = _enabled_ds(client)["sqlite"]

        body = {
            "task_name": "保单生效标签",
            "task_mode": "FIELD",
            "theme_id": theme["id"],
            "tag_value_code": "POLICY_EFFECTIVE",
            "datasource_id": ds["id"],
            "field_config": _policy_field_config(client, auth_headers),
        }
        r = client.post("/api/tag-tasks", json=body, headers=auth_headers).json()
        assert r["code"] == 0
        task_id = r["data"]["id"]
        sql = r["data"]["generated_sql"]

        # 外层 FROM = 主题表 policy a LEFT JOIN (...) b
        assert 'FROM "policy" a' in sql and 'LEFT JOIN (' in sql and ') b' in sql
        assert 'ON a."policy_id" = b."policy_id"' in sql
        # 内层 FROM = policy（第一张配置表），INNER JOIN person_customer
        inner = sql.split('LEFT JOIN (')[1].split('  ) b')[0]
        assert 'FROM "policy"' in inner
        assert 'INNER JOIN "person_customer"' in inner
        assert '"policy"."insured_id" = "person_customer"."customer_id"' in inner
        # CASE WHEN 条件链
        assert 'CASE WHEN' in inner and "'POLICY_EFFECTIVE'" in inner
        assert '"policy"."policy_status" = \'EFFECTIVE\'' in inner and "END AS tag_value_code" in inner

        detail = client.get(f"/api/tag-tasks/{task_id}").json()["data"]
        assert detail["task_mode"] == "FIELD"
        assert detail["theme_id"] == theme["id"]
        assert detail["main_table_id"] == theme["main_table_id"]
        assert detail["field_config_json"]
        assert json.loads(detail["field_config_json"])["tag_value_code"] == "POLICY_EFFECTIVE"

    def test_preview_sql_post_and_get(self, client, auth_headers):
        theme = _themes(client)["POLICY_THEME"]
        cfg = _policy_field_config(client, auth_headers)

        r = client.post("/api/tag-tasks/preview-sql", json={
            "task_mode": "FIELD", "theme_id": theme["id"],
            "tag_value_code": "PREVIEW", "field_config": cfg,
        }).json()
        assert r["code"] == 0
        assert 'FROM "policy" a' in r["data"]["sql"]
        assert "CASE WHEN" in r["data"]["sql"] and "'PREVIEW'" in r["data"]["sql"]

        # GET 版本（field_config_json 为 JSON 字符串）
        r = client.get("/api/tag-tasks/preview-sql", params={
            "task_mode": "FIELD", "theme_id": theme["id"],
            "tag_value_code": "PREVIEW2",
            "field_config_json": json.dumps(cfg, ensure_ascii=False),
        }).json()
        assert r["code"] == 0
        assert "CASE WHEN" in r["data"]["sql"] and "'PREVIEW2'" in r["data"]["sql"]

    def test_preview_without_field_config_rejected(self, client):
        theme = _themes(client)["POLICY_THEME"]
        r = client.post("/api/tag-tasks/preview-sql", json={
            "task_mode": "FIELD", "theme_id": theme["id"],
            "tag_value_code": "X",
        }).json()
        assert r["code"] != 0

    def test_create_without_theme_rejected(self, client, auth_headers):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks", json={
            "task_name": "缺主题字段任务", "task_mode": "FIELD",
            "datasource_id": ds["id"],
            "field_config": {"config_tables": [], "conditions": []},
        }, headers=auth_headers).json()
        assert r["code"] != 0

    def test_execute_generated_sql(self, client, auth_headers):
        theme = _themes(client)["POLICY_THEME"]
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks", json={
            "task_name": "字段模式执行", "task_mode": "FIELD",
            "theme_id": theme["id"], "datasource_id": ds["id"],
            "tag_value_code": "FIELD_EXEC",
            "field_config": _policy_field_config(client, auth_headers),
        }, headers=auth_headers).json()
        assert r["code"] == 0
        task_id = r["data"]["id"]

        r = client.post("/api/execution/submit",
                        json={"tag_task_id": task_id}, headers=auth_headers).json()
        assert r["code"] == 0
        rec = client.get(f"/api/execution/records/{r['data']['id']}").json()["data"]
        assert rec["status"] == "success"
        assert 'FROM "policy"' in rec["submitted_sql"]


class TestSQLMode:

    def test_create_and_execute_sql_mode(self, client, auth_headers):
        theme = _themes(client)["POLICY_THEME"]
        ds = _enabled_ds(client)["sqlite"]

        r = client.post("/api/tag-tasks", json={
            "task_name": "SQL 直配任务", "task_mode": "SQL",
            "theme_id": theme["id"], "datasource_id": ds["id"],
            "raw_sql": "SELECT policy_id, policy_no FROM policy "
                       "WHERE policy_status = 'EFFECTIVE';",
        }, headers=auth_headers).json()
        assert r["code"] == 0
        task_id = r["data"]["id"]
        # 规范化：去除尾部多余分号
        assert r["data"]["generated_sql"].endswith("'EFFECTIVE'")

        detail = client.get(f"/api/tag-tasks/{task_id}").json()["data"]
        assert detail["task_mode"] == "SQL"
        assert detail["raw_sql"] == detail["generated_sql"]

        r = client.post("/api/execution/submit",
                        json={"tag_task_id": task_id}, headers=auth_headers).json()
        assert r["code"] == 0
        rec = client.get(f"/api/execution/records/{r['data']['id']}").json()["data"]
        assert rec["status"] == "success"

    def test_create_sql_mode_rejects_write_statement(self, client, auth_headers):
        theme = _themes(client)["POLICY_THEME"]
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks", json={
            "task_name": "非法 SQL", "task_mode": "SQL",
            "theme_id": theme["id"], "datasource_id": ds["id"],
            "raw_sql": "DELETE FROM policy",
        }, headers=auth_headers).json()
        assert r["code"] != 0

    def test_create_sql_mode_requires_theme(self, client, auth_headers):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks", json={
            "task_name": "无主题 SQL", "task_mode": "SQL",
            "datasource_id": ds["id"],
            "raw_sql": "SELECT policy_id FROM policy",
        }, headers=auth_headers).json()
        assert r["code"] != 0

    @pytest.mark.parametrize("task_mode", ["BAD", "sql"])
    def test_invalid_task_mode_rejected(self, client, auth_headers, task_mode):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks", json={
            "task_name": "非法模式", "task_mode": task_mode,
            "datasource_id": ds["id"],
        }, headers=auth_headers)
        # Literal 校验失败 → 统一 40001 参数错误
        assert r.json()["code"] == 40001

    def test_validate_sql_readonly_passes_on_sqlite(self, client):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks/validate-sql", json={
            "sql": "SELECT policy_id, policy_no FROM policy",
            "datasource_id": ds["id"],
        }).json()
        assert r["code"] == 0
        assert r["data"]["valid"] is True
        assert r["data"]["normalized_sql"] == "SELECT policy_id, policy_no FROM policy"

    @pytest.mark.parametrize("sql", [
        "DELETE FROM policy",
        "UPDATE policy SET policy_status = 'X'",
        "SELECT 1; SELECT 2",
        "SELECT * FROM policy; DROP TABLE policy",
        "PRAGMA table_info(policy)",
        "  ",
    ])
    def test_validate_sql_rejects_non_readonly(self, client, sql):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks/validate-sql", json={
            "sql": sql, "datasource_id": ds["id"],
        }).json()
        assert r["code"] == 0
        assert r["data"]["valid"] is False
        assert r["data"]["message"]

    def test_validate_sql_detects_bad_column(self, client):
        ds = _enabled_ds(client)["sqlite"]
        r = client.post("/api/tag-tasks/validate-sql", json={
            "sql": "SELECT not_exist_col FROM policy",
            "datasource_id": ds["id"],
        }).json()
        assert r["code"] == 0
        assert r["data"]["valid"] is False

    def test_validate_sql_spark_mock_passes(self, client):
        ds = _enabled_ds(client)["spark"]
        r = client.post("/api/tag-tasks/validate-sql", json={
            "sql": "SELECT policy_id FROM policy",
            "datasource_id": ds["id"],
        }).json()
        assert r["code"] == 0
        assert r["data"]["valid"] is True
        assert "Mock" in r["data"]["message"]

    def test_validate_sql_unknown_datasource(self, client):
        r = client.post("/api/tag-tasks/validate-sql", json={
            "sql": "SELECT 1", "datasource_id": 99999,
        }).json()
        assert r["code"] != 0
