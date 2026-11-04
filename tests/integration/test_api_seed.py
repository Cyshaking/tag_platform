"""
tests/integration/test_api_seed.py — 种子数据接口可见性验收（V1.1 #4）
"""
import sqlite3

from app.config import demo_data as demo_cfg


class TestSeedVisible:

    def test_four_themes(self, client):
        themes = client.get("/api/themes").json()["data"]
        assert {t["theme_code"] for t in themes} == {
            "POLICY_THEME", "PERSON_THEME", "GROUP_THEME", "CASE_THEME"
        }
        for t in themes:
            assert t["main_table_name"] in {
                "policy", "person_customer", "group_customer", "policy_case"
            }

    def test_five_tables_approved(self, client, auth_headers):
        tables = client.get("/api/metadata/tables", headers=auth_headers).json()["data"]
        target = {"policy", "person_customer", "group_customer",
                  "policy_customer_rel", "policy_case"}
        seeded = [t for t in tables if t["table_name"] in target]
        assert {t["table_name"] for t in seeded} == target
        assert all(t["status"] == "approved" for t in seeded)
        assert all(t["fields"] for t in seeded)

    def test_relations_and_enums(self, client):
        relations = client.get("/api/relations").json()["data"]
        assert len(relations) >= 3

        enums = client.get("/api/enums").json()["data"]
        assert len(enums) == 16
        assert {"EFFECTIVE", "PAID", "PERSON"} <= {e["enum_code"] for e in enums}

    def test_datasources(self, client):
        dss = client.get("/api/datasources/enabled").json()["data"]
        types = {d["ds_type"] for d in dss}
        assert {"sqlite", "spark"} <= types

    def test_physical_demo_database(self, client):
        """演示业务库含 5 张物理表及脱敏样例"""
        conn = sqlite3.connect(demo_cfg.sqlite_path())
        try:
            expected = {
                "policy": 3,
                "person_customer": 3,
                "group_customer": 2,
                "policy_customer_rel": 3,
                "policy_case": 2,
            }
            for table, count in expected.items():
                actual = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                assert actual == count, f"{table} 期望 {count} 行，实际 {actual}"
            # 样例手机号已脱敏
            mobile = conn.execute(
                'SELECT mobile_masked FROM person_customer LIMIT 1'
            ).fetchone()[0]
            assert "*" in mobile
        finally:
            conn.close()

    def test_seed_is_idempotent_at_app_level(self, client):
        from app.db.database import get_session_factory
        from app.db.seed_data import init_insurance_seed_data

        # 应用启动时已初始化，这里应直接返回 False
        assert init_insurance_seed_data(get_session_factory(), physical=True) is False
