"""
tests/integration/test_api_users.py — 用户/角色配置与身份切换（V1.1 #1）

覆盖：
- user:manage 权限门禁（admin 可访问，data_approver 403）
- 角色 CRUD、编码重复、预置角色保护、被引用禁止删除
- 用户 CRUD、用户名重复、禁用后无法登录、不能删除自己
- 演示身份切换白名单（admin/dap/tap/bap/normal）
"""
import pytest


def _role_id(client, headers, code: str) -> int:
    roles = client.get("/api/users/roles", headers=headers).json()["data"]
    return next(r["id"] for r in roles if r["code"] == code)


def _user(client, headers, username: str) -> dict:
    users = client.get("/api/users", headers=headers).json()["data"]
    return next(u for u in users if u["username"] == username)


class TestPermissionGate:

    def test_admin_can_manage_users(self, client, auth_headers):
        r = client.get("/api/users", headers=auth_headers).json()
        assert r["code"] == 0
        usernames = {u["username"] for u in r["data"]}
        assert {"admin", "dap", "tap", "bap", "normal"} <= usernames

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/users"),
        ("get", "/api/users/roles"),
    ])
    def test_non_admin_forbidden(self, client, dap_headers, method, path):
        r = getattr(client, method)(path, headers=dap_headers)
        assert r.status_code == 403
        assert r.json()["code"] == 403

    def test_anonymous_rejected(self, client):
        assert client.get("/api/users").status_code == 401


class TestRoleCrud:

    def test_create_update_delete(self, client, auth_headers):
        r = client.post("/api/users/roles", json={
            "code": "auditor", "name": "审计员",
            "description": "只读审计", "permissions": ["tag_task:view"],
        }, headers=auth_headers).json()
        assert r["code"] == 0
        role_id = r["data"]["id"]

        roles = client.get("/api/users/roles", headers=auth_headers).json()["data"]
        role = next(x for x in roles if x["id"] == role_id)
        assert role["permissions"] == ["tag_task:view"]

        r = client.put(f"/api/users/roles/{role_id}", json={
            "name": "高级审计员",
            "permissions": ["tag_task:view", "metadata:view"],
        }, headers=auth_headers).json()
        assert r["code"] == 0
        roles = client.get("/api/users/roles", headers=auth_headers).json()["data"]
        role = next(x for x in roles if x["id"] == role_id)
        assert role["name"] == "高级审计员"
        assert role["permissions"] == ["tag_task:view", "metadata:view"]

        r = client.delete(f"/api/users/roles/{role_id}", headers=auth_headers).json()
        assert r["code"] == 0
        assert role_id not in {x["id"] for x in
                               client.get("/api/users/roles", headers=auth_headers).json()["data"]}

    def test_duplicate_code_rejected(self, client, auth_headers):
        r = client.post("/api/users/roles", json={
            "code": "admin", "name": "重复管理员", "permissions": [],
        }, headers=auth_headers).json()
        assert r["code"] != 0

    def test_preset_role_not_deletable(self, client, auth_headers):
        admin_role_id = _role_id(client, auth_headers, "admin")
        r = client.delete(f"/api/users/roles/{admin_role_id}", headers=auth_headers).json()
        assert r["code"] != 0

    def test_role_in_use_not_deletable(self, client, auth_headers):
        role_id = client.post("/api/users/roles", json={
            "code": "in_use_role", "name": "被引用角色", "permissions": [],
        }, headers=auth_headers).json()["data"]["id"]

        r = client.post("/api/users", json={
            "username": "in_use_user", "password": "123456",
            "display_name": "被引用用户", "role_ids": [role_id],
        }, headers=auth_headers).json()
        assert r["code"] == 0

        r = client.delete(f"/api/users/roles/{role_id}", headers=auth_headers).json()
        assert r["code"] != 0


class TestUserCrud:

    def test_create_and_login(self, client, auth_headers):
        role_id = _role_id(client, auth_headers, "user")
        r = client.post("/api/users", json={
            "username": "alice", "password": "alice123",
            "display_name": "Alice", "role_ids": [role_id],
        }, headers=auth_headers).json()
        assert r["code"] == 0
        user_id = r["data"]["id"]

        created = _user(client, auth_headers, "alice")
        assert created["id"] == user_id
        assert created["display_name"] == "Alice"
        assert [x["code"] for x in created["roles"]] == ["user"]

        # 普通用户可登录，/me 返回其角色
        r = client.post("/api/auth/login", json={
            "username": "alice", "password": "alice123",
        }).json()
        assert r["code"] == 0
        me = client.get("/api/auth/me", headers={
            "Authorization": "Bearer " + r["data"]["access_token"]
        }).json()
        assert me["data"]["username"] == "alice"

    def test_duplicate_username_rejected(self, client, auth_headers):
        r = client.post("/api/users", json={
            "username": "admin", "password": "abcdef",
        }, headers=auth_headers).json()
        assert r["code"] != 0

    def test_short_password_rejected(self, client, auth_headers):
        r = client.post("/api/users", json={
            "username": "bob", "password": "123",
        }, headers=auth_headers).json()
        assert r["code"] == 40001

    def test_update_disable_blocks_login(self, client, auth_headers):
        user_id = client.post("/api/users", json={
            "username": "carol", "password": "carol123",
        }, headers=auth_headers).json()["data"]["id"]

        r = client.put(f"/api/users/{user_id}", json={
            "display_name": "Carol2", "is_active": False,
        }, headers=auth_headers).json()
        assert r["code"] == 0

        assert _user(client, auth_headers, "carol")["display_name"] == "Carol2"
        r = client.post("/api/auth/login", json={
            "username": "carol", "password": "carol123",
        }).json()
        assert r["code"] != 0

    def test_delete_self_rejected(self, client, auth_headers):
        admin_id = _user(client, auth_headers, "admin")["id"]
        r = client.delete(f"/api/users/{admin_id}", headers=auth_headers).json()
        assert r["code"] != 0

    def test_delete_other_user(self, client, auth_headers):
        user_id = client.post("/api/users", json={
            "username": "dave", "password": "dave123",
        }, headers=auth_headers).json()["data"]["id"]

        r = client.delete(f"/api/users/{user_id}", headers=auth_headers).json()
        assert r["code"] == 0
        assert "dave" not in {u["username"] for u in
                              client.get("/api/users", headers=auth_headers).json()["data"]}

    def test_update_unknown_user(self, client, auth_headers):
        r = client.put("/api/users/99999", json={"display_name": "X"},
                       headers=auth_headers).json()
        assert r["code"] != 0


class TestIdentitySwitch:

    @pytest.mark.parametrize("username,role_code", [
        ("admin", "admin"),
        ("dap", "data_approver"),
        ("tap", "tech_approver"),
        ("bap", "biz_approver"),
        ("normal", "user"),
    ])
    def test_switch_to_whitelisted(self, client, auth_headers, username, role_code):
        r = client.post("/api/auth/switch", json={"username": username},
                        headers=auth_headers).json()
        assert r["code"] == 0
        me = client.get("/api/auth/me", headers={
            "Authorization": "Bearer " + r["data"]["access_token"]
        }).json()
        assert me["data"]["username"] == username
        assert role_code in {x["code"] for x in me["data"]["roles"]}

    def test_switch_rejects_non_whitelisted(self, client, auth_headers):
        r = client.post("/api/auth/switch", json={"username": "hacker"},
                        headers=auth_headers).json()
        assert r["code"] != 0

    def test_switch_requires_login(self, client):
        assert client.post("/api/auth/switch", json={"username": "dap"}).status_code == 401
