/* common.js — 通用 API 封装 + V1.3 权限收口 + 主题切换 */
const API_BASE = window.location.origin;

let _token = localStorage.getItem('token') || '';

function setToken(t) { _token = t; localStorage.setItem('token', t); }
function getToken() { return _token; }
function clearToken() { _token = ''; localStorage.removeItem('token'); }

async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const resp = await fetch(API_BASE + path, opts);
  const data = await resp.json();
  if (data.code && data.code !== 0 && data.code !== 200) {
    if (data.code === 40100) { clearToken(); window.location.href = '/static/index.html'; }
    let msg = data.message || '请求失败';
    if (data.data && Array.isArray(data.data) && data.data.length) {
      const details = data.data.map(d => String(d).replace(/^body\./, ''));
      msg += '：' + details.join('；');
    }
    throw new Error(msg);
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
    background:${isError ? 'var(--danger)' : 'var(--ok)'};color:#fff;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3)`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 2500);
}

function checkLogin() {
  if (!_token) { window.location.href = '/static/index.html'; return false; }
  return true;
}

function renderTable(headers, rows, containerId) {
  const el = document.getElementById(containerId);
  if (!rows || rows.length === 0) {
    el.innerHTML = '<p style="color:var(--ink-500);padding:20px;text-align:center;">暂无数据</p>';
    return;
  }
  let html = '<table>';
  html += '<tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr>';
  rows.forEach((r, i) => {
    html += '<tr style="background:' + (i % 2 ? '#fafbfc' : '#fff') + ';">' + r.map(c => `<td>${c ?? ''}</td>`).join('') + '</tr>';
  });
  html += '</table>';
  el.innerHTML = html;
}

// ========== V1.3 新增：角色判断工具 ==========
function currentRoleCodes() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || '{}');
    return (u.roles || []).map(r => r.code);
  } catch (e) { return []; }
}
function isAdmin() { return currentRoleCodes().includes('admin'); }

// ========== 身份切换（V1.3 只有 admin 可见）==========
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
  // V1.3: 只有 admin 才显示身份切换器
  if (!isAdmin()) return;

  const box = document.querySelector('.header .user');
  if (!box || document.getElementById('identitySelect')) return;

  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const current = user.username || 'admin';

  const sel = document.createElement('select');
  sel.id = 'identitySelect';
  sel.title = '演示环境身份切换（仅 admin 可用）';
  sel.style.cssText = 'margin-right:12px;padding:4px 8px;border-radius:4px;border:1px solid #cbd5e1;' +
    'background:#fff;color:#1f2937;font-size:13px;outline:none;cursor:pointer;' +
    'appearance:auto;';
  sel.innerHTML = DEMO_USERS.map(u =>
    `<option value="${u.username}" ${u.username === current ? 'selected' : ''} style="background:#fff;color:#1f2937;">${u.name}（${u.username}）</option>`
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

// ========== V1.3 新增：导航按角色隐藏 ==========
function hideUnauthorizedNav() {
  const codes = currentRoleCodes();
  const isAdminUser = codes.includes('admin');
  document.querySelectorAll('.nav a[data-perm]').forEach(a => {
    const perm = a.getAttribute('data-perm');
    if (perm === 'admin:only' && !isAdminUser) {
      a.style.display = 'none';
    }
  });
  // 如果当前页面本身需要 admin 权限，也跳转到 dashboard
  if (!isAdminUser && (location.pathname.endsWith('/users.html') || location.pathname.endsWith('users.html'))) {
    // 非 admin 直接访问 users.html → 自动跳回 dashboard
    // 但允许 users.html 的登录脚本先执行检查（showMsg 会显示）
    // 这里不强制跳转，让后端 API 返回 403 时由前端提示
  }
}

// ========== V1.3.1 审批待办角标（优先首页卡片） ==========
let _pendingInterval = null;
function fetchPendingCount() {
  apiGet('/api/approvals/count?show_my_pending=true').then(r => {
    const n = (r.data && r.data.pending) || 0;
    // V1.3.1: 优先更新首页卡片角标，兼容旧 nav 角标
    const targets = ['pendCardBadge', 'pendBadge'];
    targets.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      if (n > 0) {
        el.textContent = n > 99 ? '99+' : n;
        el.style.display = 'inline-block';
      } else {
        el.style.display = 'none';
      }
    });
  }).catch(() => { /* 未登录或无权限时静默 */ });
}

function startPendingBadge() {
  fetchPendingCount();
  if (_pendingInterval) clearInterval(_pendingInterval);
  _pendingInterval = setInterval(fetchPendingCount, 60000);
}

// ========== V1.3.1 主题切换（FAB 右下角悬浮设置按钮）==========
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

function initThemeSwitch() {
  // 应用已保存主题（V1.4.3: 侧栏风格 formal 作为默认）
  const savedTheme = localStorage.getItem('theme') || 'formal';
  applyTheme(savedTheme);

  if (document.getElementById('fabSettings')) return;

  // FAB 悬浮按钮容器（固定右下角）
  const fab = document.createElement('div');
  fab.id = 'fabSettings';
  fab.className = 'fab-menu';

  const btn = document.createElement('button');
  btn.className = 'fab-btn';
  btn.innerHTML = '⚙️';
  btn.title = '设置';

  // 下拉菜单（从按钮上方弹出）
  const menu = document.createElement('div');
  menu.className = 'fab-panel';
  menu.innerHTML = `
    <div class="fab-panel-title">切换主题</div>
    <div class="fab-item" data-theme="default">🎨 默认风格<br><span class="fab-item-desc">白导航 · 正式</span></div>
    <div class="fab-item" data-theme="formal">💼 侧栏风格<br><span class="fab-item-desc">深海军蓝 · 参考图</span></div>
  `;
  menu.querySelectorAll('.fab-item').forEach(item => {
    item.onclick = () => {
      applyTheme(item.getAttribute('data-theme'));
      showMsg('主题已切换');
      menu.classList.remove('show');
    };
  });

  btn.onclick = (e) => {
    e.stopPropagation();
    menu.classList.toggle('show');
  };

  // 点击外部关闭
  document.addEventListener('click', (e) => {
    if (menu.classList.contains('show') && !fab.contains(e.target)) {
      menu.classList.remove('show');
    }
  });

  fab.appendChild(btn);
  fab.appendChild(menu);
  document.body.appendChild(fab);
}

// ========== DOMContentLoaded 统一初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  initIdentitySwitcher();     // V1.3: admin-only
  hideUnauthorizedNav();      // V1.3: 非 admin 隐藏 admin:only 导航
  initThemeSwitch();          // V1.3: ⚙️ 设置按钮 + 主题切换
  startPendingBadge();        // V1.3: 待办角标 + 60s 刷新
});
