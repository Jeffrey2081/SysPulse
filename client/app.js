/**
 * SysPulse Mobile Frontend Application
 * High-performance real-time telemetry, canvas graphs, updates, and tabs.
 */

// State Management
const state = {
  host: window.location.host || '127.0.0.1:8888',
  token: '',
  pin: '',
  connected: false,
  pollRate: 1.0,
  tempUnit: 'c',
  ws: null,
  reconnectTimer: null,
  pendingUpdates: [],
  selectedPowerAction: null,
  
  // History buffers for real-time graphs (up to 40 samples)
  history: {
    cpu: [],
    ram: [],
    netDown: [],
    netUp: [],
    diskRead: [],
    diskWrite: []
  }
};

const MAX_HISTORY = 40;

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  initUrlParams();
  initSettingsUI();
  initTabs();
  initPwa();
  connectWebSocket();
  initCanvasResize();
  checkUpdates();
});

// URL & Auth Handling
function getApiBase() {
  const scheme = window.location.protocol === 'https:' ? 'https:' : 'http:';
  return `${scheme}//${state.host}`;
}

function getWsBase() {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${state.host}`;
}

function initUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const host = params.get('host');
  const pin = params.get('pin');

  const defaultHost = (window.location.host && !window.location.protocol.startsWith('file')) 
    ? window.location.host 
    : '192.168.1.21:53317';

  const defaultToken = 'hCcnlEyvz_tLDlSMXn2l2mTimL5lE6iZ';
  const defaultPin = '284621';

  state.host = host || localStorage.getItem('syspulse_host') || defaultHost;
  state.token = token || localStorage.getItem('syspulse_token') || defaultToken;
  state.pin = pin || localStorage.getItem('syspulse_pin') || defaultPin;

  // Ensure default points to the live Wi-Fi port 53317
  if (state.host.includes('127.0.0.1') || state.host.endsWith(':8888')) {
    state.host = '192.168.1.21:53317';
  }

  localStorage.setItem('syspulse_token', state.token);
  localStorage.setItem('syspulse_host', state.host);
  localStorage.setItem('syspulse_pin', state.pin);
}

function initSettingsUI() {
  const hostInput = document.getElementById('cfgHostInput');
  const tokenInput = document.getElementById('cfgTokenInput');
  if (hostInput) hostInput.value = state.host;
  if (tokenInput) tokenInput.value = state.token;
}

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

  const targetPane = document.getElementById(tabId);
  if (targetPane) targetPane.classList.add('active');

  const targetTabBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  if (targetTabBtn) targetTabBtn.classList.add('active');

  // Trigger canvas resize and redraw on tab activation
  setTimeout(() => {
    resizeCanvases();
    redrawAllCharts();
  }, 40);
}

function initTabs() {
  // Listen for hash changes if any
  if (window.location.hash) {
    const hash = window.location.hash.substring(1);
    if (document.getElementById(hash)) {
      switchTab(hash);
    }
  }
}

// WebSocket Connection
let connectionAttempts = 0;
let connTimeout = null;

function connectWebSocket() {
  if (state.ws) {
    try { state.ws.close(); } catch (e) {}
  }

  const url = `${getWsBase()}/ws?token=${encodeURIComponent(state.token)}&pin=${encodeURIComponent(state.pin)}`;

  updateStatus(false, `Connecting (${state.host.split(':')[0]})...`);

  if (connTimeout) clearTimeout(connTimeout);
  connTimeout = setTimeout(() => {
    if (!state.connected && state.ws) {
      try { state.ws.close(); } catch (e) {}
    }
  }, 2500);

  try {
    state.ws = new WebSocket(url);
  } catch (err) {
    scheduleReconnect();
    return;
  }

  let lastPing = Date.now();

  state.ws.onopen = () => {
    if (connTimeout) clearTimeout(connTimeout);
    connectionAttempts = 0;
    updateStatus(true, 'Connected');
    // Request current polling rate
    state.ws.send(JSON.stringify({ interval: state.pollRate }));
  };

  state.ws.onmessage = (event) => {
    const now = Date.now();
    const latency = now - lastPing;
    lastPing = now;
    document.getElementById('latencyBadge').textContent = `${Math.min(latency, 999)} ms`;

    try {
      const data = JSON.parse(event.data);
      if (data.metrics) {
        handleMetricsUpdate(data.metrics);
      }
      if (data.update_status) {
        handleUpdateStatus(data.update_status);
      }
    } catch (e) {
      console.error('Error parsing telemetry payload:', e);
    }
  };

  state.ws.onclose = () => {
    updateStatus(false, 'Disconnected');
    scheduleReconnect();
  };

  state.ws.onerror = () => {
    updateStatus(false, 'Connection error');
  };
}

function scheduleReconnect() {
  if (state.reconnectTimer) return;
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    connectionAttempts++;

    // Ensure phone targets the direct Wi-Fi endpoint
    if (window.location.protocol.startsWith('file') && !state.host.endsWith(':53317')) {
      state.host = '192.168.1.21:53317';
      localStorage.setItem('syspulse_host', state.host);
      const hostInput = document.getElementById('cfgHostInput');
      if (hostInput) hostInput.value = state.host;
    }

    connectWebSocket();
  }, 2000);
}

function updateStatus(connected, text) {
  state.connected = connected;
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  if (connected) {
    dot.className = 'status-dot connected';
    txt.textContent = text || 'Live';
  } else {
    dot.className = 'status-dot disconnected';
    txt.textContent = text || 'Offline';
  }
}

// Telemetry Processing
function handleMetricsUpdate(m) {
  // --- 1. Host Info ---
  if (m.system) {
    document.getElementById('hostName').textContent = m.system.hostname;
    document.getElementById('hostKernel').textContent = `${m.system.os_name} • ${m.system.kernel}`;
    document.getElementById('hostUptime').textContent = m.system.uptime_formatted;
    document.getElementById('hostOsBadge').textContent = m.system.os_platform.toUpperCase();
  }

  // --- 2. CPU ---
  if (m.cpu) {
    const cpuVal = Math.round(m.cpu.percent);
    document.getElementById('cpuGaugeVal').textContent = cpuVal;
    setGaugeOffset('cpuGaugeFill', cpuVal);

    if (m.cpu.temperature_c !== null) {
      const tempDisplay = state.tempUnit === 'f' 
        ? `${Math.round(m.cpu.temperature_c * 9/5 + 32)} °F`
        : `${m.cpu.temperature_c} °C`;
      document.getElementById('cpuTempSubtitle').textContent = tempDisplay;
    } else {
      document.getElementById('cpuTempSubtitle').textContent = `${m.cpu.logical_cores} Cores`;
    }

    document.getElementById('graphsCpuVal').textContent = `${m.cpu.percent}%`;
    document.getElementById('graphsCpuModel').textContent = m.cpu.model;

    // Buffer for history
    pushHistory('cpu', m.cpu.percent);

    // Update Core Breakdown
    renderCores(m.cpu.per_core);
  }

  // --- 3. RAM ---
  if (m.memory) {
    const ramVal = Math.round(m.memory.percent);
    document.getElementById('ramGaugeVal').textContent = ramVal;
    setGaugeOffset('ramGaugeFill', ramVal);
    document.getElementById('ramUsedSubtitle').textContent = `${m.memory.used_gb} / ${m.memory.total_gb} GB`;

    document.getElementById('graphsRamVal').textContent = `${m.memory.percent}%`;
    document.getElementById('graphsRamSub').textContent = `${m.memory.used_gb} GB used of ${m.memory.total_gb} GB`;

    pushHistory('ram', m.memory.percent);
  }

  // --- 4. Storage ---
  if (m.storage) {
    const diskVal = Math.round(m.storage.percent);
    document.getElementById('diskGaugeVal').textContent = diskVal;
    setGaugeOffset('diskGaugeFill', diskVal);
    document.getElementById('diskFreeSubtitle').textContent = `${m.storage.free_gb} GB Free`;

    // Dashboard Storage Summary
    document.getElementById('storageSummaryFree').textContent = `${m.storage.free_gb} GB Free`;
    document.getElementById('storageSummaryBar').style.width = `${m.storage.percent}%`;
    document.getElementById('storageSummaryUsed').textContent = `${m.storage.used_gb} GB`;
    document.getElementById('storageSummaryFreeVal').textContent = `${m.storage.free_gb} GB`;
    document.getElementById('storageSummaryTotal').textContent = `${m.storage.total_gb} GB`;

    // Tab 3 Storage Stats
    document.getElementById('storageTabTotalBadge').textContent = `${m.storage.total_gb} GB Total`;
    document.getElementById('storageTabTotal').textContent = `${m.storage.total_gb} GB`;
    document.getElementById('storageTabUsed').textContent = `${m.storage.used_gb} GB`;
    document.getElementById('storageTabFree').textContent = `${m.storage.free_gb} GB`;

    // Render individual drives
    renderDrives(m.storage.drives);

    // Disk I/O history
    if (m.storage.io) {
      document.getElementById('graphsDiskRead').textContent = `${m.storage.io.read_kb_s} KB/s`;
      document.getElementById('graphsDiskWrite').textContent = `${m.storage.io.write_kb_s} KB/s`;
      pushHistory('diskRead', m.storage.io.read_kb_s);
      pushHistory('diskWrite', m.storage.io.write_kb_s);
    }
  }

  // --- 5. Network ---
  if (m.network) {
    const dl = m.network.download_kb_s;
    const ul = m.network.upload_kb_s;

    document.getElementById('graphsNetDl').textContent = formatSpeed(dl);
    document.getElementById('graphsNetUl').textContent = formatSpeed(ul);

    pushHistory('netDown', dl);
    pushHistory('netUp', ul);
  }

  // --- 6. Top Processes ---
  if (m.top_processes) {
    renderProcesses(m.top_processes);
  }

  // Redraw active charts
  redrawAllCharts();
}

function setGaugeOffset(elementId, percent) {
  const el = document.getElementById(elementId);
  if (!el) return;
  // Circumference = 2 * PI * 42 = 263.89
  const circumference = 264;
  const offset = circumference - (percent / 100) * circumference;
  el.style.strokeDashoffset = offset;
}

function pushHistory(key, val) {
  const buf = state.history[key];
  buf.push(val);
  if (buf.length > MAX_HISTORY) {
    buf.shift();
  }
}

function formatSpeed(kb) {
  if (kb >= 1024) {
    return `${(kb / 1024).toFixed(1)} MB/s`;
  }
  return `${Math.round(kb)} KB/s`;
}

// Render CPU Cores
function renderCores(perCore) {
  const container = document.getElementById('coresContainer');
  if (!container || !perCore) return;

  if (container.children.length !== perCore.length) {
    container.innerHTML = '';
    perCore.forEach((val, i) => {
      const pill = document.createElement('div');
      pill.className = 'core-pill';
      pill.innerHTML = `
        <div class="core-pill-title">C${i}</div>
        <div class="core-pill-val" id="coreVal_${i}">0%</div>
        <div class="core-mini-bar"><div class="core-mini-fill" id="coreBar_${i}" style="width: 0%"></div></div>
      `;
      container.appendChild(pill);
    });
  }

  perCore.forEach((val, i) => {
    const txt = document.getElementById(`coreVal_${i}`);
    const bar = document.getElementById(`coreBar_${i}`);
    if (txt) txt.textContent = `${Math.round(val)}%`;
    if (bar) bar.style.width = `${Math.min(val, 100)}%`;
  });
}

// Render Mounted Drive Partitions
function renderDrives(drives) {
  const container = document.getElementById('drivesList');
  if (!container || !drives) return;

  let html = '';
  drives.forEach(d => {
    let barColor = 'linear-gradient(90deg, #10b981, #38bdf8)';
    if (d.percent > 85) barColor = 'linear-gradient(90deg, #f59e0b, #ef4444)';
    else if (d.percent > 70) barColor = 'linear-gradient(90deg, #38bdf8, #f59e0b)';

    html += `
      <div class="drive-card">
        <div class="drive-header">
          <span class="drive-mount">${d.mountpoint}</span>
          <span class="drive-pct">${d.percent}%</span>
        </div>
        <div class="progress-bar-container">
          <div class="progress-bar-fill" style="width: ${d.percent}%; background: ${barColor};"></div>
        </div>
        <div class="drive-details">
          <span>${d.used_gb} GB used of ${d.total_gb} GB</span>
          <span class="text-green">${d.free_gb} GB free (${d.fstype})</span>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Render Process Table
function renderProcesses(procs) {
  const tbody = document.getElementById('topProcsBody');
  if (!tbody || !procs) return;

  let html = '';
  procs.forEach(p => {
    html += `
      <tr>
        <td style="font-weight: 600; color: #fff;">${escapeHtml(p.name)}</td>
        <td class="text-dim">${p.pid}</td>
        <td class="text-cyan">${p.cpu}%</td>
        <td class="text-purple">${p.ram}%</td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

// ================= MODERN CANVAS CHART ENGINE =================
function drawLineChart(canvasId, datasets, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  // Background horizontal grid lines
  const gridLines = 4;
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= gridLines; i++) {
    const y = (height / gridLines) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  // Draw datasets
  datasets.forEach(ds => {
    const data = ds.data;
    if (!data || data.length < 2) return;

    const maxVal = options.maxY || Math.max(...data, 10);
    const minVal = 0;
    const stepX = width / (MAX_HISTORY - 1);
    const startOffset = (MAX_HISTORY - data.length) * stepX;

    // Build Bezier Points
    const points = [];
    data.forEach((val, idx) => {
      const x = startOffset + idx * stepX;
      const normalized = Math.min(Math.max((val - minVal) / (maxVal - minVal), 0), 1);
      const y = height - (normalized * (height - 12)) - 6;
      points.push({ x, y });
    });

    // 1. Draw glowing gradient area fill
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(points[0].x, height);
    ctx.lineTo(points[0].x, points[0].y);

    for (let i = 0; i < points.length - 1; i++) {
      const cpX = (points[i].x + points[i + 1].x) / 2;
      ctx.bezierCurveTo(cpX, points[i].y, cpX, points[i + 1].y, points[i + 1].x, points[i + 1].y);
    }

    ctx.lineTo(points[points.length - 1].x, height);
    ctx.closePath();

    const areaGrad = ctx.createLinearGradient(0, 0, 0, height);
    areaGrad.addColorStop(0, ds.fillColor || 'rgba(56, 189, 248, 0.25)');
    areaGrad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');
    ctx.fillStyle = areaGrad;
    ctx.fill();
    ctx.restore();

    // 2. Draw smooth stroke curve
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);

    for (let i = 0; i < points.length - 1; i++) {
      const cpX = (points[i].x + points[i + 1].x) / 2;
      ctx.bezierCurveTo(cpX, points[i].y, cpX, points[i + 1].y, points[i + 1].x, points[i + 1].y);
    }

    ctx.strokeStyle = ds.strokeColor || '#38bdf8';
    ctx.lineWidth = ds.lineWidth || 2.5;
    ctx.shadowColor = ds.strokeColor || '#38bdf8';
    ctx.shadowBlur = 8;
    ctx.lineCap = 'round';
    ctx.stroke();
    ctx.restore();

    // 3. Current endpoint glowing dot
    const lastPt = points[points.length - 1];
    ctx.save();
    ctx.beginPath();
    ctx.arc(lastPt.x, lastPt.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.shadowColor = ds.strokeColor || '#38bdf8';
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.restore();
  });
}

function redrawAllCharts() {
  // 1. Dashboard Quick CPU & RAM
  drawLineChart('quickCpuCanvas', [
    { data: state.history.cpu, strokeColor: '#38bdf8', fillColor: 'rgba(56, 189, 248, 0.25)' },
    { data: state.history.ram, strokeColor: '#818cf8', fillColor: 'rgba(129, 140, 248, 0.15)' }
  ], { maxY: 100 });

  // 2. Graphs Tab - Detail CPU
  drawLineChart('detailCpuCanvas', [
    { data: state.history.cpu, strokeColor: '#38bdf8', fillColor: 'rgba(56, 189, 248, 0.3)' }
  ], { maxY: 100 });

  // 3. Graphs Tab - Detail RAM
  drawLineChart('detailRamCanvas', [
    { data: state.history.ram, strokeColor: '#818cf8', fillColor: 'rgba(129, 140, 248, 0.3)' }
  ], { maxY: 100 });

  // 4. Graphs Tab - Network
  const maxNet = Math.max(...state.history.netDown, ...state.history.netUp, 50);
  drawLineChart('detailNetCanvas', [
    { data: state.history.netDown, strokeColor: '#38bdf8', fillColor: 'rgba(56, 189, 248, 0.2)' },
    { data: state.history.netUp, strokeColor: '#f43f5e', fillColor: 'rgba(244, 63, 94, 0.2)' }
  ], { maxY: maxNet });

  // 5. Graphs Tab - Disk IO
  const maxDisk = Math.max(...state.history.diskRead, ...state.history.diskWrite, 50);
  drawLineChart('detailDiskCanvas', [
    { data: state.history.diskRead, strokeColor: '#10b981', fillColor: 'rgba(16, 185, 129, 0.2)' },
    { data: state.history.diskWrite, strokeColor: '#f59e0b', fillColor: 'rgba(245, 158, 11, 0.2)' }
  ], { maxY: maxDisk });
}

function resizeCanvases() {
  const dpr = window.devicePixelRatio || 1;
  document.querySelectorAll('.canvas-wrapper canvas').forEach(canvas => {
    const rect = canvas.parentElement.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    }
  });
}

function initCanvasResize() {
  function onResize() {
    resizeCanvases();
    redrawAllCharts();
  }
  window.addEventListener('resize', onResize);
  setTimeout(onResize, 100);
}

// ================= SYSTEM UPDATES =================
async function checkUpdates(force = false) {
  const url = `${getApiBase()}/api/updates?token=${encodeURIComponent(state.token)}&force=${force ? '1' : '0'}`;

  const btn = document.getElementById('checkUpdatesBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      renderUpdates(data);
    }
  } catch (err) {
    console.error('Error fetching updates:', err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderUpdates(data) {
  state.pendingUpdates = data.packages || [];
  const count = data.update_count || 0;

  // Header badges & banners
  const countPill = document.getElementById('updateCountPill');
  const dashBadge = document.getElementById('dashUpdateBadge');
  const navBadge = document.getElementById('navUpdateBadge');
  const dashTitle = document.getElementById('dashUpdateTitle');
  const pkgManagerText = document.getElementById('updatePkgManager');

  if (countPill) countPill.textContent = `${count} Updates`;
  if (dashBadge) dashBadge.textContent = count;
  if (dashTitle) {
    dashTitle.textContent = count > 0 
      ? `⚡ ${count} System Updates Available`
      : `System Up to Date`;
  }

  if (navBadge) {
    if (count > 0) {
      navBadge.style.display = 'block';
      navBadge.textContent = count > 99 ? '99+' : count;
    } else {
      navBadge.style.display = 'none';
    }
  }

  if (pkgManagerText) {
    pkgManagerText.textContent = `Package Manager: ${data.pkg_manager.toUpperCase()} (${data.os_type})`;
  }

  filterPackages();
}

function filterPackages() {
  const container = document.getElementById('packagesList');
  const query = (document.getElementById('pkgSearchInput')?.value || '').toLowerCase();
  if (!container) return;

  const filtered = state.pendingUpdates.filter(p => p.name.toLowerCase().includes(query));

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No matching packages found.</div>';
    return;
  }

  let html = '';
  filtered.forEach(p => {
    html += `
      <div class="pkg-item">
        <span class="pkg-name">${escapeHtml(p.name)}</span>
        <span class="pkg-ver">${escapeHtml(p.current_version)} → <span class="text-green">${escapeHtml(p.new_version)}</span></span>
      </div>
    `;
  });
  container.innerHTML = html;
}

function openUpdateModal() {
  openModal('updateModal');
}

async function executeSystemUpdate() {
  closeModal('updateModal');
  const password = document.getElementById('sudoPasswordInput')?.value || '';
  const url = `${getApiBase()}/api/updates/apply?token=${encodeURIComponent(state.token)}`;

  const termStatus = document.getElementById('terminalStatus');
  if (termStatus) {
    termStatus.className = 'terminal-status running';
    termStatus.textContent = 'RUNNING';
  }

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sudo_password: password })
    });
    const result = await res.json();
    appendTerminalLine(`[SYSPULSE] ${result.message || 'Update job submitted'}`);
  } catch (err) {
    appendTerminalLine(`[ERROR] Failed to start update: ${err.message}`);
  }
}

function handleUpdateStatus(status) {
  const termStatus = document.getElementById('terminalStatus');
  const termBody = document.getElementById('terminalBody');
  const triggerBtn = document.getElementById('triggerUpdateBtn');

  if (status.is_updating) {
    if (termStatus) {
      termStatus.className = 'terminal-status running';
      termStatus.textContent = 'UPDATING...';
    }
    if (triggerBtn) triggerBtn.disabled = true;
  } else {
    if (termStatus) {
      termStatus.className = 'terminal-status';
      termStatus.textContent = status.status.toUpperCase();
    }
    if (triggerBtn) triggerBtn.disabled = false;
  }

  // Update terminal logs
  if (termBody && status.logs && status.logs.length > 0) {
    termBody.innerHTML = status.logs.map(l => `<div class="terminal-line">${escapeHtml(l)}</div>`).join('');
    termBody.scrollTop = termBody.scrollHeight;
  }
}

function appendTerminalLine(text) {
  const termBody = document.getElementById('terminalBody');
  if (!termBody) return;
  const div = document.createElement('div');
  div.className = 'terminal-line';
  div.textContent = text;
  termBody.appendChild(div);
  termBody.scrollTop = termBody.scrollHeight;
}

// ================= POWER CONTROLS =================
function confirmPowerAction(action) {
  state.selectedPowerAction = action;
  const modal = document.getElementById('powerModal');
  const title = document.getElementById('powerModalTitle');
  const desc = document.getElementById('powerModalDesc');
  const btn = document.getElementById('powerModalConfirmBtn');

  if (action === 'lock') {
    title.textContent = 'Lock PC';
    desc.textContent = 'Are you sure you want to lock your PC screen?';
    btn.textContent = 'Lock Now';
    btn.className = 'btn btn-primary';
  } else if (action === 'reboot') {
    title.textContent = 'Reboot PC';
    desc.textContent = 'Are you sure you want to restart your computer? Unsaved work will be lost.';
    btn.textContent = 'Restart Now';
    btn.className = 'btn btn-danger';
  } else if (action === 'shutdown') {
    title.textContent = 'Shutdown PC';
    desc.textContent = 'Are you sure you want to turn off your computer? You will lose connection.';
    btn.textContent = 'Power Off';
    btn.className = 'btn btn-danger';
  }
  openModal('powerModal');
}

async function executePowerAction() {
  const action = state.selectedPowerAction;
  closeModal('powerModal');
  if (!action) return;

  const url = `${getApiBase()}/api/power?token=${encodeURIComponent(state.token)}`;

  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    alert(`Command '${action.toUpperCase()}' dispatched successfully to PC.`);
  } catch (err) {
    alert(`Failed to execute power command: ${err.message}`);
  }
}

// ================= PAIRING & SETTINGS =================
function openPairModal() {
  document.getElementById('modalHostInput').value = state.host;
  openModal('pairModal');
}

document.getElementById('openPairModalBtn')?.addEventListener('click', openPairModal);

async function submitPairingPin() {
  const pin = document.getElementById('modalPinInput').value.trim();
  const host = document.getElementById('modalHostInput').value.trim() || state.host;

  if (!pin) {
    alert('Please enter the 6-digit PIN shown in your PC terminal.');
    return;
  }

  const hostClean = host.startsWith('http') ? host : `http://${host}`;
  const url = `${hostClean}/api/pair?pin=${encodeURIComponent(pin)}`;

  try {
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      state.token = data.token;
      state.host = host;
      localStorage.setItem('syspulse_token', data.token);
      localStorage.setItem('syspulse_host', host);
      closeModal('pairModal');
      initSettingsUI();
      connectWebSocket();
      checkUpdates(true);
      alert(`Successfully paired with ${data.hostname}!`);
    } else {
      alert('Pairing failed: Invalid PIN. Check the code in the terminal.');
    }
  } catch (err) {
    alert(`Connection error: Unable to reach PC at ${host}. Ensure both devices are on the same Wi-Fi.`);
  }
}

function saveConnectionSettings() {
  const host = document.getElementById('cfgHostInput').value.trim();
  const token = document.getElementById('cfgTokenInput').value.trim();

  if (host) state.host = host;
  if (token) state.token = token;

  localStorage.setItem('syspulse_host', state.host);
  localStorage.setItem('syspulse_token', state.token);

  connectWebSocket();
  checkUpdates(true);
  alert('Connection settings saved.');
}

function changePollRate(rate) {
  state.pollRate = parseFloat(rate);
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ interval: state.pollRate }));
  }
}

function changeTempUnit(unit) {
  state.tempUnit = unit;
}

// QR Camera Scanner
let cameraStream = null;
function startCameraQrScanner() {
  const container = document.getElementById('cameraScannerContainer');
  const video = document.getElementById('qrVideo');
  if (!container || !video) return;

  container.style.display = 'block';

  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    .then(stream => {
      cameraStream = stream;
      video.srcObject = stream;
      video.play();
      scanQrLoop(video);
    })
    .catch(err => {
      alert('Unable to access camera: ' + err.message);
      container.style.display = 'none';
    });
}

function stopCameraQrScanner() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
  }
  const container = document.getElementById('cameraScannerContainer');
  if (container) container.style.display = 'none';
}

function scanQrLoop(video) {
  if (!cameraStream) return;
  // If BarcodeDetector is supported natively in modern mobile browsers
  if ('BarcodeDetector' in window) {
    const detector = new BarcodeDetector({ formats: ['qr_code'] });
    detector.detect(video).then(barcodes => {
      if (barcodes.length > 0) {
        const rawUrl = barcodes[0].rawValue;
        stopCameraQrScanner();
        handleScannedUrl(rawUrl);
      } else {
        requestAnimationFrame(() => scanQrLoop(video));
      }
    }).catch(() => requestAnimationFrame(() => scanQrLoop(video)));
  } else {
    // Canvas fallback or instructions
    requestAnimationFrame(() => scanQrLoop(video));
  }
}

function handleScannedUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    const token = url.searchParams.get('token');
    const host = url.host;
    if (token) {
      state.token = token;
      state.host = host;
      localStorage.setItem('syspulse_token', token);
      localStorage.setItem('syspulse_host', host);
      closeModal('pairModal');
      initSettingsUI();
      connectWebSocket();
      checkUpdates(true);
      alert('QR Code recognized! Paired successfully.');
    }
  } catch (e) {
    alert('Invalid QR Code contents: ' + rawUrl);
  }
}

// Modal Helpers
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('show');
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('show');
}

// PWA Install
let deferredPrompt = null;
function initPwa() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btn = document.getElementById('installPwaBtn');
    if (btn) btn.style.display = 'inline-flex';
  });
}

function installPwa() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => {
      deferredPrompt = null;
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>'"]/g, tag => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[tag] || tag));
}
