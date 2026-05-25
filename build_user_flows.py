"""
build_user_flows.py  (v2)
-------------------------
v2 changes:
  - Timeline (Gantt) view added — Y axis = thread, X axis = time
  - Detail panel now shows duration & cache_key
  - View toggle at top: PARTICLES / TIMELINE (same canvas, two modes)

Usage in Jupyter:
    exec(open('build_user_flows.py').read())
    build_user_flows(df, 'user_flows.html')
"""

import json
import pandas as pd


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>User Flows</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0a0c; --bg-2: #14151a; --line: #26282f;
    --text: #f5f1e8; --text-muted: #8b8680; --text-dim: #4a4944;
    --amber: #e8a04a; --cyan: #5ec0c0; --red: #d96060;
  }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: var(--bg); color: var(--text);
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
  }
  #canvas { position: fixed; inset: 0; cursor: crosshair; }

  .hud { position: fixed; top: 24px; left: 28px; z-index: 5; pointer-events: none; }
  .hud h1 { font-family: 'Fraunces', serif; font-weight: 300; font-size: 22px; letter-spacing: -0.01em; margin-bottom: 4px; }
  .hud .sub { font-size: 11px; color: var(--text-muted); letter-spacing: 0.1em; }

  .view-toggle {
    position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
    z-index: 6; display: flex; background: var(--bg-2);
    border: 1px solid var(--line);
  }
  .view-toggle button {
    background: transparent; border: none; color: var(--text-muted);
    font-family: inherit; font-size: 10px; letter-spacing: 0.25em;
    padding: 9px 18px; cursor: pointer;
    transition: color 0.2s, background 0.2s;
  }
  .view-toggle button:hover { color: var(--text); }
  .view-toggle button.active { color: var(--amber); background: rgba(232,160,74,0.08); }

  .stats {
    position: fixed; top: 24px; right: 28px; z-index: 5;
    font-size: 11px; color: var(--text-muted);
    text-align: right; letter-spacing: 0.1em; pointer-events: none;
  }
  .stats .n { color: var(--text); font-family: 'Fraunces', serif; font-size: 18px; margin-right: 6px; }

  .hint {
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    z-index: 5; font-size: 10px; color: var(--text-dim);
    letter-spacing: 0.3em; pointer-events: none; transition: opacity 0.3s;
  }

  .legend {
    position: fixed; bottom: 20px; right: 28px; z-index: 5;
    display: none; font-size: 10px; color: var(--text-muted);
    letter-spacing: 0.1em; gap: 16px; pointer-events: none;
  }
  .legend.on { display: flex; }
  .legend .sw { display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: middle; }
  .legend .sw.hit { background: rgba(232,160,74,0.75); }
  .legend .sw.miss { background: rgba(94,192,192,0.75); }
  .legend .sw.none { background: rgba(140,140,140,0.45); }

  .tooltip {
    position: fixed; z-index: 7; background: var(--bg-2);
    border: 1px solid var(--line); padding: 8px 12px;
    font-size: 11px; color: var(--text); pointer-events: none;
    display: none; white-space: nowrap; max-width: 380px;
  }
  .tooltip .ip { color: var(--amber); font-weight: 500; }
  .tooltip .meta { color: var(--text-muted); margin-top: 4px; }

  .search-box {
    position: fixed; bottom: 60px; left: 28px; z-index: 5;
    background: var(--bg-2); border: 1px solid var(--line);
    padding: 6px 10px; width: 220px;
  }
  .search-box input {
    background: transparent; border: none; color: var(--text);
    font-family: inherit; font-size: 11px; outline: none; width: 100%;
  }
  .search-box::before { content: '⌕ '; color: var(--text-dim); font-size: 10px; }
  .search-box .hint-text { color: var(--text-dim); font-size: 9px; letter-spacing: 0.15em; margin-top: 4px; }

  .panel {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(560px, 100vw);
    background: var(--bg-2); border-left: 1px solid var(--line);
    z-index: 10; transform: translateX(100%);
    transition: transform 0.4s cubic-bezier(0.2,0.8,0.2,1);
    display: flex; flex-direction: column;
  }
  .panel.open { transform: translateX(0); }
  .panel-head {
    padding: 24px 28px 20px; border-bottom: 1px solid var(--line);
    flex-shrink: 0; position: relative;
  }
  .panel-head .ip-big {
    font-family: 'Fraunces', serif; font-weight: 300;
    font-size: 26px; color: var(--amber);
    letter-spacing: -0.01em; margin-bottom: 4px; word-break: break-all;
  }
  .panel-head .ctx-line {
    font-size: 11px; color: var(--text-muted);
    margin-top: 6px; letter-spacing: 0.05em;
  }
  .panel-head .summary {
    display: flex; flex-wrap: wrap; gap: 18px;
    margin-top: 14px; font-size: 11px;
    color: var(--text-muted); letter-spacing: 0.05em;
  }
  .panel-head .summary span strong {
    color: var(--text); font-family: 'Fraunces', serif;
    font-size: 14px; font-weight: 400; margin-right: 4px;
  }
  .close-btn {
    position: absolute; top: 20px; right: 20px;
    background: transparent; border: 1px solid var(--line);
    color: var(--text); width: 28px; height: 28px;
    cursor: pointer; font-size: 14px; line-height: 1; font-family: inherit;
  }
  .close-btn:hover { border-color: var(--amber); color: var(--amber); }

  .panel-body { flex: 1; overflow-y: auto; padding: 16px 8px 24px 28px; }
  .thread-group { margin-bottom: 24px; }
  .thread-label {
    font-size: 10px; color: var(--text-dim); letter-spacing: 0.15em;
    margin-bottom: 8px; padding-left: 8px; border-left: 2px solid var(--cyan);
  }
  .session {
    display: grid; grid-template-columns: 70px 1fr auto;
    gap: 10px; padding: 10px 12px;
    border-left: 1px solid var(--line); margin-left: 4px;
    cursor: pointer; transition: background 0.15s, border-color 0.15s;
    align-items: baseline;
  }
  .session:hover { background: rgba(232,160,74,0.05); border-left-color: var(--amber); }
  .session.expanded { background: rgba(232,160,74,0.08); border-left-color: var(--amber); }
  .session .ts { font-size: 10px; color: var(--text-muted); }
  .session .fn { font-size: 12px; color: var(--text); word-break: break-all; }
  .session .badges { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
  .badge {
    font-size: 9px; padding: 2px 6px; border-radius: 2px;
    letter-spacing: 0.1em; color: var(--text-muted);
    border: 1px solid var(--line); text-transform: uppercase;
  }
  .badge.hit { color: var(--amber); border-color: var(--amber); }
  .badge.miss { color: var(--cyan); border-color: var(--cyan); }
  .badge.dur { color: var(--text); }
  .badge.sql { color: var(--text); }

  .session-detail {
    grid-column: 1 / -1; margin-top: 12px;
    padding-top: 12px; border-top: 1px dashed var(--line); display: none;
  }
  .session.expanded .session-detail { display: block; }
  .session-detail .meta-line {
    font-size: 10px; color: var(--text-muted);
    margin-bottom: 8px; letter-spacing: 0.05em; line-height: 1.7;
  }
  .session-detail .meta-line .k { color: var(--text-dim); }
  .session-detail .meta-line .v { color: var(--text); margin-right: 12px; }
  .sql-block {
    background: var(--bg); border: 1px solid var(--line);
    padding: 12px; margin-bottom: 8px;
    font-size: 11px; line-height: 1.5; color: var(--text);
    white-space: pre-wrap; word-break: break-word;
    max-height: 280px; overflow-y: auto;
  }
  .sql-block .ds {
    color: var(--amber); font-size: 10px;
    letter-spacing: 0.1em; display: block; margin-bottom: 6px;
  }

  @media (max-width: 700px) {
    .hud h1 { font-size: 18px; }
    .view-toggle button { padding: 8px 12px; font-size: 9px; letter-spacing: 0.15em; }
    .stats { font-size: 10px; }
    .panel { width: 100vw; }
  }
</style>
</head>
<body>

<canvas id="canvas"></canvas>

<div class="hud">
  <h1>User Flows</h1>
  <div class="sub" id="hud-sub">EACH PARTICLE = ONE IP · CLICK TO EXPLORE</div>
</div>

<div class="view-toggle">
  <button class="active" data-view="particles">PARTICLES</button>
  <button data-view="timeline">TIMELINE</button>
</div>

<div class="stats" id="stats"></div>
<div class="hint" id="hint">CLICK TO INSPECT</div>

<div class="legend" id="legend">
  <span><span class="sw hit"></span>CACHE HIT</span>
  <span><span class="sw miss"></span>CACHE MISS</span>
  <span><span class="sw none"></span>NO CACHE</span>
</div>

<div class="search-box">
  <input type="text" id="search" placeholder="filter by ip..." autocomplete="off">
  <div class="hint-text">FILTERS BOTH VIEWS</div>
</div>

<div class="tooltip" id="tooltip">
  <div class="ip" id="tt-ip"></div>
  <div class="meta" id="tt-meta"></div>
</div>

<div class="panel" id="panel">
  <button class="close-btn" onclick="closePanel()">×</button>
  <div class="panel-head">
    <div class="ip-big" id="p-ip"></div>
    <div class="ctx-line" id="p-ctx"></div>
    <div class="summary" id="p-summary"></div>
  </div>
  <div class="panel-body" id="p-body"></div>
</div>

<script>
const SESSIONS = __DATA__;

SESSIONS.forEach(s => {
  s._start = s.start_ts ? Date.parse(s.start_ts) : null;
  s._end = s.end_ts ? Date.parse(s.end_ts) : s._start;
});

const byIP = {};
for (const s of SESSIONS) {
  const key = s.ip || 'unknown';
  (byIP[key] = byIP[key] || []).push(s);
}
const ipList = Object.entries(byIP)
  .map(([ip, sess]) => ({ ip, sessions: sess, count: sess.length }))
  .sort((a, b) => b.count - a.count);

const threadFirst = {};
for (const s of SESSIONS) {
  if (!s.thread || !s._start) continue;
  if (threadFirst[s.thread] === undefined || s._start < threadFirst[s.thread]) {
    threadFirst[s.thread] = s._start;
  }
}
const allThreads = Object.keys(threadFirst).sort((a, b) => threadFirst[a] - threadFirst[b]);

const validStarts = SESSIONS.map(s => s._start).filter(v => v !== null);
const validEnds = SESSIONS.map(s => s._end).filter(v => v !== null);
const timeMin = Math.min(...validStarts);
const timeMax = Math.max(...validEnds);

document.getElementById('stats').innerHTML = `
  <span class="n">${ipList.length}</span>IPs &nbsp;·&nbsp;
  <span class="n">${allThreads.length}</span>THREADS &nbsp;·&nbsp;
  <span class="n">${SESSIONS.length.toLocaleString()}</span>SESSIONS
`;

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
let vw, vh;
function resize() {
  vw = window.innerWidth; vh = window.innerHeight;
  canvas.width = vw * devicePixelRatio;
  canvas.height = vh * devicePixelRatio;
  canvas.style.width = vw + 'px';
  canvas.style.height = vh + 'px';
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
window.addEventListener('resize', resize);
resize();

let viewMode = 'particles';
let filterQuery = '';
document.querySelectorAll('.view-toggle button').forEach(btn => {
  btn.onclick = () => {
    viewMode = btn.dataset.view;
    document.querySelectorAll('.view-toggle button').forEach(b =>
      b.classList.toggle('active', b === btn));
    document.getElementById('legend').classList.toggle('on', viewMode === 'timeline');
    document.getElementById('hud-sub').textContent =
      viewMode === 'particles'
        ? 'EACH PARTICLE = ONE IP · CLICK TO EXPLORE'
        : 'EACH BAR = ONE SESSION · Y AXIS = THREAD · CLICK BAR FOR DETAIL';
  };
});

const particles = ipList.map(d => {
  const r = Math.log(d.count + 1) * 3 + 4;
  return {
    ...d,
    x: Math.random() * vw, y: Math.random() * vh,
    vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
    r, hover: false,
  };
});

const searchInput = document.getElementById('search');
searchInput.addEventListener('input', e => { filterQuery = e.target.value.trim().toLowerCase(); });
function ipVisible(ip) {
  if (!filterQuery) return true;
  return (ip || '').toLowerCase().includes(filterQuery);
}

let mouseX = -100, mouseY = -100;
canvas.addEventListener('mousemove', e => { mouseX = e.clientX; mouseY = e.clientY; });

function renderParticles() {
  let hoverP = null;
  for (const p of particles) {
    if (!ipVisible(p.ip)) continue;
    p.x += p.vx; p.y += p.vy;
    if (p.x < p.r || p.x > vw - p.r) p.vx *= -1;
    if (p.y < p.r || p.y > vh - p.r) p.vy *= -1;

    const d = Math.hypot(p.x - mouseX, p.y - mouseY);
    p.hover = d < p.r + 4;
    if (p.hover) hoverP = p;

    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 2.5);
    grad.addColorStop(0, p.hover ? 'rgba(245,241,232,0.5)' : 'rgba(232,160,74,0.25)');
    grad.addColorStop(1, 'rgba(232,160,74,0)');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 2.5, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = p.hover ? '#f5f1e8' : 'rgba(232,160,74,0.85)';
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
  }

  const tt = document.getElementById('tooltip');
  if (hoverP) {
    document.getElementById('tt-ip').textContent = hoverP.ip;
    document.getElementById('tt-meta').textContent = `${hoverP.count.toLocaleString()} sessions`;
    document.getElementById('tt-meta').style.whiteSpace = 'nowrap';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = 'crosshair';
  }
}

const TL_LEFT = 220, TL_TOP = 80, TL_BOT = 50, TL_PADR = 24;
function tlMetrics() {
  const w = vw - TL_LEFT - TL_PADR;
  const h = vh - TL_TOP - TL_BOT;
  const rowH = Math.max(3, Math.min(16, h / allThreads.length));
  return { w, h, rowH };
}
function tlX(t) { const { w } = tlMetrics(); return TL_LEFT + (t - timeMin) / (timeMax - timeMin || 1) * w; }
function tlY(i) { const { rowH } = tlMetrics(); return TL_TOP + i * rowH; }

function fmtTime(t) {
  const d = new Date(t);
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtDateTime(t) {
  const d = new Date(t);
  const p = n => String(n).padStart(2, '0');
  return `${d.getMonth()+1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function renderTimeline() {
  const { w, h, rowH } = tlMetrics();

  ctx.font = '10px JetBrains Mono';
  ctx.fillStyle = '#5a5852';
  ctx.strokeStyle = '#1f2127';
  const ticks = 8;
  for (let i = 0; i <= ticks; i++) {
    const x = TL_LEFT + w * i / ticks;
    const t = timeMin + (timeMax - timeMin) * i / ticks;
    ctx.beginPath(); ctx.moveTo(x, TL_TOP); ctx.lineTo(x, TL_TOP + h); ctx.stroke();
    ctx.fillText(fmtTime(t), x - 18, TL_TOP - 8);
  }

  ctx.fillStyle = '#8b8680';
  ctx.font = '9px JetBrains Mono';
  const labelStep = rowH < 8 ? Math.ceil(10 / rowH) : 1;
  allThreads.forEach((t, i) => {
    if (i % labelStep !== 0) return;
    const y = tlY(i) + rowH * 0.75;
    const short = t.length > 26 ? '…' + t.slice(-25) : t;
    ctx.fillText(short, 12, y);
  });

  ctx.strokeStyle = '#26282f';
  ctx.beginPath(); ctx.moveTo(TL_LEFT, TL_TOP); ctx.lineTo(TL_LEFT + w, TL_TOP); ctx.stroke();

  let hoverS = null;
  const hitC = 'rgba(232,160,74,0.75)';
  const missC = 'rgba(94,192,192,0.75)';
  const noneC = 'rgba(140,140,140,0.45)';
  const threadIdx = {};
  allThreads.forEach((t, i) => threadIdx[t] = i);

  for (const s of SESSIONS) {
    if (!s._start || !s.thread) continue;
    if (filterQuery && !ipVisible(s.ip)) continue;
    const ti = threadIdx[s.thread];
    if (ti === undefined) continue;

    const x1 = tlX(s._start);
    const x2 = tlX(s._end);
    const width = Math.max(1.5, x2 - x1);
    const y = tlY(ti);

    ctx.fillStyle = s.cache === 'hit' ? hitC : s.cache === 'miss' ? missC : noneC;
    ctx.fillRect(x1, y + 1, width, Math.max(1, rowH - 2));

    if (mouseX >= x1 - 2 && mouseX <= x1 + width + 2
        && mouseY >= y && mouseY <= y + rowH) {
      hoverS = s;
    }
  }

  const tt = document.getElementById('tooltip');
  if (hoverS) {
    document.getElementById('tt-ip').textContent = hoverS.function || '(unknown)';
    const meta = [
      `IP ${hoverS.ip}:${hoverS.port || '-'}`,
      `${fmtDateTime(hoverS._start)} · ${hoverS.duration_ms != null ? hoverS.duration_ms.toFixed(0)+'ms' : '-'}`,
      `THREAD ${hoverS.thread}`,
      hoverS.cache ? `CACHE ${hoverS.cache.toUpperCase()}${hoverS.cache_key ? ' · '+hoverS.cache_key : ''}` : 'NO CACHE',
    ].join('\n');
    document.getElementById('tt-meta').textContent = meta;
    document.getElementById('tt-meta').style.whiteSpace = 'pre-line';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = 'crosshair';
  }
  canvas._hoverSession = hoverS;
}

function loop() {
  ctx.clearRect(0, 0, vw, vh);
  if (viewMode === 'particles') renderParticles();
  else renderTimeline();
  requestAnimationFrame(loop);
}
loop();

canvas.addEventListener('click', e => {
  if (viewMode === 'particles') {
    for (const p of particles) {
      if (!ipVisible(p.ip)) continue;
      const d = Math.hypot(e.clientX - p.x, e.clientY - p.y);
      if (d < p.r + 4) { openIPPanel(p); return; }
    }
  } else {
    if (canvas._hoverSession) openSessionPanel(canvas._hoverSession);
  }
});

function openIPPanel(p) {
  document.getElementById('p-ip').textContent = p.ip;
  document.getElementById('p-ctx').textContent = '';
  document.getElementById('hint').style.opacity = 0;

  const sess = p.sessions;
  const ports = new Set(sess.map(s => s.port));
  const threads = new Set(sess.map(s => s.thread));
  const fns = new Set(sess.map(s => s.function));
  const sqls = sess.reduce((sum, s) => sum + (s.n_sqls || 0), 0);

  document.getElementById('p-summary').innerHTML = `
    <span><strong>${sess.length}</strong>sessions</span>
    <span><strong>${ports.size}</strong>ports</span>
    <span><strong>${threads.size}</strong>threads</span>
    <span><strong>${fns.size}</strong>functions</span>
    <span><strong>${sqls}</strong>sqls</span>
  `;

  const byThread = {};
  for (const s of sess) (byThread[s.thread] = byThread[s.thread] || []).push(s);
  const threadEntries = Object.entries(byThread).map(([t, arr]) => {
    arr.sort((a, b) => (a._start || 0) - (b._start || 0));
    return [t, arr];
  });
  threadEntries.sort((a, b) => (a[1][0]._start || 0) - (b[1][0]._start || 0));

  const body = document.getElementById('p-body');
  body.innerHTML = '';
  for (const [thread, arr] of threadEntries) {
    const group = document.createElement('div');
    group.className = 'thread-group';
    const lbl = document.createElement('div');
    lbl.className = 'thread-label';
    lbl.textContent = `THREAD · ${thread} · ${arr.length} call${arr.length>1?'s':''}`;
    group.appendChild(lbl);
    for (const s of arr) group.appendChild(makeSessionRow(s));
    body.appendChild(group);
  }
  document.getElementById('panel').classList.add('open');
}

function openSessionPanel(s) {
  const ip = s.ip || 'unknown';
  document.getElementById('p-ip').textContent = ip;
  document.getElementById('p-ctx').textContent = `THREAD · ${s.thread} · single call · IP has ${(byIP[ip]||[]).length} total sessions`;
  document.getElementById('hint').style.opacity = 0;

  document.getElementById('p-summary').innerHTML = `<span><strong>${s.function || '-'}</strong></span>`;

  const body = document.getElementById('p-body');
  body.innerHTML = '';
  const group = document.createElement('div');
  group.className = 'thread-group';
  const lbl = document.createElement('div');
  lbl.className = 'thread-label';
  lbl.textContent = `THREAD · ${s.thread}`;
  group.appendChild(lbl);
  const row = makeSessionRow(s);
  row.classList.add('expanded');
  const detail = row.querySelector('.session-detail');
  if (detail && !detail.dataset.loaded) fillSessionDetail(detail, s);
  group.appendChild(row);
  body.appendChild(group);

  document.getElementById('panel').classList.add('open');
}

function makeSessionRow(s) {
  const row = document.createElement('div');
  row.className = 'session';
  const tsShort = s._start ? fmtTime(s._start) : '-';
  const cacheBadge = s.cache === 'hit' ? '<span class="badge hit">cache</span>'
                   : s.cache === 'miss' ? '<span class="badge miss">db</span>' : '';
  const durBadge = s.duration_ms != null ? `<span class="badge dur">${s.duration_ms.toFixed(0)}ms</span>` : '';
  const sqlBadge = s.n_sqls ? `<span class="badge sql">${s.n_sqls} sql</span>` : '';

  const main = document.createElement('div');
  main.style.display = 'contents';
  main.innerHTML = `
    <div class="ts">${tsShort}</div>
    <div class="fn">${escapeHtml(s.function || '(unknown)')}</div>
    <div class="badges">${cacheBadge}${durBadge}${sqlBadge}</div>
  `;
  row.appendChild(main);

  const detail = document.createElement('div');
  detail.className = 'session-detail';
  row.appendChild(detail);

  row.addEventListener('click', e => {
    e.stopPropagation();
    const expanded = row.classList.toggle('expanded');
    if (expanded && !detail.dataset.loaded) fillSessionDetail(detail, s);
  });

  return row;
}

function fillSessionDetail(detail, s) {
  detail.dataset.loaded = '1';
  const dur = s.duration_ms != null ? s.duration_ms.toFixed(0) + 'ms' : '-';
  const guid = (s.guid || '-').slice(0, 14);
  const ckey = s.cache_key || '-';
  let html = `<div class="meta-line">`
    + `<span class="k">port</span> <span class="v">${s.port || '-'}</span>`
    + `<span class="k">duration</span> <span class="v">${dur}</span>`
    + `<span class="k">guid</span> <span class="v">${guid}</span><br>`
    + `<span class="k">cache</span> <span class="v">${s.cache || '-'}</span>`
    + `<span class="k">key</span> <span class="v">${escapeHtml(ckey)}</span>`
    + `</div>`;
  if (s.sqls && s.sqls.length) {
    for (let i = 0; i < s.sqls.length; i++) {
      const ds = (s.datasources && s.datasources[i]) || '-';
      html += `<div class="sql-block"><span class="ds">[${escapeHtml(ds)}]</span>${escapeHtml(s.sqls[i] || '')}</div>`;
    }
  } else {
    html += '<div class="meta-line">no sql in this call</div>';
  }
  detail.innerHTML = html;
}

function closePanel() { document.getElementById('panel').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
</script>
</body>
</html>
"""


def build_user_flows(df: pd.DataFrame, out_path: str = 'user_flows.html'):
    """Build a self-contained HTML from the sessions DataFrame."""

    records = []
    for _, row in df.iterrows():
        def safe_ts(v):
            if pd.isna(v): return None
            try: return v.isoformat()
            except Exception: return str(v)

        records.append({
            'ip': row.get('ip'),
            'port': str(row.get('port')) if row.get('port') is not None else None,
            'function': row.get('function'),
            'start_ts': safe_ts(row.get('start_ts')),
            'end_ts': safe_ts(row.get('end_ts')),
            'thread': row.get('thread'),
            'guid': row.get('guid'),
            'cache': row.get('cache'),
            'cache_key': row.get('cache_key'),
            'n_sqls': int(row.get('n_sqls') or 0),
            'duration_ms': float(row['duration_ms']) if pd.notna(row.get('duration_ms')) else None,
            'datasources': list(row.get('datasources') or []),
            'sqls': list(row.get('sqls') or []),
        })

    data_json = json.dumps(records, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace('__DATA__', data_json)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = len(html) / 1024 / 1024
    print(f'Saved: {out_path}  ({size_mb:.1f} MB, {len(records):,} sessions, {df["thread"].nunique()} threads)')
    return out_path


if __name__ == '__main__' or 'df' in dir():
    try:
        build_user_flows(df, 'user_flows.html')
    except NameError:
        print("df not found. Run: build_user_flows(df, 'user_flows.html')")
