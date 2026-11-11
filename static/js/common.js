/* common.js — TAG//OPS 控制台外壳
   保留原有 API 契约：token 存取、api 封装、权限导航、待办角标。
   仅调整视觉层与已失效的演示切换功能。 */

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
  if (resp.status === 401) {
    clearToken();
    window.location.href = '/static/index.html';
    throw new Error('登录已失效，请重新登录');
  }
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

/* 全局转义（页面内的同名函数会覆盖它，行为不受影响） */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showMsg(msg, isError) {
  const div = document.createElement('div');
  div.className = 'toast ' + (isError ? 'toast-error' : 'toast-ok');
  div.textContent = msg;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 2600);
}

function checkLogin() {
  if (!_token) { window.location.href = '/static/index.html'; return false; }
  return true;
}

function renderTable(headers, rows, containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  let html = '<div class="table-wrap"><table>';
  html += '<thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>' + r.map(c => `<td>${c ?? ''}</td>`).join('') + '</tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

// ========== 角色判断工具 ==========
function currentRoleCodes() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || '{}');
    return (u.roles || []).map(r => r.code);
  } catch (e) { return []; }
}

// ========== 导航按角色隐藏 ==========
function hideUnauthorizedNav() {
  const isAdminUser = currentRoleCodes().includes('admin');
  document.querySelectorAll('.nav a[data-perm]').forEach(a => {
    if (a.getAttribute('data-perm') === 'admin:only' && !isAdminUser) {
      a.style.display = 'none';
    }
  });
}

// ========== 导航激活态（按当前路径自动判定） ==========
function markActiveNav() {
  const here = (location.pathname.split('/').pop() || 'dashboard.html').toLowerCase();
  document.querySelectorAll('.nav a').forEach(a => {
    const href = (a.getAttribute('href') || '').split('/').pop().toLowerCase();
    if (href && href === here) a.classList.add('active');
  });
}

// ========== 顶栏时钟 / 在线指示灯 ==========
function initSysClock() {
  const box = document.querySelector('.header .user');
  if (!box || document.getElementById('sysClock')) return;
  const wrap = document.createElement('span');
  wrap.className = 'sys-status';
  wrap.innerHTML = '<span class="dot" aria-hidden="true"></span><span class="clock" id="sysClock">--:--:--</span>';
  box.insertBefore(wrap, box.firstChild);

  const tick = () => {
    const el = document.getElementById('sysClock');
    if (!el) return;
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    el.textContent = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  tick();
  setInterval(tick, 1000);
}

// ========== 审批待办角标 ==========
let _pendingInterval = null;
function fetchPendingCount() {
  apiGet('/api/approvals/count?show_my_pending=true').then(r => {
    const n = (r.data && r.data.pending) || 0;
    ['pendCardBadge', 'pendBadge'].forEach(id => {
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

// ========== 界面风格切换（ops / classic） ==========
const THEME_KEY = 'theme';
const THEMES = {
  ops:     { label: '工业数据面板', desc: 'OPS · 深石墨' },
  classic: { label: '经典海军蓝',   desc: 'CLASSIC · 浅灰' },
  clean:   { label: 'Linear 极简',  desc: 'CLEAN · 靛蓝' },
};

function currentTheme() {
  const t = localStorage.getItem(THEME_KEY) || 'ops';
  if (THEMES[t]) return t;
  return (t === 'formal' || t === 'default') ? 'classic' : 'ops';
}

function applyTheme(theme) {
  localStorage.setItem(THEME_KEY, THEMES[theme] ? theme : 'ops');
  location.reload();
}

function initThemeSwitch() {
  if (document.getElementById('themeFab')) return;
  const cur = currentTheme();
  const menu = document.createElement('div');
  menu.className = 'fab-menu';
  menu.id = 'themeFab';
  menu.innerHTML = `
    <div class="fab-panel" id="themePanel">
      <div class="fab-panel-title">界面风格 / THEME</div>
      ${Object.keys(THEMES).map(k => `
        <button type="button" class="fab-item${k === cur ? ' active' : ''}" data-theme-key="${k}">
          <span>${THEMES[k].label}<span class="fab-item-desc">${THEMES[k].desc}</span></span>
          <span class="tick">${k === cur ? '✓' : ''}</span>
        </button>`).join('')}
    </div>
    <button type="button" class="fab-btn" id="themeFabBtn" title="切换界面风格" aria-label="切换界面风格">◐</button>`;
  document.body.appendChild(menu);

  const panel = document.getElementById('themePanel');
  document.getElementById('themeFabBtn').addEventListener('click', e => {
    e.stopPropagation();
    panel.classList.toggle('show');
  });
  menu.querySelectorAll('.fab-item').forEach(btn => {
    btn.addEventListener('click', () => applyTheme(btn.dataset.themeKey));
  });
  document.addEventListener('click', e => {
    if (!menu.contains(e.target)) panel.classList.remove('show');
  });
}

// ========== DOMContentLoaded 统一初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  hideUnauthorizedNav();
  markActiveNav();
  initSysClock();
  initThemeSwitch();
  startPendingBadge();
});
