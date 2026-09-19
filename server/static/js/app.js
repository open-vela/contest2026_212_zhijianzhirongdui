/* ═══════════════════════════════════════════════════════════
   枢络 VelaMesh — Frontend Application
   Management (Admin) + Employee views with dual themes
   ═══════════════════════════════════════════════════════════ */

// ── State ────────────────────────────────────────────────
const API = '';
let token = localStorage.getItem('token') || null;
let user = null;
let currentView = 'admin';
let currentTab = { admin: 'dashboard', employee: 'home' };
let theme = localStorage.getItem('theme') || 'ios'; // ios | hyperos
let ws = null;
let personsCache = [];

// ── DOM Helpers ───────────────────────────────────────────
const $ = id => document.getElementById(id);
const api = async (path, opts = {}) => {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (res.status === 401 && path !== '/api/v1/auth/login') {
    doLogout(); return null;
  }
  return res.json();
};

// ── Login ─────────────────────────────────────────────────
async function doLogin() {
  const username = $('login-username').value.trim();
  const password = $('login-password').value.trim();
  const errEl = $('login-error');
  errEl.textContent = '';
  try {
    const res = await api('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (res.access_token) {
      token = res.access_token;
      user = res.user;
      localStorage.setItem('token', token);
      localStorage.setItem('user', JSON.stringify(user));
      enterApp();
    } else {
      errEl.textContent = res.detail || '登录失败';
    }
  } catch (e) {
    errEl.textContent = '无法连接服务器';
  }
}

function enterApp() {
  $('login-page').classList.add('hidden');
  $('app').classList.add('active');
  const avatar = $('user-avatar');
  avatar.textContent = (user.username || 'U')[0].toUpperCase();
  $('user-name').textContent = user.username;
  applyTheme();
  switchView('admin');
  loadDashboard();
  loadAllAdminData();
  connectWebSocket();
}

function doLogout() {
  token = null; user = null;
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  if (ws) { ws.close(); ws = null; }
  $('app').classList.remove('active');
  $('login-page').classList.remove('hidden');
}

// Check saved session on load
(function checkSession() {
  const saved = localStorage.getItem('user');
  if (token && saved) {
    try {
      user = JSON.parse(saved);
      api('/api/v1/auth/me').then(data => {
        if (data && data.id) {
          user = data;
          enterApp();
        } else { token = null; }
      }).catch(() => { token = null; });
    } catch { token = null; }
  }
})();

// ── View Switching (Admin ↔ Employee) ────────────────────
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === view));

  // Show/hide admin sidebar and content
  $('sidebar-admin').style.display = view === 'admin' ? 'block' : 'none';
  $('content-admin').style.display = view === 'admin' ? 'block' : 'none';

  // Show/hide employee content and bottom nav
  $('content-employee').style.display = view === 'employee' ? 'block' : 'none';
  $('emp-nav').style.display = view === 'employee' ? 'flex' : 'none';

  if (view === 'employee') {
    switchEmpTab(currentTab.employee);
    loadEmployeeData();
  } else {
    switchTab('admin', currentTab.admin);
  }
}

// ── Tab Switching (Admin) ────────────────────────────────
function switchTab(view, tab) {
  currentTab[view] = tab;
  document.querySelectorAll(`#sidebar-${view} .nav-item`).forEach(n => {
    n.classList.toggle('active', n.dataset.tab === tab);
  });
  document.querySelectorAll(`#content-${view} .tab-panel`).forEach(p => {
    p.classList.toggle('active', p.id === `panel-${view}-${tab}`);
  });
  // Load tab data on demand
  if (view === 'admin') {
    switch (tab) {
      case 'recognitions': loadRecognitions(); break;
      case 'persons': loadPersons(); break;
      case 'devices': loadDevices(); break;
      case 'visitors': loadVisitors(); break;
      case 'alerts': loadAlerts(); break;
      case 'settings': loadSettings(); break;
    }
  }
}

// ── Employee Tab Switching ───────────────────────────────
function switchEmpTab(tab) {
  currentTab.employee = tab;
  document.querySelectorAll('.emp-tab').forEach(t => t.classList.toggle('active', t.dataset.empTab === tab));
  document.querySelectorAll('#content-employee .tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `panel-emp-${tab}`);
  });
  if (tab === 'access') loadEmpAccess();
  if (tab === 'identity') loadEmpIdentity();
}

// ── Theme Toggle ──────────────────────────────────────────
function toggleTheme() {
  theme = theme === 'ios' ? 'hyperos' : 'ios';
  localStorage.setItem('theme', theme);
  applyTheme();
}

function applyTheme() {
  const html = document.documentElement;
  const btn = $('theme-btn');
  if (theme === 'hyperos') {
    html.setAttribute('data-theme', 'hyperos');
    btn.textContent = '🌙';
  } else {
    html.removeAttribute('data-theme');
    btn.textContent = '☀️';
  }
}
applyTheme();

// ── WebSocket ─────────────────────────────────────────────
function connectWebSocket() {
  if (ws) { ws.close(); }
  try {
    ws = new WebSocket(`ws://${location.host}/ws/events?token=${token}`);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'pong') return;
        if (msg.type === 'recognition' || msg.type === 'event') {
          addEventToStream(msg.data);
          loadDashboard(); // refresh stats
        }
      } catch {}
    };
    ws.onclose = () => { setTimeout(connectWebSocket, 5000); };
    ws.onopen = () => {
      // Send ping every 30s
      if (ws._pingInterval) clearInterval(ws._pingInterval);
      ws._pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, 30000);
    };
  } catch {}
}

// ── Dashboard ─────────────────────────────────────────────
async function loadDashboard() {
  try {
    const data = await api('/api/v1/realtime/overview');
    if (!data || !data.data) return;
    const d = data.data;
    $('dashboard-stats').innerHTML = `
      <div class="stat-card glass"><div class="label">在线设备</div><div class="value green">${d.online_devices}</div></div>
      <div class="stat-card glass"><div class="label">总人数</div><div class="value blue">${d.total_persons}</div></div>
      <div class="stat-card glass"><div class="label">今日事件</div><div class="value blue">${d.today_events}</div></div>
      <div class="stat-card glass"><div class="label">今日通过</div><div class="value green">${d.today_granted}</div></div>
      <div class="stat-card glass"><div class="label">今日告警</div><div class="value ${d.today_alerts > 0 ? 'red' : 'green'}">${d.today_alerts}</div></div>
    `;
    // Event stream
    const es = $('event-stream');
    if (d.recent_events && d.recent_events.length) {
      es.innerHTML = d.recent_events.map(e => `<div class="event-item">
        <div class="event-dot ${e.decision}"></div>
        <div class="event-info"><div class="name">${esc(e.person_name)}</div><div class="meta">${esc(e.node_id)} · 置信度 ${(e.fusion_conf*100).toFixed(0)}%</div></div>
        <div class="event-time">${fmtTime(e.created_at)}</div>
      </div>`).join('');
    } else {
      es.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><div>暂无事件</div></div>';
    }
    // Alert stream
    const as = $('alert-stream');
    if (d.recent_alerts && d.recent_alerts.length) {
      as.innerHTML = d.recent_alerts.map(a => `<div class="event-item">
        <div class="event-dot ${a.level === 'critical' ? 'denied' : a.level === 'warning' ? 'unknown' : 'granted'}"></div>
        <div class="event-info"><div class="name">${esc(a.title)}</div><div class="meta">${esc(a.level)}</div></div>
        <div class="event-time">${fmtTime(a.created_at)}</div>
      </div>`).join('');
    } else {
      as.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><div>无告警</div></div>';
    }
  } catch {}
}

function addEventToStream(data) {
  const es = $('event-stream');
  const first = es.querySelector('.empty-state, .loading');
  if (first) es.innerHTML = '';
  const item = document.createElement('div');
  item.className = 'event-item';
  item.innerHTML = `<div class="event-dot ${data.decision}"></div>
    <div class="event-info"><div class="name">${esc(data.person_name||'未知')}</div>
    <div class="meta">${esc(data.node_id||'')} · ${((data.fusion_conf||0)*100).toFixed(0)}%</div></div>
    <div class="event-time">刚刚</div>`;
  es.prepend(item);
  while (es.children.length > 50) es.lastChild.remove();
}

// ── Recognitions ─────────────────────────────────────────
async function loadRecognitions(page = 1) {
  try {
    const data = await api(`/api/v1/events?page=${page}&page_size=20`);
    if (!data || !data.data) { $('recognition-table').innerHTML = '<tr><td colspan="8"><div class="empty-state">暂无数据</div></td></tr>'; return; }
    $('recognition-table').innerHTML = data.data.map(e => `<tr>
      <td>${fmtTime(e.created_at)}</td>
      <td>${esc(e.person_name||'未知')}</td>
      <td>${esc(e.node_id||'')}</td>
      <td>${e.face_conf ? (e.face_conf*100).toFixed(0)+'%' : '-'}</td>
      <td>${e.gait_conf ? (e.gait_conf*100).toFixed(0)+'%' : '-'}</td>
      <td>${e.ble_conf ? (e.ble_conf*100).toFixed(0)+'%' : '-'}</td>
      <td>${e.fusion_conf ? (e.fusion_conf*100).toFixed(0)+'%' : '-'}</td>
      <td><span class="badge badge-${e.decision === 'granted' ? 'green' : e.decision === 'denied' ? 'red' : 'gray'}">${e.decision === 'granted' ? '✅通过' : e.decision === 'denied' ? '❌拒绝' : '❓未知'}</span></td>
    </tr>`).join('');
  } catch {}
}

// ── Persons ───────────────────────────────────────────────
async function loadPersons() {
  try {
    const data = await api('/api/v1/persons?page_size=50');
    if (!data || !data.data) { $('persons-table').innerHTML = '<tr><td colspan="7"><div class="empty-state">暂无人员</div></td></tr>'; return; }
    personsCache = data.data;
    $('persons-table').innerHTML = data.data.map(p => `<tr>
      <td>${p.id}</td>
      <td>${esc(p.name)}</td>
      <td>${esc(p.employee_id||'')}</td>
      <td>${esc(p.department||'')}</td>
      <td><span class="badge badge-${p.person_type === 'vip' ? 'orange' : p.person_type === 'contractor' ? 'blue' : 'gray'}">${esc(p.person_type||'employee')}</span></td>
      <td>${'⭐'.repeat(p.access_level||1)}</td>
      <td><button class="btn btn-sm btn-primary" onclick="editPerson(${p.id})">编辑</button> <button class="btn btn-sm btn-danger" onclick="deletePerson(${p.id})">删除</button></td>
    </tr>`).join('');
  } catch {}
}

function showPersonForm(person) {
  $('person-modal').classList.remove('hidden');
  $('person-form-title').textContent = person ? '编辑人员' : '新增人员';
  $('pf-id').value = person ? person.id : '';
  $('pf-name').value = person ? person.name : '';
  $('pf-employee_id').value = person ? (person.employee_id||'') : '';
  $('pf-department').value = person ? (person.department||'') : '';
  $('pf-person_type').value = person ? (person.person_type||'employee') : 'employee';
  $('pf-phone').value = person ? (person.phone||'') : '';
  $('pf-access_level').value = person ? (person.access_level||1) : 1;
}

function editPerson(id) {
  const p = personsCache.find(x => x.id === id);
  if (p) showPersonForm(p);
}

function closePersonForm() { $('person-modal').classList.add('hidden'); }

async function savePerson() {
  const id = $('pf-id').value;
  const body = {
    name: $('pf-name').value,
    employee_id: $('pf-employee_id').value,
    department: $('pf-department').value,
    person_type: $('pf-person_type').value,
    phone: $('pf-phone').value,
    access_level: parseInt($('pf-access_level').value) || 1,
  };
  try {
    if (id) {
      await api(`/api/v1/persons/${id}`, { method: 'PUT', body: JSON.stringify(body) });
    } else {
      await api('/api/v1/persons', { method: 'POST', body: JSON.stringify(body) });
    }
    closePersonForm();
    loadPersons();
    loadDashboard();
  } catch {}
}

async function deletePerson(id) {
  if (!confirm('确认删除该人员？')) return;
  await api(`/api/v1/persons/${id}`, { method: 'DELETE' });
  loadPersons();
  loadDashboard();
}

// ── Devices ───────────────────────────────────────────────
async function loadDevices() {
  try {
    const data = await api('/api/v1/devices');
    if (!data || !data.data) { $('devices-grid').innerHTML = '<div class="empty-state">暂无设备</div>'; return; }
    $('devices-grid').innerHTML = data.data.map(d => `<div class="glass-sm info-card">
      <div class="card-icon">${d.is_online ? '🟢' : '🔴'}</div>
      <div class="card-value">${esc(d.name)}</div>
      <div class="card-label">${esc(d.node_id||'')} · ${esc(d.location||'')}</div>
      <div style="margin-top:8px;font-size:12px;color:var(--ios-text-secondary);">
        ${d.device_type||''} ${d.last_seen ? '· 最后在线: '+fmtTime(d.last_seen) : ''}
      </div>
    </div>`).join('');
  } catch {}
}

// ── Visitors ──────────────────────────────────────────────
async function loadVisitors() {
  try {
    const data = await api('/api/v1/visitors');
    if (!data || !data.data) { $('visitors-table').innerHTML = '<tr><td colspan="6"><div class="empty-state">暂无访客</div></td></tr>'; return; }
    $('visitors-table').innerHTML = data.data.map(v => `<tr>
      <td>${esc(v.name)}</td>
      <td>${esc(v.phone||'')}</td>
      <td>${esc(v.purpose||'')}</td>
      <td><span class="badge badge-${v.status === 'checked_in' ? 'green' : v.status === 'approved' ? 'blue' : v.status === 'pending' ? 'orange' : v.status === 'denied' ? 'red' : 'gray'}">${statusLabel(v.status)}</span></td>
      <td>${v.expected_at ? fmtTime(v.expected_at) : '-'}</td>
      <td>
        ${v.status === 'pending' ? `<button class="btn btn-sm btn-primary" onclick="approveVisitor(${v.id})">审批</button>` : ''}
        ${v.status === 'approved' ? `<button class="btn btn-sm btn-primary" onclick="checkinVisitor(${v.id})">签到</button>` : ''}
      </td>
    </tr>`).join('');
  } catch {}
}

function statusLabel(s) {
  const map = { pending:'待审批', approved:'已批准', checked_in:'已签到', checked_out:'已签退', denied:'已拒绝' };
  return map[s]||s;
}

async function approveVisitor(id) {
  await api(`/api/v1/visitors/${id}/approve`, { method: 'POST' });
  loadVisitors();
}

async function checkinVisitor(id) {
  await api(`/api/v1/visitors/${id}/check-in`, { method: 'POST' });
  loadVisitors();
}

// ── Alerts ────────────────────────────────────────────────
async function loadAlerts() {
  try {
    const data = await api('/api/v1/alerts');
    if (!data || !data.data) { $('alerts-table').innerHTML = '<tr><td colspan="4"><div class="empty-state">暂无告警</div></td></tr>'; return; }
    $('alerts-table').innerHTML = data.data.map(a => `<tr>
      <td><span class="badge badge-${a.level === 'critical' ? 'red' : a.level === 'warning' ? 'orange' : 'blue'}">${esc(a.level)}</span></td>
      <td>${esc(a.title)}</td>
      <td>${fmtTime(a.created_at)}</td>
      <td>${!a.resolved_at ? `<button class="btn btn-sm btn-primary" onclick="resolveAlert(${a.id})">处理</button>` : '✅ 已处理'}</td>
    </tr>`).join('');
  } catch {}
}

async function resolveAlert(id) {
  await api(`/api/v1/alerts/${id}/resolve`, { method: 'PUT' });
  loadAlerts();
}

// ── Settings ──────────────────────────────────────────────
async function loadSettings() {
  try {
    // Users
    const users = await api('/api/v1/users');
    if (users && users.data) {
      $('users-table').innerHTML = users.data.map(u => `<tr>
        <td>${esc(u.username)}</td>
        <td>${esc(u.display_name||'')}</td>
        <td>${(u.roles||[]).map(r => `<span class="badge badge-blue">${esc(r)}</span>`).join(' ')}</td>
        <td>${u.is_superadmin ? '✅' : '❌'}</td>
      </tr>`).join('');
    }
    // Roles
    const roles = await api('/api/v1/roles');
    if (roles && roles.data) {
      $('roles-table').innerHTML = roles.data.map(r => `<tr>
        <td><strong>${esc(r.name)}</strong></td>
        <td>${(r.permissions||[]).map(p => `<span class="badge badge-gray">${esc(p)}</span>`).join(' ')}</td>
      </tr>`).join('');
    }
  } catch {}
}

// ── Employee Data ─────────────────────────────────────────
async function loadEmployeeData() {
  try {
    const overview = await api('/api/v1/realtime/overview');
    if (overview && overview.data) {
      const d = overview.data;
      const greeting = ['早上好', '下午好', '晚上好'];
      const h = new Date().getHours();
      const g = h < 12 ? 0 : h < 18 ? 1 : 2;
      $('emp-greeting').textContent = `${greeting[g]}，祝您工作愉快`;
      $('emp-stats').innerHTML = `
        <div class="stat-card glass"><div class="label">今日通行</div><div class="value blue">${d.today_events}</div></div>
        <div class="stat-card glass"><div class="label">在线设备</div><div class="value green">${d.online_devices}</div></div>
        <div class="stat-card glass"><div class="label">员工总数</div><div class="value blue">${d.total_persons}</div></div>
      `;
    }
    loadEmpIdentity();
  } catch {}
}

async function loadEmpIdentity() {
  try {
    // Find the current user's person record (first person as demo)
    const persons = await api('/api/v1/persons?page_size=5');
    if (persons && persons.data && persons.data.length) {
      const p = persons.data[0];
      $('emp-name').textContent = p.name;
      $('emp-dept').textContent = p.department || '—';
      $('emp-level').textContent = '⭐'.repeat(p.access_level||1);
    }
    $('emp-username').textContent = user ? user.username : 'admin';
  } catch {}
}

async function loadEmpAccess() {
  try {
    const data = await api('/api/v1/events/recent?limit=20');
    if (!data || !data.data) { $('emp-access-table').innerHTML = '<tr><td colspan="4"><div class="empty-state">暂无通行记录</div></td></tr>'; return; }
    $('emp-access-table').innerHTML = data.data.map(e => `<tr>
      <td>${fmtTime(e.created_at)}</td>
      <td>${esc(e.node_id||'')}</td>
      <td><span class="badge badge-${e.decision === 'granted' ? 'green' : e.decision === 'denied' ? 'red' : 'gray'}">${e.decision === 'granted' ? '✅通过' : e.decision === 'denied' ? '❌拒绝' : '❓未知'}</span></td>
      <td>${e.fusion_conf ? (e.fusion_conf*100).toFixed(0)+'%' : '-'}</td>
    </tr>`).join('');
  } catch {}
}

// ── Admin Data Loader (loads all non-visible admin tabs in background) ──
async function loadAllAdminData() {
  loadRecognitions();
  loadPersons();
  loadDevices();
  loadVisitors();
  loadAlerts();
  loadSettings();
}

// ── Utilities ─────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function fmtTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  } catch { return ts; }
}

// Auto-refresh dashboard every 30s
setInterval(loadDashboard, 30000);
