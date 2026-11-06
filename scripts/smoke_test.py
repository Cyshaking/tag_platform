"""
API 冒烟测试 — V1.4.3 版（临时隔离库 + 失败真实退出 + 审批链完整走通）

改动点：
1. 启动前用 yaml.safe_load 精准改 database.sqlite_path 为临时库
2. 不再删除 data/tag_platform.db，跑完恢复 config.yaml，清理临时库
3. s11 用 PUT /api/metadata/tables/{id} 正确方法
4. 任何阶段失败 → sys.exit(1)
5. 审批链完整走：submit 工单 → admin 过三级审批 → 再执行
6. 所有测试用唯一标识名（避免上一轮残留）
"""
import json, sys, subprocess, time, urllib.request, os, shutil, atexit, traceback
from pathlib import Path

import yaml

BASE = 'http://127.0.0.1:8000'
_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ====== V1.4.3: 临时隔离库 ======
_config_path = os.path.join(_project_dir, 'config.yaml')
_config_backup = _config_path + '.smoke_bak'
_tmp_db = os.path.join(_project_dir, 'data', 'smoke_test_tmp.db')

# 1. 备份 config.yaml
shutil.copy(_config_path, _config_backup)
print(f"[init] config.yaml 备份 → {_config_backup}")

# 2. 用 yaml.safe_load 精准改 database.sqlite_path
with open(_config_path, 'r', encoding='utf-8') as f:
    _cfg = yaml.safe_load(f)

_old_path = _cfg.get('database', {}).get('sqlite_path', '')
_cfg['database']['sqlite_path'] = './data/smoke_test_tmp.db'

with open(_config_path, 'w', encoding='utf-8') as f:
    yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)

print(f"[init] database.sqlite_path: {_old_path} → ./data/smoke_test_tmp.db")

# 3. 清理临时库（不要碰真实库 data/tag_platform.db）
for _f in [_tmp_db, _tmp_db + '-wal', _tmp_db + '-shm']:
    if os.path.exists(_f):
        os.remove(_f)

# 4. atexit 保证 config.yaml 恢复 + 临时库清理
def _cleanup():
    try:
        if os.path.exists(_config_backup):
            shutil.copy(_config_backup, _config_path)
            os.remove(_config_backup)
            print(f"\n[cleanup] config.yaml 已恢复")
        for _f in [_tmp_db, _tmp_db + '-wal', _tmp_db + '-shm']:
            if os.path.exists(_f):
                os.remove(_f)
    except Exception as e:
        print(f"[cleanup] 清理失败: {e}")
atexit.register(_cleanup)

# ====== 启动服务 ======
proc = subprocess.Popen(
    [sys.executable, 'run.py'],
    cwd=_project_dir,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
)

# 实时打印 server 输出（让 debug print 可见）
import threading as _th
def _drain():
    try:
        for line in proc.stdout:
            print(f"[server] {line.rstrip()}")
    except Exception: pass
_drain_thread = _th.Thread(target=_drain, daemon=True)
_drain_thread.start()

print(f"[init] Starting server PID={proc.pid}...")
for _ in range(30):
    time.sleep(0.5)
    try:
        urllib.request.urlopen(BASE + '/docs', timeout=1)
        break
    except Exception:
        continue
else:
    print("[FATAL] 30 次轮询后服务仍未就绪")
    try:
        out = proc.stdout.read()
        print("=== server output tail ===")
        print(out[-3000:])
    except Exception:
        pass
    proc.kill()
    atexit.unregister(_cleanup)
    _cleanup()
    sys.exit(1)
print(f"[init] Server ready ✅\n")

# ====== HTTP 辅助 ======
def _urlopen(req):
    try:
        return urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        raise AssertionError(f"HTTP {e.code}: {body}") from None

def post(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', data=json.dumps(data).encode(), headers=headers, method='POST')
    return json.loads(_urlopen(req))

def put(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', data=json.dumps(data).encode(), headers=headers, method='PUT')
    return json.loads(_urlopen(req))

def delete(path, token=None):
    headers = {}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', headers=headers, method='DELETE')
    return json.loads(_urlopen(req))

def get(path, token=None):
    headers = {}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', headers=headers)
    return json.loads(_urlopen(req))

# ====== 测试框架 ======
passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        errors.append((name, traceback.format_exc()))
        failed += 1

# ====== 全局变量 ======
TS = str(int(time.time()))  # 时间戳防残留
token = None; table_id = None; table_fields = []; ds_id = None; tid = None; ticket_id = None; admin_id = None

def _get_table_fields(tid):
    """GET table 详情，返回字段列表 [{id, field_name, is_primary_key, ...}]"""
    r = get(f'/api/metadata/tables/{tid}', token)
    assert r['code'] == 0, r
    return r['data'].get('fields', [])

# ====== 测试用例 ======
def s1():  # 登录 admin
    global token
    r = post('/api/auth/login', {'username': 'admin', 'password': 'admin123'})
    assert r['code'] == 0, f"login failed: {r}"
    token = r['data']['access_token']

def s2():  # 创建元数据表（待审批）
    global table_id, table_fields
    r = post('/api/metadata/tables', {
        'table_name': f'smoke_user_{TS}', 'table_comment': '冒烟测试用户表',
        'fields': [
            {'field_name': 'user_id', 'field_type': 'BIGINT', 'is_primary_key': True, 'is_nullable': False, 'ordinal_position': 1},
            {'field_name': 'user_name', 'field_type': 'VARCHAR(64)', 'is_primary_key': False, 'is_nullable': True, 'ordinal_position': 2},
        ]
    }, token)
    assert r['code'] == 0, r
    table_id = int(r['data']['id'])
    # POST 不返回 status，GET 查一下
    table_fields = _get_table_fields(table_id)
    pk_field = next((f for f in table_fields if f.get('is_primary_key')), None)
    assert pk_field is not None, "smoke_user 表应有主键字段"
    print(f"    创建 smoke_user: table_id={table_id}, pk_field_id={pk_field['id']}")

def s3():  # 列元数据表
    r = get('/api/metadata/tables', token)
    assert r['code'] == 0 and len(r['data']) >= 1, r

def s4():  # 创建数据源
    global ds_id
    # V1.4.3: db_path 必须指向主库临时库（smoke_user 表存那里）
    # server 启动时 cwd=_project_dir，config.database.sqlite_path = ./data/smoke_test_tmp.db
    r = post('/api/datasources', {
        'name': f'smoke_sqlite_{TS}', 'ds_type': 'sqlite',
        'config': {'db_path': './data/smoke_test_tmp.db'}, 'is_enabled': True
    }, token)
    assert r['code'] == 0, r
    ds_id = int(r['data']['id'])

def s5():  # 测试数据源连接
    r = post('/api/datasources/test-connection', {'ds_type': 'sqlite', 'config': {'db_path': ':memory:'}})
    assert r['data']['success'] is True, r

def s6():  # Excel 模板下载
    assert urllib.request.urlopen(BASE + '/api/metadata/template').status == 200

def s7():  # 密码掩码
    r = post('/api/datasources', {
        'name': f'smoke_spark_{TS}', 'ds_type': 'spark',
        'config': {'thrift_url': 'jdbc:hive2://localhost:10015', 'password': 'secret'},
        'is_enabled': True
    }, token)
    mid = int(r['data']['id'])
    r = get(f'/api/datasources/{mid}', token)
    assert r['code'] == 0 and r['data']['config']['password'] == '******', f"密码未掩码: {r}"

def s8():  # 自动初始化角色
    r = get('/api/users/roles', token)
    codes = [x['code'] for x in r['data']]
    assert 'admin' in codes and 'data_approver' in codes, f"角色缺失: {codes}"

def s9():  # 提交元数据审批工单
    global ticket_id
    r = post('/api/approvals/submit', {'target_id': table_id, 'ticket_type': 'META_DATA'}, token)
    assert r['code'] == 0, r
    ticket_id = int(r['data']['id'])

def s10():  # admin 过三级审批
    r = post(f'/api/approvals/{ticket_id}/approve', {'comment': 'smoke data approve'}, token)
    assert r['code'] == 0 and r['data']['status'] in ('in_progress', 'approved'), f"第 1 级审批失败: {r}"
    r = post(f'/api/approvals/{ticket_id}/approve', {'comment': 'smoke tech approve'}, token)
    assert r['code'] == 0, f"第 2 级审批失败: {r}"
    r = post(f'/api/approvals/{ticket_id}/approve', {'comment': 'smoke biz approve'}, token)
    assert r['code'] == 0, f"第 3 级审批失败: {r}"
    # 最终应 approved
    r = get(f'/api/approvals/{ticket_id}', token)
    assert r['data']['status'] == 'approved', f"工单应已 approved: {r}"
    # 表状态也应 approved
    r = get(f'/api/metadata/tables/{table_id}', token)
    assert r['code'] == 0 and r['data']['status'] == 'approved', f"元数据表应已 approved: {r}"

def s11():  # V1.4.3 例外 a：已审批表变更 → 重置 pending
    r = put(f'/api/metadata/tables/{table_id}', {
        'table_comment': '已审批后改注释 → 应重置 pending',
        'fields': [
            {'field_name': 'user_id', 'field_type': 'BIGINT', 'is_primary_key': True, 'is_nullable': False, 'ordinal_position': 1},
            {'field_name': 'user_name', 'field_type': 'VARCHAR(128)', 'is_primary_key': False, 'is_nullable': True, 'ordinal_position': 2},
        ]
    }, token)
    assert r['code'] == 0, f"PUT 成功: {r}"
    # PUT 不返回 status，GET 查
    r_get = get(f'/api/metadata/tables/{table_id}', token)
    assert r_get['code'] == 0
    # 需要看 get 接口返回的数据结构里有没有 status
    status = r_get['data'].get('status') or r_get['data'].get('table', {}).get('status')
    assert status == 'pending', f"已审批表变更应重置为 pending，实际 status={status}"

def s12():  # V1.4.3 例外 c：admin 账号不可删除
    r = get('/api/users', token)
    admin_user = next((u for u in r['data'] if u.get('username') == 'admin'), None)
    assert admin_user is not None, "admin 用户不存在"
    # delete admin 应该被业务层拦截或 HTTP 层拦截
    try:
        delete(f'/api/users/{admin_user["id"]}', token)
        # 如果没抛异常，至少 admin 还在
    except Exception:
        pass  # 预期会失败
    r_check = get('/api/users', token)
    admin_still_there = any(u.get('username') == 'admin' for u in r_check['data'])
    assert admin_still_there, "admin 账号竟然被删了！"

def s13():  # 创建标签任务 + 完整审批链 + 执行
    global tid, table_fields
    # 先拿最新的主键 field_id（s11 PUT 后字段可能重建了）
    table_fields = _get_table_fields(table_id)
    pk_field = next((f for f in table_fields if f.get('is_primary_key')), None)
    assert pk_field is not None, "找不到主键字段"
    pk_field_id = pk_field['id']

    # V1.4.3: SqliteEngine 执行前必须物理建表（metadata 只是 ORM 记录，无物理 CREATE TABLE）
    # 用 httpx 发 SQL 到同一 sqlite 库
    import sqlite3
    _db_abs = os.path.join(_project_dir, 'data', 'smoke_test_tmp.db')
    _conn = sqlite3.connect(_db_abs)
    _cols = ', '.join([f'"{f["field_name"]}" {f["field_type"].upper()}' for f in table_fields])
    _conn.execute(f'CREATE TABLE IF NOT EXISTS "{f"smoke_user_{TS}"}" ({_cols})')
    _conn.execute(f'INSERT OR REPLACE INTO "{f"smoke_user_{TS}"}" ({",".join([f["field_name"] for f in table_fields])}) VALUES (1, "test")')
    _conn.commit(); _conn.close()
    print(f"    ✅ 物理建表 smoke_user_{TS} + INSERT 1 row")

    r = post('/api/tag-tasks', {
        'task_name': f'smoke_task_{TS}',
        'main_table_id': table_id, 'main_field_id': pk_field_id,
        'tag_value_code': 'vip', 'datasource_id': ds_id,
        'task_mode': 'FIELD',
        'field_config': {
            'tables': [table_id],
            'conditions': [{'table_id': table_id, 'field_name': pk_field['field_name'], 'op': 'EQ', 'value': '1'}],
        }
    }, token)
    assert r['code'] == 0 and r['data'].get('generated_sql'), f"创建标签任务失败: {r}"
    tid = int(r['data']['id'])
    # 提交标签任务审批 + 过三级
    r2 = post('/api/approvals/submit', {'target_id': tid, 'ticket_type': 'TAG_TASK'}, token)
    assert r2['code'] == 0, f"标签任务 submit 失败: {r2}"
    tid_ticket_id = int(r2['data']['id'])
    for _ in range(3):
        r3 = post(f'/api/approvals/{tid_ticket_id}/approve', {'comment': 'ok'}, token)
        assert r3['code'] == 0, f"标签任务审批失败: {r3}"
    # 执行
    r4 = post('/api/execution/submit', {'tag_task_id': tid}, token)
    assert r4['code'] == 0, f"执行失败: {r4}"
    assert r4['data']['status'] in ('success', 'running'), f"执行状态异常: {r4}"

# ====== 运行 ======
print()
test("1. Login admin", s1)
test("2. Create MetaTable (pending)", s2)
test("3. List MetaTables", s3)
test("4. Create sqlite Datasource", s4)
test("5. Test sqlite connection", s5)
test("6. Excel template download", s6)
test("7. Password masking", s7)
test("8. Auto-init roles", s8)
test("9. Submit META_DATA approval", s9)
test("10. Admin 3-step approve → table approved", s10)
test("11. Change approved table → reset pending (V1.4.3 a)", s11)
test("12. admin account protected from delete (V1.4.3 c)", s12)
test("13. TagTask create + full approve chain + execute", s13)

# ====== 汇总 ======
print(f"\n{'='*48}")
print(f"  PASSED: {passed}  |  FAILED: {failed}")
print(f"{'='*48}")
if errors:
    print("\n--- 失败详情 ---")
    for name, tb in errors:
        print(f"\n✗ {name}")
        print(tb)

print(f"\n[cleanup] Stopping server...")
try:
    proc.terminate()
    proc.wait(timeout=3)
except Exception:
    proc.kill()

sys.exit(0 if failed == 0 else 1)
