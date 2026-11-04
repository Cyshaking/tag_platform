/* common.js — 通用 API 封装 */
const API_BASE = window.location.origin;

let _token = localStorage.getItem('token') || '';

function setToken(t) {
  _token = t;
  localStorage.setItem('token', t);
}

function getToken() { return _token; }

function clearToken() {
  _token = '';
  localStorage.removeItem('token');
}

async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const resp = await fetch(API_BASE + path, opts);
  const data = await resp.json();
  if (data.code && data.code !== 0 && data.code !== 200) {
    if (data.code === 40100) { clearToken(); window.location.href = '/static/index.html'; }
    throw new Error(data.message || '请求失败');
  }
  return data;
}

async function apiGet(path) { return api('GET', path); }
async function apiPost(path, body) { return api('POST', path, body); }
async function apiPut(path, body) { return api('PUT', path, body); }
async function apiDelete(path) { return api('DELETE', path); }

function showMsg(msg, isError) {
  const div = document.createElement('div');
  div.textContent = msg;
  div.style.cssText = `position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:10px 20px;border-radius:4px;
    background:${isError ? '#e74c3c' : '#27ae60'};color:#fff;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3)`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 2500);
}

function checkLogin() {
  if (!_token) { window.location.href = '/static/index.html'; return false; }
  return true;
}

// ========== 表格渲染 ==========
function renderTable(headers, rows, containerId) {
  const el = document.getElementById(containerId);
  if (!rows || rows.length === 0) {
    el.innerHTML = '<p style="color:#888;padding:20px;text-align:center;">暂无数据</p>';
    return;
  }
  let html = '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:14px;">';
  html += '<tr style="background:#f0f4f8;">' + headers.map(h => `<th>${h}</th>`).join('') + '</tr>';
  rows.forEach((r, i) => {
    html += '<tr style="background:' + (i % 2 ? '#fafbfc' : '#fff') + ';">' + r.map(c => `<td>${c ?? ''}</td>`).join('') + '</tr>';
  });
  html += '</table>';
  el.innerHTML = html;
}

// ========== 演示身份切换（V1.1）==========
// 后端 config.yaml demo_switch 控制白名单；这里只在演示用户中选择，免密切换。
const DEMO_USERS = [
  { username: 'admin', name: '系统管理员' },
  { username: 'dap', name: '数据审批人' },
  { username: 'tap', name: '技术审批人' },
  { username: 'bap', name: '业务审批人' },
  { username: 'normal', name: '普通用户' },
];

async function switchIdentity(username) {
  const r = await apiPost('/api/auth/switch', { username });
  setToken(r.data.access_token);
  localStorage.setItem('user', JSON.stringify(r.data.user || {}));
  showMsg('已切换身份：' + (r.data.user && r.data.user.display_name || username));
  setTimeout(() => location.reload(), 500);
}

function initIdentitySwitcher() {
  const box = document.querySelector('.header .user');
  if (!box || document.getElementById('identitySelect')) return;

  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const current = user.username || 'admin';

  const sel = document.createElement('select');
  sel.id = 'identitySelect';
  sel.title = '演示环境身份切换';
  sel.style.cssText = 'margin-right:12px;padding:4px 8px;border-radius:4px;border:1px solid rgba(255,255,255,.7);' +
    'background:rgba(255,255,255,.16);color:#fff;font-size:13px;outline:none;cursor:pointer;';
  sel.innerHTML = DEMO_USERS.map(u =>
    `<option value="${u.username}" ${u.username === current ? 'selected' : ''}>${u.name}（${u.username}）</option>`
  ).join('');
  sel.onchange = () => {
    switchIdentity(sel.value).catch(err => {
      showMsg(err.message, true);
      sel.value = current;
    });
  };

  const anchor = document.getElementById('userName');
  if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sel, anchor);
  else box.insertBefore(sel, box.firstChild);
}

document.addEventListener('DOMContentLoaded', initIdentitySwitcher);
