"""
build_user_flows.py  (v4)
-------------------------
v4 changes:
  - Each session (ip,port) is analyzed for behavior pattern
  - 3 metrics per session:
      * call repetition (top function + count)
      * interval CV (std/mean of inter-call intervals)
      * mean interval
  - Classification: AUTO (CV<0.25) / MIXED (<0.75) / HUMAN (>=0.75)
  - Shown in timeline labels + tooltip + detail panel

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
    position: absolute; top: 20px; right: 20px;
    background: transparent; border: 1px solid var(--line);
    color: var(--text); width: 28px; height: 28px;
    cursor: pointer; font-size: 14px; line-height: 1; font-family: inherit;
  }
  .close-btn:hover { border-color: var(--amber); color: var(--amber); }

  .panel-body { flex: 1; overflow-y: auto; padding: 16px 8px 24px 28px; }
  .port-group { margin-bottom: 24px; }
  .port-label {
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
  .badge.dur, .badge.sql { color: var(--text); }

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
  <input type="text" id="search" placeholder="filter by ip..." autocomplete="off">
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

// global time range — used by all IP timelines for consistent X axis
const GLOBAL_TMIN = Math.min(...CALLS.map(c => c._start).filter(v => v != null));
const GLOBAL_TMAX = Math.max(...CALLS.map(c => c._end).filter(v => v != null));

document.getElementById('stats').innerHTML = `
  <span class="n">${ipList.length}</span>IPs &nbsp;·&nbsp;
  <span class="n">${CALLS.length.toLocaleString()}</span>CALLS
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
let selectedIP = null;
let filterQuery = '';

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

function fmtTime(t) {
  const d = new Date(t);
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtInterval(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  if (ms < 60000) return (ms/1000).toFixed(1) + 's';
  if (ms < 3600000) return (ms/60000).toFixed(1) + 'm';
  return (ms/3600000).toFixed(1) + 'h';
}

// --- session analysis ---
function analyzeSession(calls) {
  const sorted = [...calls].sort((a, b) => (a._start || 0) - (b._start || 0));
  const n = sorted.length;

  // function repetition
  const fnCnt = {};
  for (const c of sorted) fnCnt[c.function] = (fnCnt[c.function] || 0) + 1;
  const fnEntries = Object.entries(fnCnt).sort((a, b) => b[1] - a[1]);
  const topFn = fnEntries[0] || [null, 0];
  const uniqueFns = fnEntries.length;

  // interval analysis
  let pattern = 'SHORT';
  let intervalMean = null, intervalCV = null;
  let intervalMin = null, intervalMax = null;
  if (n >= 3) {
    const intervals = [];
    for (let i = 1; i < n; i++) {
      const dt = sorted[i]._start - sorted[i-1]._start;
      if (dt > 0) intervals.push(dt);
    }
    if (intervals.length >= 2) {
      const mean = intervals.reduce((a, b) => a + b, 0) / intervals.length;
      const variance = intervals.reduce((a, b) => a + (b - mean) ** 2, 0) / intervals.length;
      const std = Math.sqrt(variance);
      const cv = mean > 0 ? std / mean : 0;
      intervalMean = mean;
      intervalCV = cv;
      intervalMin = Math.min(...intervals);
      intervalMax = Math.max(...intervals);
      if (cv < 0.25) pattern = 'AUTO';
      else if (cv < 0.75) pattern = 'MIXED';
      else pattern = 'HUMAN';
    }
  }

  return {
    n, uniqueFns,
    topFn: topFn[0], topFnCount: topFn[1],
    pattern, intervalMean, intervalCV, intervalMin, intervalMax,
  };
}

const PATTERN_COLOR = {
  AUTO: '#6fb3b3', HUMAN: '#d99a55', MIXED: '#8b8680', SHORT: '#4a4944',
};

// --- PARTICLES ---
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
    const ports = new Set(hoverP.calls.map(c => c.port));
    document.getElementById('tt-meta').textContent = `${hoverP.count.toLocaleString()} calls · ${ports.size} sessions`;
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

// --- IP TIMELINE ---
let _ipCache = null;
function buildIpCache(ip) {
  const calls = byIP[ip] || [];
  // use global time range so X axis is comparable across IPs
  const tMin = GLOBAL_TMIN;
  const tMax = GLOBAL_TMAX;

  const byPort = {};
  for (const c of calls) {
    const k = c.port || '?';
    (byPort[k] = byPort[k] || []).push(c);
  }
  const ports = Object.keys(byPort).sort((a, b) => {
    const aF = Math.min(...byPort[a].map(c => c._start || Infinity));
    const bF = Math.min(...byPort[b].map(c => c._start || Infinity));
    return aF - bF;
  });
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

function renderIpTimeline() {
  if (!selectedIP) return;
  if (!_ipCache || _ipCache.ip !== selectedIP) _ipCache = buildIpCache(selectedIP);
  const cache = _ipCache;
  if (!cache.ports.length) return;

  const { w, h, rowH } = tlLayout(cache);
  const xScale = t => TL_LEFT + (t - cache.tMin) / (cache.tMax - cache.tMin || 1) * w;

  // time gridlines + labels
  ctx.font = '10px JetBrains Mono';
  ctx.strokeStyle = '#1f2127';
  const ticks = 8;
  for (let i = 0; i <= ticks; i++) {
    const x = TL_LEFT + w * i / ticks;
    const t = cache.tMin + (cache.tMax - cache.tMin) * i / ticks;
    ctx.beginPath(); ctx.moveTo(x, TL_TOP); ctx.lineTo(x, TL_TOP + h); ctx.stroke();
    ctx.fillStyle = '#5a5852';
    ctx.fillText(fmtTime(t), x - 18, TL_TOP - 10);
  }
  ctx.strokeStyle = '#26282f';
  ctx.beginPath(); ctx.moveTo(TL_LEFT, TL_TOP); ctx.lineTo(TL_LEFT + w, TL_TOP); ctx.stroke();

  // ports + bars
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

    // row background (alternating)
    if (i % 2 === 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.015)';
      ctx.fillRect(TL_LEFT, y, w, rowH);
    }

    // === LEFT LABEL AREA ===
    if (rowH >= 32) {
      // 3-line label
      ctx.fillStyle = '#f5f1e8';
      ctx.font = '11px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + 13);

      // pattern tag + interval
      ctx.fillStyle = patternCol;
      ctx.font = 'bold 9px JetBrains Mono';
      let patText = stat.pattern;
      if (stat.intervalMean != null) patText += '  every ~' + fmtInterval(stat.intervalMean);
      ctx.fillText(patText, 14, y + 26);

      // top function (or call count)
      ctx.fillStyle = '#8b8680';
      ctx.font = '9px JetBrains Mono';
      const topShort = stat.topFn ? shortFn(stat.topFn) : '-';
      ctx.fillText(`${stat.n}c · ${topShort} ×${stat.topFnCount}`, 14, y + 38);
    } else if (rowH >= 18) {
      // 2-line label
      ctx.fillStyle = '#f5f1e8';
      ctx.font = '11px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + rowH/2 - 2);

      ctx.fillStyle = patternCol;
      ctx.font = 'bold 9px JetBrains Mono';
      ctx.fillText(`${stat.n}c · ${stat.pattern}${stat.intervalMean != null ? ' '+fmtInterval(stat.intervalMean) : ''}`, 14, y + rowH/2 + 10);
    } else {
      // 1-line compact label
      ctx.fillStyle = '#f5f1e8';
      ctx.font = '10px JetBrains Mono';
      ctx.fillText(':' + port, 14, y + rowH/2 + 3);

      ctx.fillStyle = patternCol;
      ctx.beginPath();
      ctx.arc(85, y + rowH/2, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#5a5852';
      ctx.font = '9px JetBrains Mono';
      ctx.fillText(stat.n + 'c', 95, y + rowH/2 + 3);
    }

    // === BARS ===
    for (const c of calls) {
      if (c._start == null) continue;
      const x1 = xScale(c._start);
      const x2 = xScale(c._end);
      const barW = Math.max(2, x2 - x1);
      const barH = Math.max(4, rowH - 6);
      const barY = y + (rowH - barH) / 2;

      ctx.fillStyle = c.cache === 'hit' ? hitC : c.cache === 'miss' ? missC : noneC;
      ctx.fillRect(x1, barY, barW, barH);

      if (mouseX >= x1 - 2 && mouseX <= x1 + barW + 2
          && mouseY >= barY && mouseY <= barY + barH) {
        hoverCall = c;
      }
    }
  }

  // tooltip
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
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = 'crosshair';
  }
  canvas._hoverCall = hoverCall;
}

function shortFn(fn) {
  if (!fn) return '-';
  // SMARTPMS.PREQUIPMENT#getEquipmentList -> getEquipmentList
  const hash = fn.indexOf('#');
  if (hash >= 0) return fn.slice(hash + 1);
  const dot = fn.lastIndexOf('.');
  if (dot >= 0) return fn.slice(dot + 1);
  return fn.length > 24 ? fn.slice(0, 22) + '..' : fn;
}

// --- main loop ---
function loop() {
  ctx.clearRect(0, 0, vw, vh);
  if (viewMode === 'particles') renderParticles();
  else renderIpTimeline();
  requestAnimationFrame(loop);
}
loop();

canvas.addEventListener('click', e => {
  if (viewMode === 'particles') {
    for (const p of particles) {
      if (!ipVisible(p.ip)) continue;
      const d = Math.hypot(e.clientX - p.x, e.clientY - p.y);
      if (d < p.r + 4) { selectIP(p.ip); return; }
    }
  } else {
    if (canvas._hoverCall) openCallPanel(canvas._hoverCall);
  }
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
  document.getElementById('hint').textContent = 'CLICK BAR FOR SQL';
  closePanel();
}

function backToParticles() {
  viewMode = 'particles';
  selectedIP = null;
  document.getElementById('back-btn').classList.remove('on');
  document.getElementById('title').textContent = 'User Flows';
  document.getElementById('title').classList.remove('ip-mode');
  document.getElementById('subtitle').textContent = 'EACH PARTICLE = ONE IP · CLICK TO EXPLORE';
  document.getElementById('stats').innerHTML = `
    <span class="n">${ipList.length}</span>IPs &nbsp;·&nbsp;
    <span class="n">${CALLS.length.toLocaleString()}</span>CALLS
  `;
  document.getElementById('legend').classList.remove('on');
  document.getElementById('search-box').classList.add('on');
  document.getElementById('hint').textContent = 'CLICK TO INSPECT';
  closePanel();
}

function openCallPanel(c) {
  document.getElementById('p-ip').textContent = (c.ip || '?') + ':' + (c.port || '?');
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
  group.className = 'port-group';
  const lbl = document.createElement('div');
  lbl.className = 'port-label';
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
    + `<span class="k">duration</span> <span class="v">${dur}</span>`
    + `<span class="k">guid</span> <span class="v">${guid}</span><br>`
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
        })

    data_json = json.dumps(records, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace('__DATA__', data_json)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = len(html) / 1024 / 1024
    ip_count = df['ip'].nunique()
    print(f'Saved: {out_path}  ({size_mb:.1f} MB, {len(records):,} calls, {ip_count} IPs)')
    return out_path


if __name__ == '__main__' or 'df' in dir():
    try:
        build_user_flows(df, 'user_flows.html')
    except NameError:
        print("df not found. Run: build_user_flows(df, 'user_flows.html')")
