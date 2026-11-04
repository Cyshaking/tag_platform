"""API 冒烟测试 — 内置启动/停止服务"""
import json, sys, subprocess, time, urllib.request, os, shutil

BASE = 'http://127.0.0.1:8000'
_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 清理旧 DB（避免上次数据残留）
db_path = os.path.join(_project_dir, 'data', 'tag_platform.db')
for f in [db_path, db_path + '-wal', db_path + '-shm']:
    if os.path.exists(f):
        os.remove(f)
print(f"Cleaned old DB: {db_path}")

# ---- 启动服务 ----
proc = subprocess.Popen(
    [sys.executable, 'run.py'],
    cwd=_project_dir,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
print(f"Starting server PID={proc.pid}...")
for _ in range(30):
    time.sleep(0.5)
    try:
        urllib.request.urlopen(BASE + '/docs', timeout=1)
        break
    except Exception:
        continue
else:
    print("FAILED to start server")
    out = proc.stdout.read()
    print(out[-2000:])
    proc.kill()
    sys.exit(1)
print("Server ready ✅\n")

passed = 0; failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1

def post(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', data=json.dumps(data).encode(), headers=headers, method='POST')
    return json.loads(urllib.request.urlopen(req).read())

def get(path, token=None):
    headers = {}
    if token: headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', headers=headers)
    return json.loads(urllib.request.urlopen(req).read())

token = None; table_id = None; ds_id = None

def s1():
    global token
    r = post('/api/auth/login', {'username': 'admin', 'password': 'admin123'})
    assert r['code'] == 0
    token = r['data']['access_token']

def s2():
    global table_id
    r = post('/api/metadata/tables', {
        'table_name': 'smoke_user', 'table_comment': '冒烟测试用户表',
        'fields': [
            {'field_name': 'user_id', 'field_type': 'BIGINT', 'is_primary_key': True, 'is_nullable': False, 'ordinal_position': 1},
            {'field_name': 'user_name', 'field_type': 'VARCHAR(64)', 'is_primary_key': False, 'is_nullable': True, 'ordinal_position': 2},
        ]
    }, token)
    assert r['code'] == 0, r
    table_id = int(r['data']['id'])

def s3():
    r = get('/api/metadata/tables', token)
    assert r['code'] == 0 and len(r['data']) >= 1

def s4():
    r = get(f'/api/tag-tasks/preview-sql?main_table_id={table_id}&main_field_id=2&tag_value_code=vip', token)
    assert r['code'] == 0 and 'tag_value_code' in r['data']['sql'], r
    print(f"    SQL: {r['data']['sql'][:100]}")

def s5():
    global ds_id
    r = post('/api/datasources', {
        'name': 'smoke_sqlite', 'ds_type': 'sqlite', 'config': {'db_path': ':memory:'}, 'is_enabled': True
    }, token)
    assert r['code'] == 0, r
    ds_id = int(r['data']['id'])

def s6():
    r = post('/api/datasources/test-connection', {'ds_type': 'sqlite', 'config': {'db_path': ':memory:'}})
    assert r['data']['success'] is True, r

def s7():
    r = post('/api/approvals/submit', {'target_id': table_id, 'ticket_type': 'META_DATA'}, token)
    assert r['code'] == 0, r

def s8():
    r = post('/api/datasources', {
        'name': 'smoke_spark', 'ds_type': 'spark',
        'config': {'thrift_url': 'jdbc:hive2://localhost:10015', 'password': 'secret'},
        'is_enabled': True
    }, token)
    mid = int(r['data']['id'])
    r = get(f'/api/datasources/{mid}', token)
    assert r['data']['config']['password'] == '******', r

def s9():
    assert urllib.request.urlopen(BASE + '/api/metadata/template').status == 200

def s10():
    r = get('/api/users/roles', token)
    codes = [x['code'] for x in r['data']]
    assert 'admin' in codes and 'data_approver' in codes

def s11():
    r = post('/api/tag-tasks', {
        'task_name': 'smoke_task', 'business_theme': 'smoke',
        'main_table_id': table_id, 'main_field_id': 2,
        'tag_value_code': 'vip', 'datasource_id': ds_id
    }, token)
    assert r['code'] == 0 and r['data'].get('generated_sql')
    tid = int(r['data']['id'])
    r2 = post('/api/execution/submit', {'tag_task_id': tid}, token)
    assert r2['code'] == 0, r2
    print(f"    Execute status: {r2['data']['status']}")

# Run all
print()
test("1. Login", s1)
test("2. Create MetaTable", s2)
test("3. List MetaTables", s3)
test("4. Preview SQL generation", s4)
test("5. Create sqlite Datasource", s5)
test("6. Test sqlite connection", s6)
test("7. Submit approval ticket", s7)
test("8. Password masking", s8)
test("9. Download Excel template", s9)
test("10. Auto-init roles", s10)
test("11. TagTask create + Execute", s11)

print(f"\n{'='*40}")
print(f"  PASSED: {passed}  |  FAILED: {failed}")
print(f"{'='*40}")
print(f"\nStopping server...")
proc.terminate(); proc.wait(timeout=3)
sys.exit(0 if failed == 0 else 1)
