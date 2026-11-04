"""
tests/integration/test_api_themes.py — 业务主题接口（V1.1 #3）
"""
import pytest


def _themes(client):
    return {t["theme_code"]: t for t in client.get("/api/themes").json()["data"]}


def _tables(client, headers):
    return {t["table_name"]: t for t in
            client.get("/api/metadata/tables", headers=headers).json()["data"]}


def _sqlite_ds(client):
    dss = client.get("/api/datasources/enabled").json()["data"]
    return next(d for d in dss if d["ds_type"] == "sqlite")


class TestThemeRead:

    def test_seeded_theme_detail(self, client):
        theme = _themes(client)["POLICY_THEME"]
        r = client.get(f"/api/themes/{theme['id']}/tables").json()
        assert r["code"] == 0
        assert r["data"]["table_name"] == "policy"
        assert len(r["data"]["fields"]) == 14
        pk = [f for f in r["data"]["fields"] if f["is_primary_key"]]
        assert pk and pk[0]["field_name"] == "policy_id"

    def test_unknown_theme(self, client):
        r = client.get("/api/themes/99999").json()
        assert r["code"] != 0
        r = client.get("/api/themes/99999/tables").json()
        assert r["code"] != 0


class TestThemeWrite:

    def test_crud(self, client, auth_headers):
        tables = _tables(client, auth_headers)
        policy_table_id = tables["policy"]["id"]

        r = client.post("/api/themes", json={
            "theme_code": "CRUD_THEME", "theme_name": "CRUD 主题",
            "main_table_id": policy_table_id, "description": "测试",
        }, headers=auth_headers).json()
        assert r["code"] == 0
        theme_id = r["data"]["id"]

        # 编码重复
        r = client.post("/api/themes", json={
            "theme_code": "CRUD_THEME", "theme_name": "重复",
            "main_table_id": policy_table_id,
        }, headers=auth_headers).json()
        assert r["code"] != 0

        # 主题表不存在
        r = client.post("/api/themes", json={
            "theme_code": "BAD_THEME", "theme_name": "非法表",
            "main_table_id": 99999,
        }, headers=auth_headers).json()
        assert r["code"] != 0

        r = client.put(f"/api/themes/{theme_id}",
                       json={"theme_name": "CRUD 主题-改"}, headers=auth_headers).json()
        assert r["code"] == 0
        assert _themes(client)["CRUD_THEME"]["theme_name"] == "CRUD 主题-改"

        r = client.delete(f"/api/themes/{theme_id}", headers=auth_headers).json()
        assert r["code"] == 0
        assert "CRUD_THEME" not in _themes(client)

    def test_referenced_theme_protected(self, client, auth_headers):
        themes = _themes(client)
        tables = _tables(client, auth_headers)
        policy = themes["POLICY_THEME"]
        ds = _sqlite_ds(client)

        fields = {f["field_name"]: f["id"] for f in tables["policy"]["fields"]}
        r = client.post("/api/tag-tasks", json={
            "task_name": "引用主题的任务", "task_mode": "FIELD",
            "theme_id": policy["id"], "datasource_id": ds["id"],
            "field_config": {"config_tables": [tables["policy"]["id"]], "conditions": [
                {"logic": None, "field_id": fields["policy_status"],
                 "operator": "EQ", "value": "EFFECTIVE"},
            ]},
        }, headers=auth_headers).json()
        assert r["code"] == 0

        # 被引用时禁止改主题表
        r = client.put(f"/api/themes/{policy['id']}", json={
            "main_table_id": tables["person_customer"]["id"],
        }, headers=auth_headers).json()
        assert r["code"] != 0

        # 被引用时禁止删除
        r = client.delete(f"/api/themes/{policy['id']}", headers=auth_headers).json()
        assert r["code"] != 0

    @pytest.mark.parametrize("theme_code,main_table", [
        ("PERSON_THEME", "person_customer"),
        ("GROUP_THEME", "group_customer"),
        ("CASE_THEME", "policy_case"),
    ])
    def test_all_seed_themes_have_fields(self, client, theme_code, main_table):
        theme = _themes(client)[theme_code]
        r = client.get(f"/api/themes/{theme['id']}/tables").json()
        assert r["code"] == 0
        assert r["data"]["table_name"] == main_table
        assert len(r["data"]["fields"]) > 0
