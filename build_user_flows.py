"""
build_user_flows.py  (v5)
-------------------------
v5 changes:
  - New top toggle: BY IP / BY TABLE
  - Table view: each particle = one table, color hashed from table name
  - Click table -> right panel with calls grouped by function
  - df must have 'tables' column (list of table names per call)

Usage in Jupyter:
    # 1) add 'tables' column to df first:
    import sqlglot; from sqlglot import exp
    def _extract(sql):
        try: return list({t.name.lower() for t in sqlglot.parse_one(sql, dialect='oracle').find_all(exp.Table)})
        except: return []
    df['tables'] = df['sqls'].apply(lambda sqls: list({t for sql in (sqls or []) for t in _extract(sql)}))

    # 2) build html
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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400&family=JetBrains+Mono:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0a0c; --bg-2: #14151a; --line: #26282f;
    --text: #f5f1e8; --text-muted: #8b8680; --text-dim: #4a4944;
    --amber: #e8a04a; --cyan: #5ec0c0; --red: #d96060;
    --auto: #6fb3b3; --human: #d99a55; --mixed: #8b8680;
  }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: var(--bg); color: var(--text);
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
  }
  #canvas { position: fixed; inset: 0; cursor: crosshair; }

  .header {
    position: fixed; top: 0; left: 0; right: 0;
    z-index: 5; padding: 24px 28px;
    display: flex; align-items: flex-start; justify-content: space-between;
    pointer-events: none;
  }
  .header > * { pointer-events: auto; }
  .header-left { display: flex; align-items: center; gap: 16px; }
  .back-btn {
    background: var(--bg-2); border: 1px solid var(--line);
    color: var(--text); font-family: inherit;
    font-size: 11px; letter-spacing: 0.15em;
    padding: 8px 14px; cursor: pointer;
    display: none; transition: border-color 0.2s, color 0.2s;
  }
  .back-btn:hover { border-color: var(--amber); color: var(--amber); }
  .back-btn.on { display: block; }
  .title-block h1 {
    font-family: 'Fraunces', serif; font-weight: 300;
    font-size: 22px; letter-spacing: -0.01em; margin-bottom: 4px;
  }
  .title-block h1.ip-mode { color: var(--amber); }
  .title-block .sub {
    font-size: 11px; color: var(--text-muted); letter-spacing: 0.1em;
  }

  /* TOP CENTER TOGGLE */
  .view-toggle {
    position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
    z-index: 6; display: flex; background: var(--bg-2);
    border: 1px solid var(--line);
  }
  .view-toggle.hidden { display: none; }
  .view-toggle button {
    background: transparent; border: none; color: var(--text-muted);
    font-family: inherit; font-size: 10px; letter-spacing: 0.25em;
    padding: 9px 18px; cursor: pointer;
    transition: color 0.2s, background 0.2s;
  }
  .view-toggle button:hover { color: var(--text); }
  .view-toggle button.active { color: var(--amber); background: rgba(232,160,74,0.08); }

  .stats {
    font-size: 11px; color: var(--text-muted);
    text-align: right; letter-spacing: 0.1em; pointer-events: none;
  }
  .stats .n {
    color: var(--text); font-family: 'Fraunces', serif;
    font-size: 18px; margin-right: 6px;
  }

  .hint {
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    z-index: 5; font-size: 10px; color: var(--text-dim);
    letter-spacing: 0.3em; pointer-events: none; transition: opacity 0.3s;
  }
  .legend {
    position: fixed; bottom: 18px; right: 28px; z-index: 5;
    display: none; flex-direction: column; gap: 4px;
    font-size: 10px; color: var(--text-muted);
    letter-spacing: 0.1em; pointer-events: none; text-align: right;
  }
  .legend.on { display: flex; }
  .legend .row { display: flex; gap: 14px; justify-content: flex-end; }
  .legend .row .grp-label { color: var(--text-dim); font-size: 9px; }
  .legend .sw { display: inline-block; width: 10px; height: 10px; margin-right: 6px; vertical-align: middle; }
  .legend .sw.hit { background: rgba(232,160,74,0.75); }
  .legend .sw.miss { background: rgba(94,192,192,0.75); }
  .legend .sw.none { background: rgba(140,140,140,0.55); }
  .legend .pat { font-weight: 700; }
  .legend .pat.auto { color: var(--auto); }
  .legend .pat.human { color: var(--human); }
  .legend .pat.mixed { color: var(--mixed); }

  .search-box {
    position: fixed; bottom: 60px; left: 28px; z-index: 5;
    background: var(--bg-2); border: 1px solid var(--line);
    padding: 6px 10px; width: 220px; display: none;
  }
  .search-box.on { display: block; }
  .search-box input {
    background: transparent; border: none; color: var(--text);
    font-family: inherit; font-size: 11px; outline: none; width: 100%;
  }
  .search-box::before { content: '⌕ '; color: var(--text-dim); font-size: 10px; }

  .bottom-controls {
    position: fixed; bottom: 60px; left: 268px; z-index: 5;
    display: none; gap: 8px;
  }
  .bottom-controls.on { display: flex; }
  .bottom-controls button {
    background: var(--bg-2); border: 1px solid var(--line);
    color: var(--text); font-family: inherit;
    font-size: 10px; letter-spacing: 0.2em;
    padding: 9px 14px; cursor: pointer;
    transition: border-color 0.2s, color 0.2s;
  }
  .bottom-controls button:hover { border-color: var(--amber); color: var(--amber); }
  .bottom-controls button.active { color: var(--amber); border-color: var(--amber); background: rgba(232,160,74,0.08); }
  .bottom-controls input {
    background: var(--bg-2); border: 1px solid var(--line);
    color: var(--text); font-family: inherit;
    font-size: 11px; padding: 9px 12px; width: 240px;
    outline: none;
  }
  .bottom-controls input:focus { border-color: var(--amber); }

  .tooltip {
    position: fixed; z-index: 7; background: var(--bg-2);
    border: 1px solid var(--line); padding: 10px 14px;
    font-size: 11px; color: var(--text); pointer-events: none;
    display: none; white-space: nowrap; max-width: 440px;
  }
  .tooltip .ip { color: var(--amber); font-weight: 500; word-break: break-all; white-space: normal; }
  .tooltip .meta { color: var(--text-muted); margin-top: 4px; }

  .panel {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: min(580px, 100vw);
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
    font-size: 24px; color: var(--amber);
    letter-spacing: -0.01em; margin-bottom: 4px; word-break: break-all;
  }
  .panel-head .ip-big.tbl { /* color set inline via JS */ }
  .panel-head .ctx-line {
    font-size: 11px; color: var(--text-muted);
    margin-top: 6px; letter-spacing: 0.05em; line-height: 1.6;
  }
  .panel-head .ctx-line .pat { font-weight: 700; }
  .panel-head .ctx-line .pat.auto { color: var(--auto); }
  .panel-head .ctx-line .pat.human { color: var(--human); }
  .panel-head .ctx-line .pat.mixed { color: var(--mixed); }
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
    position: absolute; top: 16px; right: 16px;
    background: var(--bg); border: 1px solid var(--line);
    color: var(--text); width: 40px; height: 40px;
    cursor: pointer; font-size: 18px; line-height: 1; font-family: inherit;
    z-index: 100;
  }
  .close-btn:hover { border-color: var(--amber); color: var(--amber); }

  .panel-body { flex: 1; overflow-y: auto; padding: 16px 8px 24px 28px; }
  .group { margin-bottom: 24px; }
  .group-label {
    font-size: 10px; color: var(--text-dim); letter-spacing: 0.15em;
    margin-bottom: 8px; padding-left: 8px; border-left: 2px solid var(--cyan);
    word-break: break-all;
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
  .badge.dur, .badge.sql, .badge.ip { color: var(--text); }

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
    .title-block h1 { font-size: 18px; }
    .stats { font-size: 10px; }
    .panel { width: 100vw; }
    .view-toggle button { padding: 8px 12px; font-size: 9px; letter-spacing: 0.15em; }
  }
</style>
</head>
<body>

<canvas id="canvas"></canvas>

<div class="header">
  <div class="header-left">
    <button class="back-btn" id="back-btn" onclick="backToParticles()">← BACK</button>
    <div class="title-block">
      <h1 id="title">User Flows</h1>
      <div class="sub" id="subtitle">EACH PARTICLE = ONE IP · CLICK TO EXPLORE</div>
    </div>
  </div>
  <div class="stats" id="stats"></div>
</div>

<div class="view-toggle" id="view-toggle">
  <button class="active" data-view="ips">BY IP</button>
  <button data-view="tables">BY TABLE</button>
  <button data-view="stream">STREAM</button>
  <button data-view="users">USERS</button>
  <button data-view="lineage">LINEAGE</button>
</div>

<div class="hint" id="hint">CLICK TO INSPECT</div>

<div class="legend" id="legend">
  <div class="row">
    <span class="grp-label">BAR COLOR</span>
    <span><span class="sw hit"></span>CACHE HIT</span>
    <span><span class="sw miss"></span>CACHE MISS</span>
    <span><span class="sw none"></span>NO CACHE</span>
  </div>
  <div class="row">
    <span class="grp-label">PATTERN</span>
    <span class="pat auto">AUTO</span>
    <span class="pat mixed">MIXED</span>
    <span class="pat human">HUMAN</span>
  </div>
</div>

<div class="search-box on" id="search-box">
  <input type="text" id="search" placeholder="filter..." autocomplete="off">
</div>

<div class="bottom-controls" id="bottom-controls">
  <button id="gather-btn">GATHER BY DOMAIN</button>
  <button id="edges-btn">SHOW LINKS</button>
</div>

<div class="bottom-controls" id="stream-controls" style="left: 28px;">
  <input id="stream-table-input" list="stream-table-list" placeholder="select table..." />
  <datalist id="stream-table-list"></datalist>
  <button id="stream-play">⏸ PAUSE</button>
  <button id="stream-speed-100" class="active">100×</button>
  <button id="stream-speed-1000">1000×</button>
  <button id="stream-speed-10000">10000×</button>
  <button id="stream-reset">↺ RESTART</button>
</div>

<div class="bottom-controls" id="users-controls" style="left: 28px; flex-direction: column; align-items: flex-start; gap: 6px;">
  <div style="display: flex; gap: 8px;">
    <button data-mode="mapped_users" class="active">MAPPED · USERS</button>
    <button data-mode="mapped_tables">MAPPED · TABLES</button>
    <button data-mode="unmapped">UNMAPPED · TABLES</button>
  </div>
  <div style="display: flex; gap: 8px;">
    <button data-metric="count" class="active">BY CALL COUNT</button>
    <button data-metric="duration">BY DURATION</button>
  </div>
</div>

<div class="bottom-controls" id="lineage-controls" style="left: 28px;">
  <button data-lmetric="count" class="active">BY CALL COUNT</button>
  <button data-lmetric="duration">BY DURATION</button>
</div>

<div class="tooltip" id="tooltip">
  <div class="ip" id="tt-ip"></div>
  <div class="meta" id="tt-meta"></div>
</div>

<div class="panel" id="panel">
  <button class="close-btn" id="close-btn" type="button">×</button>
  <div class="panel-head">
    <div class="ip-big" id="p-ip"></div>
    <div class="ctx-line" id="p-ctx"></div>
    <div class="summary" id="p-summary"></div>
  </div>
  <div class="panel-body" id="p-body"></div>
</div>

<script>
const CALLS = __DATA__;

CALLS.forEach(c => {
  c._start = c.start_ts ? Date.parse(c.start_ts) : null;
  c._end = c.end_ts ? Date.parse(c.end_ts) : c._start;
});

const byIP = {};
for (const c of CALLS) {
  const key = c.ip || 'unknown';
  (byIP[key] = byIP[key] || []).push(c);
}
const ipList = Object.entries(byIP)
  .map(([ip, calls]) => ({ ip, calls, count: calls.length }))
  .sort((a, b) => b.count - a.count);

// table aggregation
const byTable = {};
for (const c of CALLS) {
  for (const t of (c.tables || [])) {
    (byTable[t] = byTable[t] || []).push(c);
  }
}
const tableList = Object.entries(byTable)
  .map(([table, calls]) => ({ table, calls, count: calls.length }))
  .sort((a, b) => b.count - a.count);

// infer domain per table = its most common datasource
function inferTableDomain(table) {
  const calls = byTable[table] || [];
  const cnt = {};
  for (const c of calls) {
    if (c.datasources) {
      const unique = new Set(c.datasources.filter(Boolean));
      for (const ds of unique) cnt[ds] = (cnt[ds] || 0) + 1;
    }
  }
  const top = Object.entries(cnt).sort((a,b) => b[1] - a[1])[0];
  return top ? top[0] : 'unknown';
}
const tableDomains = {};
for (const d of tableList) tableDomains[d.table] = inferTableDomain(d.table);
const allDomains = [...new Set(Object.values(tableDomains))].sort();
let domainCenters = {};
function computeDomainCenters() {
  domainCenters = {};
  if (allDomains.length === 0) return;
  if (allDomains.length === 1) {
    domainCenters[allDomains[0]] = { x: vw/2, y: vh/2 };
    return;
  }
  allDomains.forEach((d, i) => {
    const angle = (i / allDomains.length) * Math.PI * 2 - Math.PI / 2;
    const radius = Math.min(vw, vh) * 0.28;
    domainCenters[d] = {
      x: vw / 2 + Math.cos(angle) * radius,
      y: vh / 2 + Math.sin(angle) * radius,
    };
  });
}

// global time (pre-computed in Python — instant)
const GLOBAL_TMIN = Date.parse(__TMIN__);
const GLOBAL_TMAX = Date.parse(__TMAX__);

// stable hue per table name
function hashHue(s) {
  let h = 0;
  for (let i = 0; i < (s||'').length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xffff;
  return h % 360;
}
function tableColor(name, alpha = 1) {
  const hue = hashHue(name);
  return `hsla(${hue}, 55%, 65%, ${alpha})`;
}

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
computeDomainCenters();
window.addEventListener('resize', computeDomainCenters);
window.addEventListener('resize', () => { _moundsCache = null; });

// view state
let mainView = 'ips';            // 'ips' | 'tables'
let viewMode = 'particles';       // 'particles' | 'ip_timeline'
let selectedIP = null;
let filterQuery = '';

// particles
const ipParticles = ipList.map(d => {
  const r = Math.log(d.count + 1) * 3 + 4;
  return {
    ip: d.ip, calls: d.calls, count: d.count,
    x: Math.random() * vw, y: Math.random() * vh,
    vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
    r, hover: false,
  };
});
const tableParticles = tableList.map(d => {
  const domain = tableDomains[d.table];
  const r = Math.log(d.count + 1) * 3 + 4;
  return {
    table: d.table, calls: d.calls, count: d.count,
    x: Math.random() * vw, y: Math.random() * vh,
    vx: (Math.random() - 0.5) * 0.5, vy: (Math.random() - 0.5) * 0.5,
    r, hue: hashHue(d.table), domain, hover: false,
  };
});

// gather state
let clustered = false;
let showEdges = false;

function toggleGather() {
  clustered = !clustered;
  const btn = document.getElementById('gather-btn');
  btn.classList.toggle('active', clustered);
  btn.textContent = clustered ? 'SCATTER' : 'GATHER BY DOMAIN';
  if (!clustered) {
    for (const p of tableParticles) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 2.5;
      p.vx += Math.cos(angle) * speed;
      p.vy += Math.sin(angle) * speed;
    }
  }
}
function toggleEdges() {
  showEdges = !showEdges;
  const btn = document.getElementById('edges-btn');
  btn.classList.toggle('active', showEdges);
  btn.textContent = showEdges ? 'HIDE LINKS' : 'SHOW LINKS';
}
window.toggleGather = toggleGather;
window.toggleEdges = toggleEdges;
document.getElementById('gather-btn').addEventListener('click', toggleGather);
document.getElementById('edges-btn').addEventListener('click', toggleEdges);

// --- STREAM state ---
const sortedCalls = [...CALLS].filter(c => c._start != null).sort((a, b) => a._start - b._start);
let streamCursor = 0;
let streamTime = GLOBAL_TMIN;
let streamPlaying = true;
let streamSpeed = 100;
let activePulses = [];

// table-specific state
let selectedStreamTable = null;
let streamTableCalls = [];
let fnOrder = [];        // function names sorted by frequency (top first)
let fnLanes = {};        // function name -> lane index

const STREAM_TOP = 160;
const STREAM_BOT = 90;
const STREAM_LEFT = 180;
const STREAM_RIGHT = 40;
const STREAM_WINDOW_SEC = 3600;  // 1 hour of data visible across the lane area

function streamLaneHeight() {
  const h = vh - STREAM_TOP - STREAM_BOT;
  return h / Math.max(1, fnOrder.length || 1);
}
function streamLaneY(fn) {
  const idx = fnLanes[fn] ?? 0;
  const laneH = streamLaneHeight();
  return STREAM_TOP + laneH * idx + laneH / 2;
}
function streamGetX(callTime) {
  const dataSec = (streamTime - callTime) / 1000;
  const widthPx = vw - STREAM_LEFT - STREAM_RIGHT;
  return (vw - STREAM_RIGHT) - (dataSec / STREAM_WINDOW_SEC) * widthPx;
}

function selectStreamTable(name) {
  if (!name || !byTable[name]) return;
  selectedStreamTable = name;
  streamTableCalls = sortedCalls.filter(c => (c.tables || []).includes(name));
  const fnCount = {};
  for (const c of streamTableCalls) fnCount[c.function] = (fnCount[c.function] || 0) + 1;
  fnOrder = Object.entries(fnCount).sort((a, b) => b[1] - a[1]).map(e => e[0]);
  fnLanes = {};
  fnOrder.forEach((f, i) => fnLanes[f] = i);
  streamCursor = 0;
  streamTime = streamTableCalls.length ? streamTableCalls[0]._start : GLOBAL_TMIN;
  activePulses = [];
}

function populateTableSelect() {
  const dl = document.getElementById('stream-table-list');
  dl.innerHTML = '';
  for (const t of tableList) {
    const opt = document.createElement('option');
    opt.value = t.table;
    opt.label = `${t.table} (${t.count})`;
    dl.appendChild(opt);
  }
}
populateTableSelect();

document.getElementById('stream-table-input').addEventListener('change', e => {
  selectStreamTable(e.target.value.trim());
});

function streamReset() {
  if (selectedStreamTable) {
    streamCursor = 0;
    streamTime = streamTableCalls.length ? streamTableCalls[0]._start : GLOBAL_TMIN;
    activePulses = [];
  }
}

function tickStream(dtMs) {
  if (!streamPlaying || !selectedStreamTable) return;
  streamTime += dtMs * streamSpeed;
  if (streamTime >= GLOBAL_TMAX) { streamReset(); return; }
  // spawn newly-arrived calls
  while (streamCursor < streamTableCalls.length && streamTableCalls[streamCursor]._start <= streamTime) {
    activePulses.push({ call: streamTableCalls[streamCursor] });
    streamCursor++;
  }
  // drop pulses that flowed off the left
  activePulses = activePulses.filter(p => streamGetX(p.call._start) > STREAM_LEFT - 30);
}

function renderStream() {
  // header: clock
  const d = new Date(streamTime);
  const pad = n => String(n).padStart(2, '0');
  const timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const subStr = selectedStreamTable
    ? `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} · ${streamSpeed}× · TABLE: ${selectedStreamTable} (${streamTableCalls.length} calls, ${fnOrder.length} fns)`
    : 'CHOOSE A TABLE BELOW';

  ctx.save();
  ctx.fillStyle = 'rgba(245,241,232,0.85)';
  ctx.font = '300 56px Fraunces, serif';
  ctx.textAlign = 'center';
  ctx.fillText(timeStr, vw/2, 90);
  ctx.fillStyle = 'rgba(139,134,128,0.85)';
  ctx.font = '10px JetBrains Mono';
  ctx.fillText(subStr, vw/2, 112);
  ctx.restore();

  if (!selectedStreamTable || !fnOrder.length) {
    // progress bar still
    const progress = (streamTime - GLOBAL_TMIN) / (GLOBAL_TMAX - GLOBAL_TMIN || 1);
    ctx.fillStyle = 'rgba(232,160,74,0.6)';
    ctx.fillRect(0, vh - 3, vw * progress, 3);
    return;
  }

  // lane backgrounds + labels
  const laneH = streamLaneHeight();
  ctx.textAlign = 'left';
  for (let i = 0; i < fnOrder.length; i++) {
    const y = STREAM_TOP + laneH * i;
    if (i % 2 === 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.02)';
      ctx.fillRect(STREAM_LEFT, y, vw - STREAM_LEFT - STREAM_RIGHT, laneH);
    }
    ctx.fillStyle = '#8b8680';
    ctx.font = '10px JetBrains Mono';
    let lbl = shortFn(fnOrder[i]);
    if (lbl.length > 22) lbl = lbl.slice(0, 21) + '…';
    ctx.fillText(lbl, 14, y + laneH/2 + 4);
  }

  // playhead (right edge = now)
  ctx.strokeStyle = 'rgba(232,160,74,0.35)';
  ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(vw - STREAM_RIGHT, STREAM_TOP);
  ctx.lineTo(vw - STREAM_RIGHT, vh - STREAM_BOT);
  ctx.stroke();
  ctx.setLineDash([]);

  // pulses
  let hoverP = null;
  for (const p of activePulses) {
    const c = p.call;
    const x = streamGetX(c._start);
    const y = streamLaneY(c.function);
    if (x < STREAM_LEFT || x > vw - STREAM_RIGHT + 4) continue;

    let r, g, b;
    if (c.cache === 'hit') { r = 232; g = 160; b = 74; }
    else if (c.cache === 'miss') { r = 94; g = 192; b = 192; }
    else { r = 180; g = 180; b = 180; }

    // fade by horizontal position (newer = brighter)
    const widthPx = vw - STREAM_LEFT - STREAM_RIGHT;
    const norm = ((vw - STREAM_RIGHT) - x) / widthPx;  // 0 = right (new), 1 = left (old)
    const alpha = 0.85 - norm * 0.5;
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
    ctx.beginPath();
    ctx.arc(x, y, 4.5, 0, Math.PI * 2);
    ctx.fill();

    const d2 = Math.hypot(mouseX - x, mouseY - y);
    if (d2 < 9 && !hoverP) hoverP = { call: c, x, y };
  }

  // tooltip
  const tt = document.getElementById('tooltip');
  if (hoverP) {
    const c = hoverP.call;
    document.getElementById('tt-ip').textContent = c.function || '(unknown)';
    const meta = [
      `${pad(new Date(c._start).getHours())}:${pad(new Date(c._start).getMinutes())}:${pad(new Date(c._start).getSeconds())} · ${c.ip}:${c.port}`,
      c.cache ? `CACHE ${c.cache.toUpperCase()}${c.cache_key ? ' · '+c.cache_key : ''}` : 'NO CACHE',
      c.duration_ms != null ? `duration ${c.duration_ms.toFixed(0)}ms` : '',
      c.n_sqls ? `${c.n_sqls} sql` : '',
    ].filter(Boolean).join('\n');
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

  // progress bar
  const progress = (streamTime - GLOBAL_TMIN) / (GLOBAL_TMAX - GLOBAL_TMIN || 1);
  ctx.fillStyle = 'rgba(232,160,74,0.6)';
  ctx.fillRect(0, vh - 3, vw * progress, 3);
}

document.getElementById('stream-play').addEventListener('click', () => {
  streamPlaying = !streamPlaying;
  document.getElementById('stream-play').textContent = streamPlaying ? '⏸ PAUSE' : '▶ PLAY';
});
document.getElementById('stream-reset').addEventListener('click', streamReset);
for (const speed of [100, 1000, 10000]) {
  document.getElementById('stream-speed-' + speed).addEventListener('click', () => {
    streamSpeed = speed;
    for (const s of [100, 1000, 10000]) {
      document.getElementById('stream-speed-' + s).classList.toggle('active', s === speed);
    }
  });
}

// --- USERS view (treemap with zoom/pan) ---
let usersMode = 'mapped_users';  // 'mapped_users' | 'mapped_tables' | 'unmapped'
let userRects = [];
let _userHover = null;

// zoom/pan state
let usersScale = 1;
let usersOffX = 0;
let usersOffY = 0;
function resetUsersZoom() {
  usersScale = 1; usersOffX = 0; usersOffY = 0;
}

// drag-vs-click discrimination
let usersDragging = false;
let usersDragStartX = 0, usersDragStartY = 0;
let usersDragOrigX = 0, usersDragOrigY = 0;
let usersDragMoved = false;

const mappedCalls = CALLS.filter(c => c.session_user_id);
const unmappedCalls = CALLS.filter(c => !c.session_user_id);

function _functionsOf(calls) {
  const cnt = {};
  for (const c of calls) cnt[c.function] = (cnt[c.function] || 0) + 1;
  return Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(e => e[0]);
}
function _durationOf(calls) {
  let s = 0;
  for (const c of calls) s += (c.duration_ms || 0);
  return s;
}
function _keywordsOf(calls) {
  const valCount = {};   // "col='val'" -> count
  const colCount = {};   // col -> count (where 등장)
  const selectCols = new Set();
  const whereCols = new Set();
  for (const c of calls) {
    for (const sc of (c.select_cols || [])) selectCols.add(sc);
    const wv = c.where_values || {};
    for (const [col, vals] of Object.entries(wv)) {
      whereCols.add(col);
      colCount[col] = (colCount[col] || 0) + 1;
      for (const v of vals) {
        const key = `${col}='${v}'`;
        valCount[key] = (valCount[key] || 0) + 1;
      }
    }
  }
  const topValues = Object.entries(valCount).sort((a,b) => b[1]-a[1]).slice(0, 12)
                          .map(([k, n]) => ({ key: k, count: n }));
  const overlap = [...whereCols].filter(c => selectCols.has(c))
                          .sort((a,b) => (colCount[b]||0) - (colCount[a]||0))
                          .slice(0, 10)
                          .map(c => ({ col: c, count: colCount[c] || 0 }));
  return { topValues, overlap };
}

// mapped users
const callsByUser = {};
for (const c of mappedCalls) {
  const u = c.session_user_id;
  (callsByUser[u] = callsByUser[u] || []).push(c);
}
const userItemsBase = Object.entries(callsByUser)
  .map(([user, calls]) => ({
    key: user, calls,
    count: calls.length,
    duration: _durationOf(calls),
    functions: _functionsOf(calls),
    keywords: _keywordsOf(calls),
  }));

// mapped calls grouped by table
const callsByMappedTable = {};
for (const c of mappedCalls) {
  for (const t of (c.tables || [])) {
    (callsByMappedTable[t] = callsByMappedTable[t] || []).push(c);
  }
}
const mappedTableItemsBase = Object.entries(callsByMappedTable)
  .map(([t, calls]) => ({
    key: t, calls,
    count: calls.length,
    duration: _durationOf(calls),
    functions: _functionsOf(calls),
    keywords: _keywordsOf(calls),
  }));

// unmapped calls grouped by table
const callsByUnmappedTable = {};
for (const c of unmappedCalls) {
  for (const t of (c.tables || [])) {
    (callsByUnmappedTable[t] = callsByUnmappedTable[t] || []).push(c);
  }
}
const unmappedTableItemsBase = Object.entries(callsByUnmappedTable)
  .map(([t, calls]) => ({
    key: t, calls,
    count: calls.length,
    duration: _durationOf(calls),
    functions: _functionsOf(calls),
    keywords: _keywordsOf(calls),
  }));

// pre-sort by both metrics
function _sortByMetric(base, metric) {
  return [...base]
    .sort((a, b) => b[metric] - a[metric])
    .map(it => ({ ...it, value: it[metric] }));
}
const _itemsCache = {
  mapped_users: { count: _sortByMetric(userItemsBase, 'count'), duration: _sortByMetric(userItemsBase, 'duration') },
  mapped_tables: { count: _sortByMetric(mappedTableItemsBase, 'count'), duration: _sortByMetric(mappedTableItemsBase, 'duration') },
  unmapped: { count: _sortByMetric(unmappedTableItemsBase, 'count'), duration: _sortByMetric(unmappedTableItemsBase, 'duration') },
};

let usersMetric = 'count';  // 'count' | 'duration'

function currentUsersItems() {
  return _itemsCache[usersMode][usersMetric] || [];
}
function currentUsersHeaderText() {
  const items = currentUsersItems();
  const base = usersMode === 'mapped_users' ? userItemsBase
             : usersMode === 'mapped_tables' ? mappedTableItemsBase
             : unmappedTableItemsBase;
  const callsTotal = usersMode === 'unmapped' ? unmappedCalls.length : mappedCalls.length;
  const totalDuration = base.reduce((s, it) => s + it.duration, 0);
  const metricLabel = usersMetric === 'count' ? 'CALL COUNT' : 'TOTAL DURATION';
  const totalStr = usersMetric === 'count'
    ? `${callsTotal.toLocaleString()} calls`
    : `${fmtInterval(totalDuration)} total`;

  if (usersMode === 'mapped_users') {
    return [
      `${items.length.toLocaleString()} mapped users`,
      `${totalStr} · sorted by ${metricLabel} · scroll to zoom · drag to pan · ${(usersScale*100).toFixed(0)}%`
    ];
  }
  if (usersMode === 'mapped_tables') {
    return [
      `${items.length.toLocaleString()} tables · mapped traffic`,
      `${totalStr} · sorted by ${metricLabel} · scroll to zoom · drag to pan · ${(usersScale*100).toFixed(0)}%`
    ];
  }
  return [
    `${items.length.toLocaleString()} tables · unmapped traffic`,
    `${totalStr} · sorted by ${metricLabel} · scroll to zoom · drag to pan · ${(usersScale*100).toFixed(0)}%`
  ];
}
function currentUsersLabelPrefix() {
  return usersMode === 'mapped_users' ? 'USER ' : 'TABLE ';
}

// squarified treemap
function squarify(items, rect) {
  if (!items.length) return [];
  if (items.length === 1) return [{ ...items[0], rect: {...rect} }];

  const total = items.reduce((s, i) => s + i.value, 0);
  const isHoriz = rect.w >= rect.h;
  const length = isHoriz ? rect.h : rect.w;

  let row = [];
  let rowSum = 0;
  let bestWorst = Infinity;
  let i = 0;

  while (i < items.length) {
    const newSum = rowSum + items[i].value;
    const newRow = [...row, items[i]];
    const rowFrac = newSum / total;
    const rowSize = isHoriz ? rect.w * rowFrac : rect.h * rowFrac;
    const worst = newRow.reduce((mx, item) => {
      const itemFrac = item.value / newSum;
      const itemLen = length * itemFrac;
      const ratio = Math.max(rowSize / itemLen, itemLen / rowSize);
      return Math.max(mx, ratio);
    }, 0);
    if (worst > bestWorst && row.length > 0) break;
    row.push(items[i]);
    rowSum = newSum;
    bestWorst = worst;
    i++;
  }

  const rowFrac = rowSum / total;
  const rowSize = isHoriz ? rect.w * rowFrac : rect.h * rowFrac;
  const placed = [];
  let offset = 0;
  for (const item of row) {
    const itemFrac = item.value / rowSum;
    const itemLen = length * itemFrac;
    if (isHoriz) {
      placed.push({ ...item, rect: { x: rect.x, y: rect.y + offset, w: rowSize, h: itemLen } });
    } else {
      placed.push({ ...item, rect: { x: rect.x + offset, y: rect.y, w: itemLen, h: rowSize } });
    }
    offset += itemLen;
  }
  let restRect;
  if (isHoriz) {
    restRect = { x: rect.x + rowSize, y: rect.y, w: rect.w - rowSize, h: rect.h };
  } else {
    restRect = { x: rect.x, y: rect.y + rowSize, w: rect.w, h: rect.h - rowSize };
  }
  return [...placed, ...squarify(items.slice(i), restRect)];
}

function renderUsersView() {
  const items = currentUsersItems();
  const top = 160, bot = 90, side = 24;
  const rect = { x: side, y: top, w: vw - side*2, h: vh - top - bot };

  // header
  const [hd1, hd2] = currentUsersHeaderText();
  ctx.save();
  ctx.fillStyle = 'rgba(245,241,232,0.85)';
  ctx.font = '300 36px Fraunces, serif';
  ctx.textAlign = 'center';
  ctx.fillText(hd1, vw/2, 88);
  ctx.fillStyle = 'rgba(139,134,128,0.85)';
  ctx.font = '10px JetBrains Mono';
  ctx.fillText(hd2, vw/2, 112);
  ctx.restore();

  if (!items.length) return;

  userRects = squarify(items, rect);

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, top - 30, vw, vh);
  ctx.clip();

  let hover = null;
  for (const r of userRects) {
    if (!r.rect || r.rect.w < 1 || r.rect.h < 1) continue;
    const sx = r.rect.x * usersScale + usersOffX;
    const sy = r.rect.y * usersScale + usersOffY;
    const sw = r.rect.w * usersScale;
    const sh = r.rect.h * usersScale;
    if (sx + sw < 0 || sx > vw || sy + sh < 0 || sy > vh) continue;

    const hue = hashHue(r.key);
    const isHover = mouseX >= sx && mouseX <= sx + sw && mouseY >= sy && mouseY <= sy + sh;
    if (isHover) hover = r;

    ctx.fillStyle = isHover
      ? `hsla(${hue}, 55%, 70%, 0.95)`
      : `hsla(${hue}, 45%, 50%, 0.75)`;
    ctx.fillRect(sx, sy, sw, sh);
    ctx.strokeStyle = 'rgba(10,10,12,0.5)';
    ctx.lineWidth = 1;
    ctx.strokeRect(sx, sy, sw, sh);

    if (sw > 50 && sh > 20) {
      const labelSize = Math.max(10, Math.min(24, Math.sqrt(sw * sh) / 7));
      ctx.fillStyle = 'rgba(10,10,12,0.9)';
      ctx.textAlign = 'left';
      ctx.font = `${labelSize}px JetBrains Mono`;
      const maxChars = Math.floor(sw / (labelSize * 0.6));
      const txt = r.key.length > maxChars
        ? r.key.slice(0, Math.max(1, maxChars - 1)) + '…'
        : r.key;
      ctx.fillText(txt, sx + 8, sy + labelSize + 4);
      let nextY = sy + labelSize + 4;
      if (sh > labelSize * 2.4) {
        ctx.fillStyle = 'rgba(10,10,12,0.65)';
        ctx.font = `${Math.max(9, labelSize * 0.55)}px JetBrains Mono`;
        nextY = sy + labelSize + 4 + labelSize * 0.75;
        const valueLabel = usersMetric === 'count'
          ? r.count.toLocaleString() + ' calls'
          : fmtInterval(r.duration);
        ctx.fillText(valueLabel + ' · ' + (r.functions ? r.functions.length : 0) + ' fns', sx + 8, nextY);
      }
      // function list — show as many as fit
      if (r.functions && sh > labelSize * 4) {
        const fnSize = Math.max(8, labelSize * 0.5);
        const lineH = fnSize * 1.35;
        const listTop = nextY + lineH * 0.6;
        const available = sh - (listTop - sy) - 6;
        const maxLines = Math.floor(available / lineH);
        const fnMaxChars = Math.floor((sw - 16) / (fnSize * 0.6));
        ctx.font = `${fnSize}px JetBrains Mono`;
        ctx.fillStyle = 'rgba(10,10,12,0.55)';
        const total = r.functions.length;
        const showCount = Math.max(0, Math.min(total, maxLines));
        const reservedForMore = total > maxLines ? 1 : 0;
        const shown = r.functions.slice(0, Math.max(0, showCount - reservedForMore));
        let yy = listTop + fnSize;
        for (const fn of shown) {
          const s = shortFn(fn);
          const t2 = s.length > fnMaxChars ? s.slice(0, Math.max(1, fnMaxChars - 1)) + '…' : s;
          ctx.fillText(t2, sx + 8, yy);
          yy += lineH;
        }
        if (reservedForMore) {
          ctx.fillStyle = 'rgba(10,10,12,0.45)';
          ctx.fillText('+ ' + (total - shown.length) + ' more', sx + 8, yy);
        }
      }
    }
  }
  ctx.restore();
  _userHover = hover;

  const tt = document.getElementById('tooltip');
  if (hover) {
    document.getElementById('tt-ip').textContent = currentUsersLabelPrefix() + hover.key;
    const calls = hover.calls;
    const fns = new Set(calls.map(c => c.function));
    const ips = new Set(calls.map(c => c.ip));
    document.getElementById('tt-meta').textContent =
      `${calls.length.toLocaleString()} calls · ${fmtInterval(hover.duration)} total · ${fns.size} functions · ${ips.size} IPs`;
    document.getElementById('tt-meta').style.whiteSpace = 'nowrap';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = usersDragging ? 'grabbing' : 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = usersDragging ? 'grabbing' : 'grab';
  }
}

function openUserDetailPanel(r) {
  const pIp = document.getElementById('p-ip');
  const hue = hashHue(r.key);
  pIp.style.color = `hsl(${hue}, 55%, 65%)`;
  pIp.textContent = currentUsersLabelPrefix() + r.key;

  const calls = r.calls;
  const fns = {};
  for (const c of calls) (fns[c.function] = fns[c.function] || []).push(c);
  const ips = new Set(calls.map(c => c.ip));
  const ports = new Set(calls.map(c => c.port));

  document.getElementById('p-ctx').textContent =
    `${calls.length.toLocaleString()} calls · ${Object.keys(fns).length} functions · ${ips.size} IPs · ${ports.size} sessions`;
  document.getElementById('p-summary').innerHTML = `
    <span><strong>${calls.length}</strong>calls</span>
    <span><strong>${Object.keys(fns).length}</strong>functions</span>
    <span><strong>${ips.size}</strong>IPs</span>
  `;

  const body = document.getElementById('p-body');
  body.innerHTML = '';
  const tCol = `hsl(${hue}, 55%, 65%)`;
  const fnEntries = Object.entries(fns).sort((a, b) => b[1].length - a[1].length);
  for (const [fn, arr] of fnEntries) {
    const group = document.createElement('div');
    group.className = 'group';
    const lbl = document.createElement('div');
    lbl.className = 'group-label';
    lbl.style.borderLeftColor = tCol;
    lbl.textContent = `${shortFn(fn) || fn} · ${arr.length} call${arr.length>1?'s':''}`;
    group.appendChild(lbl);
    arr.sort((a, b) => (a._start || 0) - (b._start || 0));
    const shown = arr.slice(0, 50);
    for (const c of shown) group.appendChild(makeTableCallRow(c));
    if (arr.length > 50) {
      const more = document.createElement('div');
      more.className = 'group-label';
      more.style.borderLeftColor = 'var(--text-dim)';
      more.style.marginTop = '8px';
      more.textContent = `+ ${arr.length - 50} more (truncated)`;
      group.appendChild(more);
    }
    body.appendChild(group);
  }
  document.getElementById('panel').classList.add('open');
}

document.querySelectorAll('#users-controls button[data-mode]').forEach(btn => {
  btn.addEventListener('click', () => {
    usersMode = btn.dataset.mode;
    document.querySelectorAll('#users-controls button[data-mode]').forEach(b =>
      b.classList.toggle('active', b === btn));
    resetUsersZoom();
    closePanel();
  });
});
document.querySelectorAll('#users-controls button[data-metric]').forEach(btn => {
  btn.addEventListener('click', () => {
    usersMetric = btn.dataset.metric;
    document.querySelectorAll('#users-controls button[data-metric]').forEach(b =>
      b.classList.toggle('active', b === btn));
    resetUsersZoom();
    closePanel();
  });
});

document.querySelectorAll('#lineage-controls button[data-lmetric]').forEach(btn => {
  btn.addEventListener('click', () => {
    lineageMetric = btn.dataset.lmetric;
    document.querySelectorAll('#lineage-controls button[data-lmetric]').forEach(b =>
      b.classList.toggle('active', b === btn));
    _moundsBuildOrUpdate();  // recompute targets for smooth transition
  });
});

// --- LINEAGE view ---
const lineageJoins = {};
const lineageNext = {};
const lineagePrev = {};
const lineageUnions = {};
const lineageWhereValues = {};

for (const c of CALLS) {
  for (const pair of (c.join_pairs || [])) {
    const [ta, ka, tb, kb] = pair;
    if (!ta || !tb) continue;
    if (!lineageJoins[ta]) lineageJoins[ta] = {};
    if (!lineageJoins[ta][tb]) lineageJoins[ta][tb] = { keys: new Set(), count: 0 };
    lineageJoins[ta][tb].keys.add(`${ka} = ${kb}`);
    lineageJoins[ta][tb].count++;
    if (!lineageJoins[tb]) lineageJoins[tb] = {};
    if (!lineageJoins[tb][ta]) lineageJoins[tb][ta] = { keys: new Set(), count: 0 };
    lineageJoins[tb][ta].keys.add(`${kb} = ${ka}`);
    lineageJoins[tb][ta].count++;
  }
  for (const pair of (c.union_pairs || [])) {
    const [a, b] = pair;
    if (!a || !b) continue;
    if (!lineageUnions[a]) lineageUnions[a] = {};
    if (!lineageUnions[b]) lineageUnions[b] = {};
    lineageUnions[a][b] = (lineageUnions[a][b] || 0) + 1;
    lineageUnions[b][a] = (lineageUnions[b][a] || 0) + 1;
  }
  if (c.where_values) {
    for (const t of (c.tables || [])) {
      if (!lineageWhereValues[t]) lineageWhereValues[t] = {};
      for (const [col, vals] of Object.entries(c.where_values)) {
        if (!lineageWhereValues[t][col]) lineageWhereValues[t][col] = new Set();
        for (const v of vals) lineageWhereValues[t][col].add(v);
      }
    }
  }
}

// session calls list (sorted by time)
const sessionCallsList = {};
for (const c of CALLS) {
  const k = `${c.ip}:${c.port}`;
  (sessionCallsList[k] = sessionCallsList[k] || []).push(c);
}
for (const k of Object.keys(sessionCallsList)) {
  sessionCallsList[k].sort((a, b) => (a._start || 0) - (b._start || 0));
  // session adjacency
  const arr = sessionCallsList[k];
  for (let i = 0; i < arr.length - 1; i++) {
    const ta = arr[i].tables || [];
    const tb = arr[i+1].tables || [];
    for (const a of ta) for (const b of tb) {
      if (a === b) continue;
      if (!lineageNext[a]) lineageNext[a] = {};
      lineageNext[a][b] = (lineageNext[a][b] || 0) + 1;
      if (!lineagePrev[b]) lineagePrev[b] = {};
      lineagePrev[b][a] = (lineagePrev[b][a] || 0) + 1;
    }
  }
}

// sessions containing each table
const sessionsByTable = {};
for (const k of Object.keys(sessionCallsList)) {
  const seen = new Set();
  for (const c of sessionCallsList[k]) for (const t of (c.tables || [])) seen.add(t);
  for (const t of seen) (sessionsByTable[t] = sessionsByTable[t] || []).push(k);
}

function computeLineagePatterns(selectedTable, windowSize) {
  const sessions = sessionsByTable[selectedTable] || [];
  const patterns = {};
  for (const sk of sessions) {
    const calls = sessionCallsList[sk];
    const idx = calls.findIndex(c => (c.tables || []).includes(selectedTable));
    if (idx < 0) continue;
    const start = Math.max(0, idx - windowSize);
    const end = Math.min(calls.length, idx + windowSize + 1);
    const path = calls.slice(start, end);
    const localIdx = idx - start;
    const sig = path.map((c, i) => (c.function || '?') + (i === localIdx ? '*' : '')).join('|');
    if (!patterns[sig]) {
      patterns[sig] = { sig, sample: path, selectedIdx: localIdx, count: 0,
                        isStart: start === 0, isEnd: end === calls.length };
    }
    patterns[sig].count++;
  }
  return Object.values(patterns).sort((a, b) => b.count - a.count);
}

// all tables, mapping-agnostic, sorted by duration
const lineageTableItems = [];
{
  const tableCalls = {};
  for (const c of CALLS) {
    for (const t of (c.tables || [])) {
      (tableCalls[t] = tableCalls[t] || []).push(c);
    }
  }
  for (const [t, calls] of Object.entries(tableCalls)) {
    lineageTableItems.push({
      key: t, calls,
      count: calls.length,
      duration: calls.reduce((s, c) => s + (c.duration_ms || 0), 0),
      functions: _functionsOf(calls),
      value: 0,
    });
  }
  lineageTableItems.sort((a, b) => b.duration - a.duration);
  lineageTableItems.forEach(it => it.value = it.duration);
}

let lineageMode = 'treemap';
let lineageSelected = null;
let lineageWindow = 1;  // path window size (prev/selected/next)
let lineageRects = [];
let lineageHover = null;
let lineageDetailHover = null;

let lineageScale = 1, lineageOffX = 0, lineageOffY = 0;
function resetLineageZoom() { lineageScale = 1; lineageOffX = 0; lineageOffY = 0; }
let lineageDragging = false;
let lineageDragStartX = 0, lineageDragStartY = 0;
let lineageDragOrigX = 0, lineageDragOrigY = 0;
let lineageDragMoved = false;

function _mulberry32(seed) {
  return function() {
    seed |= 0;
    seed = seed + 0x6D2B79F5 | 0;
    let t = seed;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

let _moundsCache = null;
let _moundsCacheVw = 0, _moundsCacheVh = 0;

let lineageMetric = 'count';   // 'count' | 'duration'
let _moundsItems = null;
let _moundsLastTime = performance.now();

function _moundsBuildOrUpdate() {
  const items = lineageTableItems;
  if (!items.length) { _moundsItems = []; return; }
  const sorted = [...items].sort((a, b) => b[lineageMetric] - a[lineageMetric]);

  const sideMargin = 40;
  const baseY = vh - 60;
  const topReserved = 140;
  const maxHeight = baseY - topReserved - 30;
  const maxV = Math.max(...sorted.map(it => it[lineageMetric]));

  const targets = [];
  let cx = sideMargin;
  for (let i = 0; i < sorted.length; i++) {
    const it = sorted[i];
    const v = it[lineageMetric] || 0;
    const frac = maxV > 0 ? Math.sqrt(v / maxV) : 0;
    const height = 30 + frac * maxHeight;
    const width = 60 + frac * 200;
    const moundCx = cx + width / 2;
    let seed = 0;
    for (const ch of it.key) seed = (seed * 31 + ch.charCodeAt(0)) & 0xFFFFFFFF;
    targets.push({
      key: it.key, it,
      seed: seed || 1,
      cxTarget: moundCx,
      widthTarget: width,
      heightTarget: height,
      baseY,
    });
    cx += width + 6;
  }

  if (!_moundsItems || _moundsItems.length === 0) {
    _moundsItems = targets.map(t => ({
      ...t,
      cx: t.cxTarget,
      width: t.widthTarget,
      height: t.heightTarget,
    }));
  } else {
    const byKey = new Map(_moundsItems.map(m => [m.key, m]));
    _moundsItems = targets.map(t => {
      const existing = byKey.get(t.key);
      if (existing) {
        return {
          ...t,
          cx: existing.cx,
          width: existing.width,
          height: existing.height,
        };
      } else {
        return { ...t, cx: t.cxTarget, width: t.widthTarget, height: t.heightTarget };
      }
    });
  }
  _moundsCacheVw = vw;
  _moundsCacheVh = vh;
}

function _moundsAnimate(dtMs) {
  if (!_moundsItems) return;
  const k = Math.min(1, dtMs / 1000 * 4.5);
  for (const m of _moundsItems) {
    m.cx += (m.cxTarget - m.cx) * k;
    m.width += (m.widthTarget - m.width) * k;
    m.height += (m.heightTarget - m.height) * k;
  }
}

// stable jitter cache per mound (computed once for each step)
const _moundJitterCache = new Map();
function _getJitterRow(seed, steps) {
  const key = seed + '_' + steps;
  let cached = _moundJitterCache.get(key);
  if (cached) return cached;
  const rng = _mulberry32(seed);
  cached = [];
  for (let j = 0; j <= steps; j++) {
    cached.push({
      jx: (rng() - 0.5) * 2.2,
      jy: (rng() - 0.5) * 2.6,
    });
  }
  _moundJitterCache.set(key, cached);
  return cached;
}

function _drawMound(m, time, isHover) {
  const hue = hashHue(m.key);
  const halfW = m.width / 2;
  const steps = Math.max(30, Math.floor(m.width / 6));
  const jitter = _getJitterRow(m.seed, steps);
  const baseScreenY = m.baseY * lineageScale + lineageOffY;

  ctx.beginPath();
  ctx.moveTo((m.cx - halfW) * lineageScale + lineageOffX, baseScreenY);
  for (let j = 0; j <= steps; j++) {
    const t = j / steps;
    const u = (t - 0.5) * 4.4;
    const x = m.cx - halfW + t * m.width;
    const y = m.baseY - Math.exp(-u * u * 0.5) * m.height;
    const heightFromBase = m.baseY - y;
    const factor = m.height > 0 ? Math.min(1, heightFromBase / m.height) : 0;
    const phase = m.seed * 0.0007 + j * 0.18;
    const windX = Math.sin(time * 0.0009 + phase) * 2.5 * factor;
    const windY = Math.cos(time * 0.0006 + phase * 0.6) * 1.2 * factor;
    const jt = jitter[j] || { jx: 0, jy: 0 };
    ctx.lineTo(
      (x + jt.jx + windX) * lineageScale + lineageOffX,
      (y + jt.jy + windY) * lineageScale + lineageOffY
    );
  }
  ctx.lineTo((m.cx + halfW) * lineageScale + lineageOffX, baseScreenY);
  ctx.closePath();

  ctx.fillStyle = isHover ? `hsla(${hue}, 60%, 50%, 0.7)` : `hsla(${hue}, 45%, 42%, 0.5)`;
  ctx.fill();
  ctx.strokeStyle = isHover ? `hsla(${hue}, 70%, 75%, 1)` : `hsla(${hue}, 55%, 62%, 0.85)`;
  ctx.lineWidth = isHover ? 2 : 1.3;
  ctx.lineJoin = 'round';
  ctx.stroke();
}

function renderLineageMounds() {
  const now = performance.now();
  const dtMs = Math.min(100, now - _moundsLastTime);
  _moundsLastTime = now;

  if (!_moundsItems || _moundsCacheVw !== vw || _moundsCacheVh !== vh) {
    _moundsBuildOrUpdate();
  }
  _moundsAnimate(dtMs);

  // header
  ctx.save();
  ctx.fillStyle = 'rgba(245,241,232,0.85)';
  ctx.font = '300 36px Fraunces, serif';
  ctx.textAlign = 'center';
  ctx.fillText(`${lineageTableItems.length.toLocaleString()} tables · usage lineage`, vw/2, 88);
  ctx.fillStyle = 'rgba(139,134,128,0.85)';
  ctx.font = '10px JetBrains Mono';
  const metricLabel = lineageMetric === 'count' ? 'CALL COUNT' : 'TOTAL DURATION';
  ctx.fillText(`each mound = one table · sorted by ${metricLabel} · drag to scroll · click for lineage · ${(lineageScale*100).toFixed(0)}%`, vw/2, 112);
  ctx.restore();

  // baseline
  const baseScreenY = (vh - 60) * lineageScale + lineageOffY;
  ctx.strokeStyle = 'rgba(139,134,128,0.3)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, baseScreenY);
  ctx.lineTo(vw, baseScreenY);
  ctx.stroke();

  // hover detection
  let hover = null;
  for (const m of _moundsItems) {
    const halfW = m.width / 2;
    const bx = (m.cx - halfW) * lineageScale + lineageOffX;
    const by = (m.baseY - m.height) * lineageScale + lineageOffY;
    const bw = m.width * lineageScale;
    const bh = m.height * lineageScale;
    if (mouseX >= bx && mouseX <= bx + bw && mouseY >= by && mouseY <= by + bh) {
      hover = m;
    }
  }

  // draw mounds
  for (const m of _moundsItems) {
    const halfW = m.width / 2;
    const bx = (m.cx - halfW) * lineageScale + lineageOffX;
    const bw = m.width * lineageScale;
    if (bx + bw < -20 || bx > vw + 20) continue;
    _drawMound(m, now, hover === m);
  }

  // labels
  for (const m of _moundsItems) {
    const halfW = m.width / 2;
    const bx = (m.cx - halfW) * lineageScale + lineageOffX;
    const bw = m.width * lineageScale;
    if (bx + bw < -20 || bx > vw + 20) continue;
    const isHover = (hover === m);
    const labelX = m.cx * lineageScale + lineageOffX;
    const peakY = (m.baseY - m.height) * lineageScale + lineageOffY;
    const labelY = peakY - 10;
    if (isHover || (m.width * lineageScale > 80 && m.height * lineageScale > 70)) {
      ctx.fillStyle = isHover ? 'rgba(245,241,232,1)' : 'rgba(200,190,170,0.85)';
      ctx.font = isHover ? 'bold 11px JetBrains Mono' : '9px JetBrains Mono';
      ctx.textAlign = 'center';
      const txt = m.key.length > 28 ? m.key.slice(0, 27) + '…' : m.key;
      ctx.fillText(txt, labelX, labelY);
      if (isHover) {
        ctx.fillStyle = 'rgba(232,160,74,0.95)';
        ctx.font = '9px JetBrains Mono';
        const meta = lineageMetric === 'count'
          ? `${m.it.count.toLocaleString()} calls`
          : `${fmtInterval(m.it.duration)}`;
        ctx.fillText(meta, labelX, labelY - 14);
      }
    }
  }

  lineageHover = hover ? { key: hover.key, count: hover.it.count, duration: hover.it.duration, ...hover.it } : null;
  document.getElementById('tooltip').style.display = 'none';
  canvas.style.cursor = lineageDragging ? 'grabbing' : (hover ? 'pointer' : 'grab');
}

function renderLineageTreemap() {
  const top = 160, bot = 90, side = 24;
  const rect = { x: side, y: top, w: vw - side*2, h: vh - top - bot };

  ctx.save();
  ctx.fillStyle = 'rgba(245,241,232,0.85)';
  ctx.font = '300 36px Fraunces, serif';
  ctx.textAlign = 'center';
  ctx.fillText(`${lineageTableItems.length.toLocaleString()} tables · usage lineage`, vw/2, 88);
  ctx.fillStyle = 'rgba(139,134,128,0.85)';
  ctx.font = '10px JetBrains Mono';
  const totalDur = lineageTableItems.reduce((s, it) => s + it.duration, 0);
  ctx.fillText(`${fmtInterval(totalDur)} total · sorted by duration · click a table for lineage · scroll to zoom · ${(lineageScale*100).toFixed(0)}%`, vw/2, 112);
  ctx.restore();

  if (!lineageTableItems.length) return;
  lineageRects = squarify(lineageTableItems, rect);

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, top - 30, vw, vh);
  ctx.clip();

  let hover = null;
  for (const r of lineageRects) {
    if (!r.rect || r.rect.w < 1 || r.rect.h < 1) continue;
    const sx = r.rect.x * lineageScale + lineageOffX;
    const sy = r.rect.y * lineageScale + lineageOffY;
    const sw = r.rect.w * lineageScale;
    const sh = r.rect.h * lineageScale;
    if (sx + sw < 0 || sx > vw || sy + sh < 0 || sy > vh) continue;

    const hue = hashHue(r.key);
    const isHover = mouseX >= sx && mouseX <= sx + sw && mouseY >= sy && mouseY <= sy + sh;
    if (isHover) hover = r;

    ctx.fillStyle = isHover ? `hsla(${hue}, 55%, 70%, 0.95)` : `hsla(${hue}, 45%, 50%, 0.75)`;
    ctx.fillRect(sx, sy, sw, sh);
    ctx.strokeStyle = 'rgba(10,10,12,0.5)';
    ctx.lineWidth = 1;
    ctx.strokeRect(sx, sy, sw, sh);

    if (sw > 50 && sh > 20) {
      const labelSize = Math.max(10, Math.min(24, Math.sqrt(sw * sh) / 7));
      ctx.fillStyle = 'rgba(10,10,12,0.9)';
      ctx.textAlign = 'left';
      ctx.font = `${labelSize}px JetBrains Mono`;
      const maxChars = Math.floor(sw / (labelSize * 0.6));
      const txt = r.key.length > maxChars ? r.key.slice(0, Math.max(1, maxChars-1)) + '…' : r.key;
      ctx.fillText(txt, sx + 8, sy + labelSize + 4);
      if (sh > labelSize * 2.4) {
        ctx.fillStyle = 'rgba(10,10,12,0.65)';
        ctx.font = `${Math.max(9, labelSize * 0.55)}px JetBrains Mono`;
        ctx.fillText(fmtInterval(r.duration) + ' · ' + r.count + ' calls', sx + 8, sy + labelSize + 4 + labelSize * 0.75);
      }
    }
  }
  ctx.restore();
  lineageHover = hover;

  const tt = document.getElementById('tooltip');
  if (hover) {
    document.getElementById('tt-ip').textContent = 'TABLE ' + hover.key;
    document.getElementById('tt-meta').textContent =
      `${hover.count.toLocaleString()} calls · ${fmtInterval(hover.duration)} · click for lineage`;
    document.getElementById('tt-meta').style.whiteSpace = 'nowrap';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = lineageDragging ? 'grabbing' : 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = lineageDragging ? 'grabbing' : 'grab';
  }
}

function _drawGroup(g, hoverBoxOut) {
  const c = g.call;
  const tables = c.tables || [];

  // group container
  ctx.fillStyle = g.isSelected ? 'rgba(232, 160, 74, 0.06)' : 'rgba(245, 241, 232, 0.02)';
  ctx.fillRect(g.x, g.y, g.w, g.h);
  ctx.strokeStyle = g.isSelected ? 'rgba(232, 160, 74, 0.55)' : 'rgba(139, 134, 128, 0.35)';
  ctx.lineWidth = g.isSelected ? 1.5 : 1;
  ctx.strokeRect(g.x, g.y, g.w, g.h);

  // function name header
  ctx.fillStyle = g.isSelected ? 'rgba(232, 160, 74, 1)' : 'rgba(245,241,232,0.92)';
  ctx.font = 'bold 11px JetBrains Mono';
  ctx.textAlign = 'left';
  const fn = shortFn(c.function || '');
  const headerTxt = (g.isSelected ? '★  ' : '') + fn;
  const maxHeader = Math.floor((g.w - 90) / 7);
  const shownFn = headerTxt.length > maxHeader ? headerTxt.slice(0, maxHeader-1) + '…' : headerTxt;
  ctx.fillText(shownFn, g.x + 8, g.y + 15);

  // cache badge
  if (c.cache) {
    const cacheTxt = c.cache === 'hit' ? 'CACHE HIT' : c.cache === 'miss' ? 'CACHE MISS' : 'CACHE';
    ctx.font = 'bold 8px JetBrains Mono';
    const cw = ctx.measureText(cacheTxt).width + 8;
    const cx = g.x + g.w - cw - 6;
    const cy = g.y + 5;
    const cacheColor = c.cache === 'hit' ? 'rgba(232, 160, 74, 0.85)' : c.cache === 'miss' ? 'rgba(94, 192, 192, 0.85)' : 'rgba(160,160,160,0.7)';
    ctx.fillStyle = cacheColor;
    ctx.fillRect(cx, cy, cw, 13);
    ctx.fillStyle = 'rgba(10,10,12,0.95)';
    ctx.textAlign = 'center';
    ctx.fillText(cacheTxt, cx + cw/2, cy + 10);
  }

  if (!tables.length) return [];

  // === VERTICAL table stack ===
  const tableH = 26;
  const tableW = Math.min(190, g.w - 24);
  const relGap = 28;  // vertical space for relation label
  const n = Math.min(tables.length, 3);
  const shownTables = tables.slice(0, n);
  const tableX = g.x + (g.w - tableW) / 2;
  const tableYStart = g.y + 30;

  // relations
  const visibleIdx = new Map();
  shownTables.forEach((t, i) => visibleIdx.set(t, i));
  const rels = [];
  for (const [ta, ka, tb, kb] of (c.join_pairs || [])) {
    const ai = visibleIdx.get(ta);
    const bi = visibleIdx.get(tb);
    if (ai != null && bi != null && ai !== bi) {
      const lo = Math.min(ai, bi), hi = Math.max(ai, bi);
      const label = ai < bi ? `${ka} = ${kb}` : `${kb} = ${ka}`;
      rels.push({ from: lo, to: hi, type: 'join', label });
    }
  }
  for (const [a, b] of (c.union_pairs || [])) {
    const ai = visibleIdx.get(a);
    const bi = visibleIdx.get(b);
    if (ai != null && bi != null && ai !== bi) {
      const lo = Math.min(ai, bi), hi = Math.max(ai, bi);
      rels.push({ from: lo, to: hi, type: 'union', label: '+' });
    }
  }

  // vertical relation lines (between adjacent boxes)
  for (const r of rels) {
    if (r.to - r.from > 1) continue;
    const fromY = tableYStart + r.from * (tableH + relGap) + tableH;
    const toY = tableYStart + r.to * (tableH + relGap);
    const lineX = tableX + tableW / 2;
    ctx.strokeStyle = r.type === 'join' ? 'rgba(217, 130, 100, 0.9)' : 'rgba(140, 200, 220, 0.9)';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(lineX, fromY);
    ctx.lineTo(lineX, toY);
    ctx.stroke();
  }

  // table boxes (stacked)
  const hits = [];
  for (let i = 0; i < n; i++) {
    const t = shownTables[i];
    const isSelected = t === lineageSelected;
    const tx = tableX;
    const ty = tableYStart + i * (tableH + relGap);

    const hue = hashHue(t);
    const isHover = mouseX >= tx && mouseX <= tx + tableW && mouseY >= ty && mouseY <= ty + tableH;
    if (isHover && !isSelected) hoverBoxOut.box = { table: t };

    if (isSelected) {
      ctx.fillStyle = `hsla(${hue}, 65%, 60%, 0.98)`;
      ctx.fillRect(tx, ty, tableW, tableH);
      ctx.strokeStyle = 'rgba(245,241,232,0.95)';
      ctx.lineWidth = 2.5;
      ctx.strokeRect(tx - 1, ty - 1, tableW + 2, tableH + 2);
      ctx.strokeStyle = 'rgba(232, 160, 74, 0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(tx - 4, ty - 4, tableW + 8, tableH + 8);
    } else {
      ctx.fillStyle = isHover ? `hsla(${hue}, 50%, 55%, 0.95)` : `hsla(${hue}, 40%, 42%, 0.85)`;
      ctx.fillRect(tx, ty, tableW, tableH);
      ctx.strokeStyle = 'rgba(10,10,12,0.6)';
      ctx.lineWidth = 1;
      ctx.strokeRect(tx, ty, tableW, tableH);
    }

    ctx.fillStyle = 'rgba(10,10,12,1)';
    ctx.font = isSelected ? 'bold 13px JetBrains Mono' : '10px JetBrains Mono';
    ctx.textAlign = 'center';
    const charW = isSelected ? 7.5 : 6;
    const maxLen = Math.floor((tableW - 10) / charW);
    const shownT = t.length > maxLen ? t.slice(0, maxLen-1) + '…' : t;
    ctx.fillText(shownT, tx + tableW/2, ty + tableH/2 + (isSelected ? 5 : 4));

    hits.push({ table: t, rect: { x: tx, y: ty, w: tableW, h: tableH } });
  }

  // relation labels (centered on vertical line)
  for (const r of rels) {
    if (r.to - r.from > 1) continue;
    const fromY = tableYStart + r.from * (tableH + relGap) + tableH;
    const toY = tableYStart + r.to * (tableH + relGap);
    const midY = (fromY + toY) / 2;
    const labelX = tableX + tableW / 2;

    if (r.type === 'join') {
      ctx.font = '9px JetBrains Mono';
      const labelW = ctx.measureText(r.label).width + 10;
      ctx.fillStyle = 'rgba(18,14,12,0.95)';
      ctx.fillRect(labelX - labelW/2, midY - 8, labelW, 16);
      ctx.strokeStyle = 'rgba(217, 130, 100, 0.8)';
      ctx.lineWidth = 1;
      ctx.strokeRect(labelX - labelW/2, midY - 8, labelW, 16);
      ctx.fillStyle = 'rgba(232, 180, 140, 1)';
      ctx.textAlign = 'center';
      ctx.fillText(r.label, labelX, midY + 3);
    } else {
      ctx.fillStyle = 'rgba(18,14,12,0.95)';
      ctx.fillRect(labelX - 13, midY - 13, 26, 26);
      ctx.strokeStyle = 'rgba(140, 200, 220, 0.8)';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(labelX - 13, midY - 13, 26, 26);
      ctx.fillStyle = 'rgba(140, 200, 220, 1)';
      ctx.font = 'bold 20px JetBrains Mono';
      ctx.textAlign = 'center';
      ctx.fillText('+', labelX, midY + 7);
    }
  }

  // stack end Y
  const stackEnd = tableYStart + n * tableH + (n-1) * relGap;

  // PREV-SELECT → THIS-WHERE carry-over (right side)
  if (g.prevCall) {
    const prevSelect = new Set(g.prevCall.select_cols || []);
    const thisWhereCols = Object.keys(c.where_values || {});
    const carry = thisWhereCols.filter(col => prevSelect.has(col));
    const rightX = tableX + tableW + 12;
    const rightW = g.x + g.w - rightX - 8;
    if (carry.length && rightW > 50) {
      let ry = g.y + 28;
      ctx.fillStyle = 'rgba(90, 160, 210, 0.95)';
      ctx.font = 'bold 9px JetBrains Mono';
      ctx.textAlign = 'left';
      ctx.fillText('PREV →', rightX, ry);
      ry += 12;
      ctx.fillStyle = 'rgba(140, 180, 220, 0.9)';
      ctx.font = '9px JetBrains Mono';
      const maxChars = Math.max(4, Math.floor(rightW / 6));
      for (const col of carry.slice(0, 14)) {
        if (ry >= g.y + g.h - 6) break;
        const t = col.length > maxChars ? col.slice(0, maxChars-1) + '…' : col;
        ctx.fillText(t, rightX, ry);
        ry += 11;
      }
      if (carry.length > 14 && ry < g.y + g.h - 6) {
        ctx.fillStyle = 'rgba(139,134,128,0.7)';
        ctx.font = '8px JetBrains Mono';
        ctx.fillText(`+ ${carry.length - 14} more`, rightX, ry);
      }
    }
  }

  if (tables.length > n) {
    ctx.fillStyle = 'rgba(139,134,128,0.7)';
    ctx.font = '8px JetBrains Mono';
    ctx.textAlign = 'left';
    ctx.fillText(`+ ${tables.length - n} more tables`, g.x + 8, stackEnd + 12);
  }

  // WHERE values — show as much as fits
  const wv = c.where_values || {};
  const wvEntries = Object.entries(wv);
  if (wvEntries.length) {
    let y = stackEnd + (tables.length > n ? 24 : 16);
    ctx.fillStyle = 'rgba(170, 200, 140, 0.95)';
    ctx.font = 'bold 9px JetBrains Mono';
    ctx.textAlign = 'left';
    ctx.fillText('WHERE', g.x + 8, y);
    y += 12;
    ctx.font = '9px JetBrains Mono';
    ctx.fillStyle = 'rgba(170, 200, 140, 0.88)';
    const maxChars = Math.floor((g.w - 16) / 5.8);
    let shownCols = 0;
    for (const [col, vals] of wvEntries) {
      if (y >= g.y + g.h - 4) {
        const left = wvEntries.length - shownCols;
        if (left > 0) {
          ctx.fillStyle = 'rgba(139,134,128,0.7)';
          ctx.font = '8px JetBrains Mono';
          ctx.fillText(`+ ${left} more columns`, g.x + 8, y);
        }
        break;
      }
      const valArr = vals.slice(0, 10);
      const txt = `${col} = '${valArr.join("', '")}'` + (vals.length > 10 ? ` +${vals.length-10}` : '');
      const shown = txt.length > maxChars ? txt.slice(0, maxChars-1) + '…' : txt;
      ctx.fillText(shown, g.x + 8, y);
      y += 11;
      shownCols++;
    }
  }

  return hits;
}

function renderLineageDetail() {
  if (!lineageSelected) return;
  const patterns = computeLineagePatterns(lineageSelected, lineageWindow);
  const totalSessions = patterns.reduce((s, p) => s + p.count, 0);

  // header
  ctx.save();
  ctx.fillStyle = 'rgba(245,241,232,0.85)';
  ctx.font = '300 28px Fraunces, serif';
  ctx.textAlign = 'center';
  ctx.fillText('Lineage of ' + lineageSelected, vw/2, 50);
  ctx.fillStyle = 'rgba(139,134,128,0.85)';
  ctx.font = '10px JetBrains Mono';
  ctx.fillText(`${patterns.length} unique paths · ${totalSessions} sessions · prev / SELECTED / next · click a table to navigate · ESC to back`, vw/2, 72);
  ctx.restore();

  // legend
  ctx.save();
  ctx.font = '9px JetBrains Mono';
  ctx.textAlign = 'left';
  let lx = 24;
  const ly = 90;
  ctx.fillStyle = 'rgba(217, 130, 100, 0.95)'; ctx.fillRect(lx, ly-4, 14, 2);
  ctx.fillStyle = 'rgba(180,180,180,0.85)'; ctx.fillText('JOIN', lx+18, ly+1); lx += 56;
  ctx.fillStyle = 'rgba(140, 200, 220, 0.95)'; ctx.fillRect(lx, ly-4, 14, 2);
  ctx.fillStyle = 'rgba(180,180,180,0.85)'; ctx.fillText('UNION (+)', lx+18, ly+1); lx += 86;
  ctx.fillStyle = 'rgba(135, 206, 250, 0.55)'; ctx.fillRect(lx, ly-4, 14, 2);
  ctx.fillStyle = 'rgba(180,180,180,0.85)'; ctx.fillText('TIME →', lx+18, ly+1);
  ctx.restore();

  const maxPatterns = Math.min(patterns.length, 3);
  if (maxPatterns === 0) {
    ctx.fillStyle = 'rgba(139,134,128,0.7)';
    ctx.font = '12px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText('No session paths found for this table', vw/2, vh/2);
    return;
  }

  const cardTop = 108;
  const cardGap = 10;
  const cardHeight = (vh - cardTop - 30 - (maxPatterns-1)*cardGap) / maxPatterns;

  const hoverOut = { box: null };

  for (let pi = 0; pi < maxPatterns; pi++) {
    const p = patterns[pi];
    const cardY = cardTop + pi * (cardHeight + cardGap);
    const cardX = 20;
    const cardW = vw - 40;

    ctx.fillStyle = 'rgba(28, 26, 24, 0.55)';
    ctx.fillRect(cardX, cardY, cardW, cardHeight);

    ctx.fillStyle = 'rgba(232,160,74,0.9)';
    ctx.font = 'bold 11px JetBrains Mono';
    ctx.textAlign = 'left';
    const pct = ((p.count / totalSessions) * 100).toFixed(1);
    const positionTag = p.isStart && p.isEnd ? '· complete'
                      : p.isStart ? '· starts here'
                      : p.isEnd ? '· ends here'
                      : '· mid-session';
    ctx.fillText(`PATTERN ${pi+1}  ·  ${p.count} sessions (${pct}%)  ${positionTag}`, cardX + 8, cardY + 16);

    const path = p.sample;
    const groupGap = 36;
    const groupAreaY = cardY + 24;
    const groupAreaH = cardHeight - 28;
    const groupW = (cardW - 16 - (path.length-1) * groupGap) / path.length;

    for (let i = 0; i < path.length; i++) {
      const c = path[i];
      const g = {
        call: c,
        prevCall: i > 0 ? path[i-1] : null,
        x: cardX + 8 + i * (groupW + groupGap),
        y: groupAreaY,
        w: groupW,
        h: groupAreaH,
        isSelected: i === p.selectedIdx,
      };

      // arrow to next group (time flow)
      if (i < path.length - 1) {
        const ax1 = g.x + g.w + 4;
        const ax2 = g.x + g.w + groupGap - 6;
        const ay = groupAreaY + groupAreaH / 2;
        ctx.strokeStyle = 'rgba(135, 206, 250, 0.55)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(ax1, ay);
        ctx.lineTo(ax2, ay);
        ctx.stroke();
        ctx.fillStyle = 'rgba(135, 206, 250, 0.7)';
        ctx.beginPath();
        ctx.moveTo(ax2, ay);
        ctx.lineTo(ax2 - 5, ay - 4);
        ctx.lineTo(ax2 - 5, ay + 4);
        ctx.closePath();
        ctx.fill();
      }

      _drawGroup(g, hoverOut);
    }
  }

  lineageDetailHover = hoverOut.box;
  canvas.style.cursor = hoverOut.box ? 'pointer' : 'default';
  document.getElementById('tooltip').style.display = 'none';
}

function renderLineageView() {
  if (lineageMode === 'treemap') renderLineageMounds();
  else renderLineageDetail();
}

canvas.addEventListener('wheel', e => {
  if (mainView === 'users') {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.88 : 1.13;
    const newScale = Math.max(0.4, Math.min(40, usersScale * factor));
    if (newScale === usersScale) return;
    const wx = (e.clientX - usersOffX) / usersScale;
    const wy = (e.clientY - usersOffY) / usersScale;
    usersScale = newScale;
    usersOffX = e.clientX - wx * usersScale;
    usersOffY = e.clientY - wy * usersScale;
  } else if (mainView === 'lineage' && lineageMode === 'treemap') {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.88 : 1.13;
    const newScale = Math.max(0.4, Math.min(40, lineageScale * factor));
    if (newScale === lineageScale) return;
    const wx = (e.clientX - lineageOffX) / lineageScale;
    const wy = (e.clientY - lineageOffY) / lineageScale;
    lineageScale = newScale;
    lineageOffX = e.clientX - wx * lineageScale;
    lineageOffY = e.clientY - wy * lineageScale;
  }
}, { passive: false });

canvas.addEventListener('mousedown', e => {
  if (mainView === 'users') {
    usersDragging = true;
    usersDragStartX = e.clientX; usersDragStartY = e.clientY;
    usersDragOrigX = usersOffX; usersDragOrigY = usersOffY;
    usersDragMoved = false;
  } else if (mainView === 'lineage' && lineageMode === 'treemap') {
    lineageDragging = true;
    lineageDragStartX = e.clientX; lineageDragStartY = e.clientY;
    lineageDragOrigX = lineageOffX; lineageDragOrigY = lineageOffY;
    lineageDragMoved = false;
  }
});
canvas.addEventListener('mousemove', e => {
  if (usersDragging) {
    const dx = e.clientX - usersDragStartX;
    const dy = e.clientY - usersDragStartY;
    if (!usersDragMoved && Math.hypot(dx, dy) > 4) usersDragMoved = true;
    if (usersDragMoved) {
      usersOffX = usersDragOrigX + dx;
      usersOffY = usersDragOrigY + dy;
    }
  }
  if (lineageDragging) {
    const dx = e.clientX - lineageDragStartX;
    const dy = e.clientY - lineageDragStartY;
    if (!lineageDragMoved && Math.hypot(dx, dy) > 4) lineageDragMoved = true;
    if (lineageDragMoved) {
      lineageOffX = lineageDragOrigX + dx;
      lineageOffY = lineageDragOrigY + dy;
    }
  }
});
canvas.addEventListener('mouseup', () => { usersDragging = false; lineageDragging = false; });
canvas.addEventListener('mouseleave', () => { usersDragging = false; lineageDragging = false; });

// --- EDGES ---
// JOIN edges: tables that appear in the same call (same SQL flow)
// SESSION edges: tables that appear in consecutive calls of the same (ip,port)
const particleByTable = {};
for (const p of tableParticles) particleByTable[p.table] = p;

const joinEdges = {};      // 'a__b' -> count
const sessionEdges = {};   // 'a__b' -> count

for (const c of CALLS) {
  const tbs = c.tables || [];
  for (let i = 0; i < tbs.length; i++) {
    for (let j = i+1; j < tbs.length; j++) {
      const a = tbs[i], b = tbs[j];
      if (a === b) continue;
      const k = a < b ? a + '__' + b : b + '__' + a;
      joinEdges[k] = (joinEdges[k] || 0) + 1;
    }
  }
}

const _portCalls = {};
for (const c of CALLS) {
  const key = (c.ip || '?') + ':' + (c.port || '?');
  (_portCalls[key] = _portCalls[key] || []).push(c);
}
for (const key of Object.keys(_portCalls)) {
  const arr = _portCalls[key].sort((a, b) => (a._start || 0) - (b._start || 0));
  for (let i = 0; i < arr.length - 1; i++) {
    const ta = arr[i].tables || [];
    const tb = arr[i+1].tables || [];
    if (!ta.length || !tb.length) continue;
    for (const a of ta) {
      for (const b of tb) {
        if (a === b) continue;
        const k = a < b ? a + '__' + b : b + '__' + a;
        sessionEdges[k] = (sessionEdges[k] || 0) + 1;
      }
    }
  }
}

// remove session edges that are also join edges — JOIN takes priority
for (const k of Object.keys(sessionEdges)) {
  if (joinEdges[k]) delete sessionEdges[k];
}

// max counts for opacity scaling
const _joinMax = Math.max(1, ...Object.values(joinEdges));
const _sessMax = Math.max(1, ...Object.values(sessionEdges));

const searchInput = document.getElementById('search');
searchInput.addEventListener('input', e => {
  filterQuery = e.target.value.trim().toLowerCase();
  recomputeVisibleTables();
});
function ipVisible(s) {
  if (!filterQuery) return true;
  return (s || '').toLowerCase().includes(filterQuery);
}

// for tables view: filter shows matched table + its 1-hop neighbors via edges
let visibleTablesNow = null;
function isDirectMatch(name) {
  if (!filterQuery) return true;
  return (name || '').toLowerCase().includes(filterQuery);
}
function recomputeVisibleTables() {
  if (!filterQuery) { visibleTablesNow = null; return; }
  const direct = new Set();
  for (const p of tableParticles) {
    if (isDirectMatch(p.table)) direct.add(p.table);
  }
  const all = new Set(direct);
  for (const k of Object.keys(joinEdges)) {
    const [a, b] = k.split('__');
    if (direct.has(a)) all.add(b);
    if (direct.has(b)) all.add(a);
  }
  for (const k of Object.keys(sessionEdges)) {
    const [a, b] = k.split('__');
    if (direct.has(a)) all.add(b);
    if (direct.has(b)) all.add(a);
  }
  visibleTablesNow = all;
}
function tableInView(name) {
  if (!visibleTablesNow) return true;
  return visibleTablesNow.has(name);
}

let mouseX = -100, mouseY = -100;
canvas.addEventListener('mousemove', e => { mouseX = e.clientX; mouseY = e.clientY; });

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (mainView === 'lineage' && lineageMode === 'detail') {
      lineageMode = 'treemap';
      lineageSelected = null;
      return;
    }
  }
});

// --- TOGGLE ---
document.querySelectorAll('.view-toggle button').forEach(btn => {
  btn.onclick = () => {
    if (viewMode === 'ip_timeline') backToParticles();
    mainView = btn.dataset.view;
    document.querySelectorAll('.view-toggle button').forEach(b =>
      b.classList.toggle('active', b === btn));
    if (mainView === 'stream') {
      if (!selectedStreamTable && tableList.length) {
        selectStreamTable(tableList[0].table);
        document.getElementById('stream-table-input').value = tableList[0].table;
      } else {
        streamReset();
      }
    }
    if (mainView === 'users') resetUsersZoom();
    if (mainView === 'lineage') {
      lineageMode = 'treemap';
      lineageSelected = null;
      resetLineageZoom();
    }
    refreshHeader();
    closePanel();
    searchInput.value = ''; filterQuery = ''; recomputeVisibleTables();
  };
});

function refreshHeader() {
  if (viewMode === 'ip_timeline') return;
  if (mainView === 'ips') {
    document.getElementById('title').textContent = 'User Flows';
    document.getElementById('title').classList.remove('ip-mode');
    document.getElementById('subtitle').textContent = 'EACH PARTICLE = ONE IP · CLICK TO EXPLORE';
    document.getElementById('stats').innerHTML = `
      <span class="n">${ipList.length}</span>IPs &nbsp;·&nbsp;
      <span class="n">${CALLS.length.toLocaleString()}</span>CALLS`;
    document.getElementById('search').placeholder = 'filter by ip...';
    document.getElementById('bottom-controls').classList.remove('on');
    document.getElementById('stream-controls').classList.remove('on');
    document.getElementById('users-controls').classList.remove('on');
    document.getElementById('lineage-controls').classList.remove('on');
    document.getElementById('search-box').classList.add('on');
    document.getElementById('hint').textContent = 'CLICK TO INSPECT';
  } else if (mainView === 'tables') {
    document.getElementById('title').textContent = 'Table Flows';
    document.getElementById('title').classList.remove('ip-mode');
    document.getElementById('subtitle').textContent = 'EACH PARTICLE = ONE TABLE · CLICK TO SEE WHO USES IT';
    document.getElementById('stats').innerHTML = `
      <span class="n">${tableList.length}</span>TABLES &nbsp;·&nbsp;
      <span class="n">${CALLS.length.toLocaleString()}</span>CALLS`;
    document.getElementById('search').placeholder = 'filter by table...';
    document.getElementById('bottom-controls').classList.add('on');
    document.getElementById('stream-controls').classList.remove('on');
    document.getElementById('users-controls').classList.remove('on');
    document.getElementById('lineage-controls').classList.remove('on');
    document.getElementById('search-box').classList.add('on');
    document.getElementById('hint').textContent = 'CLICK TO INSPECT';
  } else if (mainView === 'stream') {
    document.getElementById('title').textContent = 'Stream';
    document.getElementById('title').classList.remove('ip-mode');
    document.getElementById('subtitle').textContent = 'LIVE REPLAY · EACH PULSE = ONE CALL · COLOR = CACHE STATE';
    document.getElementById('stats').innerHTML = '';
    document.getElementById('bottom-controls').classList.remove('on');
    document.getElementById('stream-controls').classList.add('on');
    document.getElementById('users-controls').classList.remove('on');
    document.getElementById('lineage-controls').classList.remove('on');
    document.getElementById('search-box').classList.remove('on');
    document.getElementById('hint').textContent = '';
  } else if (mainView === 'users') {
    document.getElementById('title').textContent = 'Users';
    document.getElementById('title').classList.remove('ip-mode');
    document.getElementById('subtitle').textContent = 'MAPPED USERS BY CALL COUNT · CLICK A RECT FOR DETAILS';
    document.getElementById('stats').innerHTML = '';
    document.getElementById('bottom-controls').classList.remove('on');
    document.getElementById('stream-controls').classList.remove('on');
    document.getElementById('users-controls').classList.add('on');
    document.getElementById('lineage-controls').classList.remove('on');
    document.getElementById('search-box').classList.remove('on');
    document.getElementById('hint').textContent = 'CLICK A RECT TO EXPLORE';
  } else if (mainView === 'lineage') {
    document.getElementById('title').textContent = 'Lineage';
    document.getElementById('title').classList.remove('ip-mode');
    document.getElementById('subtitle').textContent = 'USAGE LINEAGE · MOUNDS BY TABLE · CLICK FOR JOIN + ADJACENCY';
    document.getElementById('stats').innerHTML = '';
    document.getElementById('bottom-controls').classList.remove('on');
    document.getElementById('stream-controls').classList.remove('on');
    document.getElementById('users-controls').classList.remove('on');
    document.getElementById('lineage-controls').classList.toggle('on', lineageMode === 'treemap');
    document.getElementById('search-box').classList.remove('on');
    document.getElementById('hint').textContent = 'CLICK A TABLE · ESC TO GO BACK';
  }
  document.getElementById('legend').classList.remove('on');
  document.getElementById('back-btn').classList.remove('on');
}
refreshHeader();

// --- IP PARTICLES ---
function renderIpParticles() {
  let hoverP = null;
  for (const p of ipParticles) {
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
    const ports = new Set(hoverP.calls.map(c => c.port));
    document.getElementById('tt-meta').textContent = `${hoverP.count.toLocaleString()} calls · ${ports.size} sessions`;
    document.getElementById('tt-meta').style.whiteSpace = 'nowrap';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px'; tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none'; canvas.style.cursor = 'crosshair';
  }
  canvas._hover = hoverP;
}

// --- TABLE PARTICLES ---
function renderTableParticles() {
  // edges — controlled by SHOW LINKS button (independent of gather)
  if (showEdges) {
    // session edges (sky blue) first
    ctx.lineWidth = 1;
    for (const k of Object.keys(sessionEdges)) {
      const [a, b] = k.split('__');
      const pa = particleByTable[a], pb = particleByTable[b];
      if (!pa || !pb) continue;
      // when filtering: at least one endpoint must be a direct match
      if (filterQuery && !isDirectMatch(a) && !isDirectMatch(b)) continue;
      const cnt = sessionEdges[k];
      const alpha = Math.min(0.5, 0.05 + (cnt / _sessMax) * 0.45);
      ctx.strokeStyle = `rgba(135, 206, 250, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
    // join edges (red) on top
    for (const k of Object.keys(joinEdges)) {
      const [a, b] = k.split('__');
      const pa = particleByTable[a], pb = particleByTable[b];
      if (!pa || !pb) continue;
      if (filterQuery && !isDirectMatch(a) && !isDirectMatch(b)) continue;
      const cnt = joinEdges[k];
      const alpha = Math.min(0.75, 0.1 + (cnt / _joinMax) * 0.65);
      ctx.strokeStyle = `rgba(217, 96, 96, ${alpha})`;
      ctx.lineWidth = 1 + Math.min(2, (cnt / _joinMax) * 2);
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
    ctx.lineWidth = 1;
  }

  // domain labels — only when clustered
  if (clustered) {
    ctx.save();
    ctx.font = '600 11px JetBrains Mono';
    ctx.fillStyle = 'rgba(245,241,232,0.4)';
    ctx.textAlign = 'center';
    for (const [domain, center] of Object.entries(domainCenters)) {
      ctx.fillText(domain.toUpperCase(), center.x, center.y - 90);
    }
    ctx.restore();
  }

  let hoverP = null;
  for (const p of tableParticles) {
    if (!tableInView(p.table)) continue;

    // attraction to domain center — only when clustered
    if (clustered) {
      const center = domainCenters[p.domain];
      if (center) {
        const dx = center.x - p.x;
        const dy = center.y - p.y;
        const dist = Math.hypot(dx, dy) || 1;
        const force = Math.min(0.05, dist * 0.0006);
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
      }
    }
    p.vx *= 0.97; p.vy *= 0.97;
    p.vx += (Math.random() - 0.5) * 0.04;
    p.vy += (Math.random() - 0.5) * 0.04;

    p.x += p.vx; p.y += p.vy;
    if (p.x < p.r) { p.x = p.r; p.vx *= -0.3; }
    if (p.x > vw - p.r) { p.x = vw - p.r; p.vx *= -0.3; }
    if (p.y < p.r) { p.y = p.r; p.vy *= -0.3; }
    if (p.y > vh - p.r) { p.y = vh - p.r; p.vy *= -0.3; }

    const d = Math.hypot(p.x - mouseX, p.y - mouseY);
    p.hover = d < p.r + 4;
    if (p.hover) hoverP = p;

    const baseCol = `hsla(${p.hue}, 55%, 65%`;
    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 2.5);
    grad.addColorStop(0, p.hover ? 'rgba(245,241,232,0.5)' : `${baseCol}, 0.25)`);
    grad.addColorStop(1, `${baseCol}, 0)`);
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 2.5, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = p.hover ? '#f5f1e8' : `${baseCol}, 0.85)`;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
  }
  const tt = document.getElementById('tooltip');
  if (hoverP) {
    document.getElementById('tt-ip').textContent = hoverP.table;
    const fns = new Set(hoverP.calls.map(c => c.function));
    const ips = new Set(hoverP.calls.map(c => c.ip));
    document.getElementById('tt-meta').textContent = `${(hoverP.domain||'').toUpperCase()} · ${hoverP.count.toLocaleString()} calls · ${fns.size} functions · ${ips.size} IPs`;
    document.getElementById('tt-meta').style.whiteSpace = 'nowrap';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px'; tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none'; canvas.style.cursor = 'crosshair';
  }
  canvas._hover = hoverP;
}

// --- IP TIMELINE (unchanged from v4) ---
function fmtTime(t) {
  const d = new Date(t); const p = n => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtInterval(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  if (ms < 60000) return (ms/1000).toFixed(1) + 's';
  if (ms < 3600000) return (ms/60000).toFixed(1) + 'm';
  return (ms/3600000).toFixed(1) + 'h';
}

function analyzeSession(calls) {
  const sorted = [...calls].sort((a, b) => (a._start || 0) - (b._start || 0));
  const n = sorted.length;
  const fnCnt = {};
  for (const c of sorted) fnCnt[c.function] = (fnCnt[c.function] || 0) + 1;
  const fnEntries = Object.entries(fnCnt).sort((a, b) => b[1] - a[1]);
  const topFn = fnEntries[0] || [null, 0];
  let pattern = 'SHORT', intervalMean = null, intervalCV = null, intervalMin = null, intervalMax = null;
  if (n >= 3) {
    const intervals = [];
    for (let i = 1; i < n; i++) { const dt = sorted[i]._start - sorted[i-1]._start; if (dt > 0) intervals.push(dt); }
    if (intervals.length >= 2) {
      const mean = intervals.reduce((a, b) => a + b, 0) / intervals.length;
      const variance = intervals.reduce((a, b) => a + (b - mean) ** 2, 0) / intervals.length;
      const std = Math.sqrt(variance);
      const cv = mean > 0 ? std / mean : 0;
      intervalMean = mean; intervalCV = cv;
      intervalMin = Math.min(...intervals); intervalMax = Math.max(...intervals);
      if (cv < 0.25) pattern = 'AUTO'; else if (cv < 0.75) pattern = 'MIXED'; else pattern = 'HUMAN';
    }
  }
  return { n, uniqueFns: fnEntries.length, topFn: topFn[0], topFnCount: topFn[1], pattern, intervalMean, intervalCV, intervalMin, intervalMax };
}
const PATTERN_COLOR = { AUTO: '#6fb3b3', HUMAN: '#d99a55', MIXED: '#8b8680', SHORT: '#4a4944' };

let _ipCache = null;
function buildIpCache(ip) {
  const calls = byIP[ip] || [];
  const tMin = GLOBAL_TMIN, tMax = GLOBAL_TMAX;
  const byPort = {};
  for (const c of calls) { const k = c.port || '?'; (byPort[k] = byPort[k] || []).push(c); }
  // pre-compute first call time per port (avoid Math.min(...arr) inside sort)
  const portFirst = {};
  for (const k of Object.keys(byPort)) {
    let m = Infinity;
    for (const c of byPort[k]) if (c._start != null && c._start < m) m = c._start;
    portFirst[k] = m;
  }
  const ports = Object.keys(byPort).sort((a, b) => portFirst[a] - portFirst[b]);
  const portStats = {};
  for (const p of ports) portStats[p] = analyzeSession(byPort[p]);
  return { ip, ports, byPort, portStats, tMin, tMax };
}

const TL_LEFT = 260, TL_TOP = 100, TL_BOT = 60, TL_PADR = 32;
function tlLayout(cache) {
  const w = vw - TL_LEFT - TL_PADR;
  const h = vh - TL_TOP - TL_BOT;
  const rowH = Math.max(12, Math.min(56, h / Math.max(1, cache.ports.length)));
  return { w, h, rowH };
}

function shortFn(fn) {
  if (!fn) return '-';
  const hash = fn.indexOf('#'); if (hash >= 0) return fn.slice(hash + 1);
  const dot = fn.lastIndexOf('.'); if (dot >= 0) return fn.slice(dot + 1);
  return fn.length > 24 ? fn.slice(0, 22) + '..' : fn;
}

function renderIpTimeline() {
  if (!selectedIP) return;
  if (!_ipCache || _ipCache.ip !== selectedIP) _ipCache = buildIpCache(selectedIP);
  const cache = _ipCache;
  if (!cache.ports.length) return;
  const { w, h, rowH } = tlLayout(cache);
  const xScale = t => TL_LEFT + (t - cache.tMin) / (cache.tMax - cache.tMin || 1) * w;

  ctx.font = '10px JetBrains Mono'; ctx.strokeStyle = '#1f2127';
  const ticks = 8;
  for (let i = 0; i <= ticks; i++) {
    const x = TL_LEFT + w * i / ticks;
    const t = cache.tMin + (cache.tMax - cache.tMin) * i / ticks;
    ctx.beginPath(); ctx.moveTo(x, TL_TOP); ctx.lineTo(x, TL_TOP + h); ctx.stroke();
    ctx.fillStyle = '#5a5852'; ctx.fillText(fmtTime(t), x - 18, TL_TOP - 10);
  }
  ctx.strokeStyle = '#26282f';
  ctx.beginPath(); ctx.moveTo(TL_LEFT, TL_TOP); ctx.lineTo(TL_LEFT + w, TL_TOP); ctx.stroke();

  let hoverCall = null;
  const hitC = 'rgba(232,160,74,0.78)';
  const missC = 'rgba(94,192,192,0.78)';
  const noneC = 'rgba(140,140,140,0.55)';

  for (let i = 0; i < cache.ports.length; i++) {
    const port = cache.ports[i];
    const y = TL_TOP + i * rowH;
    const calls = cache.byPort[port];
    const stat = cache.portStats[port];
    const patternCol = PATTERN_COLOR[stat.pattern];

    if (i % 2 === 0) { ctx.fillStyle = 'rgba(255,255,255,0.015)'; ctx.fillRect(TL_LEFT, y, w, rowH); }

    if (rowH >= 32) {
      ctx.fillStyle = '#f5f1e8'; ctx.font = '11px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + 13);
      ctx.fillStyle = patternCol; ctx.font = 'bold 9px JetBrains Mono';
      let patText = stat.pattern;
      if (stat.intervalMean != null) patText += '  every ~' + fmtInterval(stat.intervalMean);
      ctx.fillText(patText, 14, y + 26);
      ctx.fillStyle = '#8b8680'; ctx.font = '9px JetBrains Mono';
      const topShort = stat.topFn ? shortFn(stat.topFn) : '-';
      ctx.fillText(`${stat.n}c · ${topShort} ×${stat.topFnCount}`, 14, y + 38);
    } else if (rowH >= 18) {
      ctx.fillStyle = '#f5f1e8'; ctx.font = '11px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + rowH/2 - 2);
      ctx.fillStyle = patternCol; ctx.font = 'bold 9px JetBrains Mono';
      ctx.fillText(`${stat.n}c · ${stat.pattern}${stat.intervalMean != null ? ' '+fmtInterval(stat.intervalMean) : ''}`, 14, y + rowH/2 + 10);
    } else {
      ctx.fillStyle = '#f5f1e8'; ctx.font = '10px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + rowH/2 + 3);
      ctx.fillStyle = patternCol;
      ctx.beginPath(); ctx.arc(85, y + rowH/2, 3, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#5a5852'; ctx.font = '9px JetBrains Mono';
      ctx.fillText(stat.n + 'c', 95, y + rowH/2 + 3);
    }

    for (const c of calls) {
      if (c._start == null) continue;
      const x1 = xScale(c._start); const x2 = xScale(c._end);
      const barW = Math.max(2, x2 - x1);
      const barH = Math.max(4, rowH - 6);
      const barY = y + (rowH - barH) / 2;
      ctx.fillStyle = c.cache === 'hit' ? hitC : c.cache === 'miss' ? missC : noneC;
      ctx.fillRect(x1, barY, barW, barH);
      if (mouseX >= x1 - 2 && mouseX <= x1 + barW + 2 && mouseY >= barY && mouseY <= barY + barH) hoverCall = c;
    }
  }

  const tt = document.getElementById('tooltip');
  if (hoverCall) {
    const stat = cache.portStats[hoverCall.port];
    document.getElementById('tt-ip').textContent = hoverCall.function || '(unknown)';
    const meta = [
      `:${hoverCall.port} · ${fmtTime(hoverCall._start)} · ${hoverCall.duration_ms != null ? hoverCall.duration_ms.toFixed(0)+'ms' : '-'}`,
      hoverCall.cache ? `CACHE ${hoverCall.cache.toUpperCase()}${hoverCall.cache_key ? ' · '+hoverCall.cache_key : ''}` : 'NO CACHE',
      hoverCall.n_sqls ? `${hoverCall.n_sqls} sql` : '',
      `─────`,
      `SESSION: ${stat.n} calls · ${stat.uniqueFns} unique fn · ${stat.pattern}`,
      stat.intervalMean != null ? `interval ~${fmtInterval(stat.intervalMean)} (cv ${stat.intervalCV.toFixed(2)})` : '',
      stat.topFn && stat.topFnCount > 1 ? `top: ${shortFn(stat.topFn)} ×${stat.topFnCount}` : '',
    ].filter(Boolean).join('\n');
    document.getElementById('tt-meta').textContent = meta;
    document.getElementById('tt-meta').style.whiteSpace = 'pre-line';
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px'; tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none'; canvas.style.cursor = 'crosshair';
  }
  canvas._hoverCall = hoverCall;
}

// --- MAIN LOOP ---
let _lastFrame = performance.now();
function loop() {
  const now = performance.now();
  const dtMs = Math.min(100, now - _lastFrame);  // cap at 100ms to avoid huge jumps
  _lastFrame = now;

  ctx.clearRect(0, 0, vw, vh);
  if (viewMode === 'ip_timeline') renderIpTimeline();
  else if (mainView === 'stream') {
    tickStream(dtMs);
    renderStream();
  }
  else if (mainView === 'users') renderUsersView();
  else if (mainView === 'lineage') renderLineageView();
  else if (mainView === 'ips') renderIpParticles();
  else renderTableParticles();
  requestAnimationFrame(loop);
}
loop();

// --- CLICK ---
canvas.addEventListener('click', e => {
  if (viewMode === 'ip_timeline') {
    if (canvas._hoverCall) openCallPanel(canvas._hoverCall);
    return;
  }
  if (mainView === 'users') {
    if (usersDragMoved) { usersDragMoved = false; return; }
    if (_userHover) openUserDetailPanel(_userHover);
    return;
  }
  if (mainView === 'lineage') {
    if (lineageMode === 'treemap') {
      if (lineageDragMoved) { lineageDragMoved = false; return; }
      if (lineageHover) {
        lineageSelected = lineageHover.key;
        lineageMode = 'detail';
      }
    } else {
      if (lineageDetailHover) {
        lineageSelected = lineageDetailHover.table;
      }
    }
    return;
  }
  const hovered = canvas._hover;
  if (!hovered) return;
  if (mainView === 'ips') selectIP(hovered.ip);
  else if (mainView === 'tables') openTablePanel(hovered);
});

function selectIP(ip) {
  selectedIP = ip;
  viewMode = 'ip_timeline';
  _ipCache = null;
  const calls = byIP[ip] || [];
  const ports = new Set(calls.map(c => c.port));
  const fns = new Set(calls.map(c => c.function));

  document.getElementById('back-btn').classList.add('on');
  document.getElementById('title').textContent = ip;
  document.getElementById('title').classList.add('ip-mode');
  document.getElementById('subtitle').textContent =
    `${calls.length.toLocaleString()} CALLS · ${ports.size} SESSIONS · ${fns.size} FUNCTIONS`;
  document.getElementById('stats').innerHTML = '';
  document.getElementById('legend').classList.add('on');
  document.getElementById('search-box').classList.remove('on');
  document.getElementById('view-toggle').classList.add('hidden');
  document.getElementById('bottom-controls').classList.remove('on');
  document.getElementById('stream-controls').classList.remove('on');
  document.getElementById('users-controls').classList.remove('on');
  document.getElementById('hint').textContent = 'CLICK BAR FOR SQL';
  closePanel();
}

function backToParticles() {
  viewMode = 'particles';
  selectedIP = null;
  document.getElementById('view-toggle').classList.remove('hidden');
  refreshHeader();
  closePanel();
}

// --- TABLE PANEL ---
function openTablePanel(p) {
  const tName = p.table;
  const tCol = `hsl(${p.hue}, 55%, 65%)`;
  const pIp = document.getElementById('p-ip');
  pIp.textContent = tName;
  pIp.style.color = tCol;

  const calls = p.calls;
  const fns = {};
  for (const c of calls) (fns[c.function] = fns[c.function] || []).push(c);
  const ips = new Set(calls.map(c => c.ip));
  const datasources = new Set();
  for (const c of calls) {
    if (c.datasources) for (const d of c.datasources) if (d) datasources.add(d);
  }

  document.getElementById('p-ctx').innerHTML =
    `${calls.length.toLocaleString()} calls reference this table · ${Object.keys(fns).length} functions · ${ips.size} IPs · ${datasources.size} datasources`;

  document.getElementById('p-summary').innerHTML = `
    <span><strong>${calls.length}</strong>calls</span>
    <span><strong>${Object.keys(fns).length}</strong>functions</span>
    <span><strong>${ips.size}</strong>IPs</span>
  `;

  const body = document.getElementById('p-body');
  body.innerHTML = '';

  // sort fns by call count desc
  const fnEntries = Object.entries(fns).sort((a, b) => b[1].length - a[1].length);
  for (const [fn, arr] of fnEntries) {
    const group = document.createElement('div');
    group.className = 'group';
    const lbl = document.createElement('div');
    lbl.className = 'group-label';
    lbl.style.borderLeftColor = tCol;
    lbl.textContent = `${fn} · ${arr.length} call${arr.length>1?'s':''}`;
    group.appendChild(lbl);

    arr.sort((a, b) => (a._start || 0) - (b._start || 0));
    // limit to a reasonable display, say 100, but expand on demand
    const showLimit = 50;
    const shown = arr.slice(0, showLimit);
    for (const c of shown) group.appendChild(makeTableCallRow(c));
    if (arr.length > showLimit) {
      const more = document.createElement('div');
      more.className = 'group-label';
      more.style.borderLeftColor = 'var(--text-dim)';
      more.style.marginTop = '8px';
      more.textContent = `+ ${arr.length - showLimit} more (truncated)`;
      group.appendChild(more);
    }
    body.appendChild(group);
  }

  document.getElementById('panel').classList.add('open');
}

function makeTableCallRow(c) {
  const row = document.createElement('div');
  row.className = 'session';
  const tsShort = c._start ? fmtTime(c._start) : '-';
  const cacheBadge = c.cache === 'hit' ? '<span class="badge hit">cache</span>'
                   : c.cache === 'miss' ? '<span class="badge miss">db</span>' : '';
  const durBadge = c.duration_ms != null ? `<span class="badge dur">${c.duration_ms.toFixed(0)}ms</span>` : '';
  const ipBadge = c.ip ? `<span class="badge ip">${escapeHtml(c.ip)}${c.port?':'+c.port:''}</span>` : '';

  const main = document.createElement('div');
  main.style.display = 'contents';
  main.innerHTML = `
    <div class="ts">${tsShort}</div>
    <div class="fn">${escapeHtml(shortFn(c.function))}</div>
    <div class="badges">${cacheBadge}${durBadge}${ipBadge}</div>
  `;
  row.appendChild(main);

  const detail = document.createElement('div');
  detail.className = 'session-detail';
  row.appendChild(detail);

  row.addEventListener('click', e => {
    e.stopPropagation();
    const expanded = row.classList.toggle('expanded');
    if (expanded && !detail.dataset.loaded) fillCallDetail(detail, c);
  });

  return row;
}

// --- existing call panel (timeline bar click) ---
function openCallPanel(c) {
  const pIp = document.getElementById('p-ip');
  pIp.style.color = '';
  pIp.textContent = (c.ip || '?') + ':' + (c.port || '?');
  const portCalls = (byIP[c.ip] || []).filter(x => x.port === c.port);
  const stat = analyzeSession(portCalls);
  const patCls = stat.pattern.toLowerCase();
  let ctxHtml = `session has <strong style="color:var(--text)">${stat.n}</strong> calls, <strong style="color:var(--text)">${stat.uniqueFns}</strong> unique fn`;
  ctxHtml += ` · pattern <span class="pat ${patCls}">${stat.pattern}</span>`;
  if (stat.intervalMean != null) {
    ctxHtml += `<br>interval avg <strong style="color:var(--text)">${fmtInterval(stat.intervalMean)}</strong> (cv ${stat.intervalCV.toFixed(2)}, range ${fmtInterval(stat.intervalMin)}–${fmtInterval(stat.intervalMax)})`;
  }
  if (stat.topFn && stat.topFnCount > 1) {
    ctxHtml += `<br>most: <strong style="color:var(--text)">${escapeHtml(shortFn(stat.topFn))}</strong> repeated ${stat.topFnCount}× (${Math.round(stat.topFnCount/stat.n*100)}%)`;
  }
  document.getElementById('p-ctx').innerHTML = ctxHtml;
  document.getElementById('p-summary').innerHTML = `<span><strong>${escapeHtml(c.function || '-')}</strong></span>`;

  const body = document.getElementById('p-body');
  body.innerHTML = '';
  const group = document.createElement('div');
  group.className = 'group';
  const lbl = document.createElement('div');
  lbl.className = 'group-label';
  lbl.textContent = `THIS CALL · clicked from timeline`;
  group.appendChild(lbl);
  const row = makeCallRow(c);
  row.classList.add('expanded');
  const detail = row.querySelector('.session-detail');
  if (detail && !detail.dataset.loaded) fillCallDetail(detail, c);
  group.appendChild(row);
  body.appendChild(group);

  document.getElementById('panel').classList.add('open');
}

function makeCallRow(c) {
  const row = document.createElement('div');
  row.className = 'session';
  const tsShort = c._start ? fmtTime(c._start) : '-';
  const cacheBadge = c.cache === 'hit' ? '<span class="badge hit">cache</span>'
                   : c.cache === 'miss' ? '<span class="badge miss">db</span>' : '';
  const durBadge = c.duration_ms != null ? `<span class="badge dur">${c.duration_ms.toFixed(0)}ms</span>` : '';
  const sqlBadge = c.n_sqls ? `<span class="badge sql">${c.n_sqls} sql</span>` : '';

  const main = document.createElement('div');
  main.style.display = 'contents';
  main.innerHTML = `
    <div class="ts">${tsShort}</div>
    <div class="fn">${escapeHtml(c.function || '(unknown)')}</div>
    <div class="badges">${cacheBadge}${durBadge}${sqlBadge}</div>
  `;
  row.appendChild(main);
  const detail = document.createElement('div');
  detail.className = 'session-detail';
  row.appendChild(detail);
  row.addEventListener('click', e => {
    e.stopPropagation();
    const expanded = row.classList.toggle('expanded');
    if (expanded && !detail.dataset.loaded) fillCallDetail(detail, c);
  });
  return row;
}

function fillCallDetail(detail, c) {
  detail.dataset.loaded = '1';
  const dur = c.duration_ms != null ? c.duration_ms.toFixed(0) + 'ms' : '-';
  const guid = (c.guid || '-').slice(0, 14);
  const ckey = c.cache_key || '-';
  let html = `<div class="meta-line">`
    + `<span class="k">ip</span> <span class="v">${escapeHtml(c.ip||'-')}:${c.port||'-'}</span>`
    + `<span class="k">duration</span> <span class="v">${dur}</span><br>`
    + `<span class="k">guid</span> <span class="v">${guid}</span>`
    + `<span class="k">cache</span> <span class="v">${c.cache || '-'}</span>`
    + `<span class="k">key</span> <span class="v">${escapeHtml(ckey)}</span>`
    + `</div>`;
  if (c.sqls && c.sqls.length) {
    for (let i = 0; i < c.sqls.length; i++) {
      const ds = (c.datasources && c.datasources[i]) || '-';
      html += `<div class="sql-block"><span class="ds">[${escapeHtml(ds)}]</span>${escapeHtml(c.sqls[i] || '')}</div>`;
    }
  } else {
    html += '<div class="meta-line">no sql in this call</div>';
  }
  detail.innerHTML = html;
}

function closePanel() { document.getElementById('panel').classList.remove('open'); }
window.closePanel = closePanel;
// simple, direct binding
const _closeBtn = document.getElementById('close-btn');
_closeBtn.addEventListener('click', function(e) {
  e.preventDefault();
  e.stopPropagation();
  closePanel();
});
_closeBtn.addEventListener('touchstart', function(e) {
  e.preventDefault();
  e.stopPropagation();
  closePanel();
}, { passive: false });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (document.getElementById('panel').classList.contains('open')) closePanel();
    else if (viewMode === 'ip_timeline') backToParticles();
  }
});

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
    """Build a self-contained HTML from the calls DataFrame."""

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
            'guid': row.get('guid'),
            'cache': row.get('cache'),
            'cache_key': row.get('cache_key'),
            'n_sqls': int(row.get('n_sqls') or 0),
            'duration_ms': float(row['duration_ms']) if pd.notna(row.get('duration_ms')) else None,
            'datasources': list(row.get('datasources') or []),
            'sqls': list(row.get('sqls') or []),
            'tables': list(row.get('tables') or []),
            'session_user_id': row.get('session_user_id') if pd.notna(row.get('session_user_id')) else None,
            'join_pairs': list(row.get('join_pairs') or []),
            'union_pairs': list(row.get('union_pairs') or []),
            'where_values': dict(row.get('where_values') or {}),
            'select_cols': list(row.get('select_cols') or []),
        })

    # pre-compute global time range here (much faster than in JS)
    starts = df['start_ts'].dropna()
    ends = df['end_ts'].dropna()
    global_tmin = starts.min().isoformat() if len(starts) else None
    global_tmax = ends.max().isoformat() if len(ends) else None

    data_json = json.dumps(records, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace('__DATA__', data_json)
    html = html.replace('__TMIN__', json.dumps(global_tmin))
    html = html.replace('__TMAX__', json.dumps(global_tmax))

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = len(html) / 1024 / 1024
    ip_count = df['ip'].nunique()
    table_count = len({t for row in df['tables'].dropna() for t in (row or [])})
    print(f'Saved: {out_path}  ({size_mb:.1f} MB, {len(records):,} calls, {ip_count} IPs, {table_count} tables)')
    return out_path


# Auto-run if df is in scope (e.g. exec(open(...).read()) from Jupyter)
try:
    df
    build_user_flows(df, 'user_flows.html')
except NameError:
    print("df not in scope. Call manually: build_user_flows(df, 'user_flows.html')")
