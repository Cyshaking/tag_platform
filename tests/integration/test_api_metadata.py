"""
tests/integration/test_api_metadata.py — 元数据 API 集成测试
"""
from fastapi.testclient import TestClient


class TestMetadataAPI:

    def test_crud_flow(self, client: TestClient, auth_headers):
        """完整 CRUD 链路"""
        # CREATE
        r = client.post("/api/metadata/tables", json={
            "table_name": "products", "table_comment": "产品表",
            "fields": [
                {"field_name": "pid", "field_type": "INT", "is_primary_key": True, "ordinal_position": 1},
                {"field_name": "pname", "field_type": "VARCHAR(64)", "ordinal_position": 2},
            ],
        }, headers=auth_headers)
        assert r.json()["code"] == 0
        tid = r.json()["data"]["id"]

        # GET ONE
        r = client.get(f"/api/metadata/tables/{tid}", headers=auth_headers)
        assert r.json()["data"]["table_name"] == "products"
        assert len(r.json()["data"]["fields"]) == 2

        # LIST
        r = client.get("/api/metadata/tables", headers=auth_headers)
        assert r.json()["code"] == 0
        assert any(t["id"] == tid for t in r.json()["data"])

        # DELETE
        r = client.delete(f"/api/metadata/tables/{tid}", headers=auth_headers)
        assert r.json()["code"] == 0

        r = client.get(f"/api/metadata/tables/{tid}", headers=auth_headers)
        assert r.json()["code"] != 0  # 不存在了

    def test_duplicate_rejected(self, client, auth_headers):
        client.post("/api/metadata/tables", json={
            "table_name": "dup_t", "fields": [{"field_name": "id", "field_type": "INT", "is_primary_key": True}],
        }, headers=auth_headers)
        r = client.post("/api/metadata/tables", json={
            "table_name": "dup_t", "fields": [{"field_name": "id", "field_type": "INT", "is_primary_key": True}],
        }, headers=auth_headers)
        assert r.json()["code"] != 0

    def test_unauthorized_blocked(self, client):
        """无 token 调写接口 → 401"""
        r = client.post("/api/metadata/tables", json={
            "table_name": "no_auth_t",
            "fields": [{"field_name": "id", "field_type": "INT", "is_primary_key": True}],
        })
        # FastAPI BusinessException 全局处理返回 200 + code；
        # HTTPException(401) 返回 401
        if r.status_code == 200:
            assert r.json()["code"] == 40100 or r.json().get("code", 0) != 0
        else:
            assert r.status_code == 401

    def test_template_download(self, client, auth_headers):
        r = client.get("/api/metadata/template", headers=auth_headers)
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]

    def test_excel_import_success(self, client, auth_headers):
        """构造内存 Excel 上传"""
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws1 = wb.active; ws1.title = "表信息"
        ws1.append(["表名", "表中文名"]); ws1.append(["items", "商品表"])
        ws2 = wb.create_sheet("字段信息")
        ws2.append(["字段名", "字段类型", "字段中文名", "是否主键", "是否可空", "顺序"])
        ws2.append(["item_id", "INT", "ID", "Y", "N", 1])
        ws2.append(["name", "VARCHAR(64)", "名称", "N", "Y", 2])
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)

        r = client.post("/api/metadata/import",
                        files={"file": ("items.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        headers=auth_headers)
        j = r.json()
        assert j["code"] == 0, j
        assert j["data"]["field_count"] == 2

    def test_excel_import_bad_format(self, client, auth_headers):
        """上传非 Excel 文件 → 被拒绝"""
        r = client.post("/api/metadata/import",
                        files={"file": ("bad.txt", b"not excel", "text/plain")},
                        headers=auth_headers)
        assert r.json()["code"] != 0
