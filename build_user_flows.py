"""
build_user_flows.py
-------------------
df (session_to_row로 만든 DataFrame) 받아서
self-contained HTML 하나 생성. 더블클릭으로 열면 바로 작동.

Jupyter에서:
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
    --bg: #0a0a0c;
    --bg-2: #14151a;
    --line: #26282f;
    --text: #f5f1e8;
    --text-muted: #8b8680;
    --text-dim: #4a4944;
    --amber: #e8a04a;
    --cyan: #5ec0c0;
    --red: #d96060;
  }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
  }
  #canvas { position: fixed; inset: 0; cursor: crosshair; }

  /* HUD top-left */
  .hud {
    position: fixed; top: 24px; left: 28px;
    z-index: 5; pointer-events: none;
  }
  .hud h1 {
    font-family: 'Fraunces', serif;
    font-weight: 300;
    font-size: 22px;
    letter-spacing: -0.01em;
    margin-bottom: 4px;
  }
  .hud .sub {
    font-size: 11px;
    color: var(--text-muted);
    letter-spacing: 0.1em;
  }

  /* HUD top-right stats */
  .stats {
    position: fixed; top: 24px; right: 28px;
    z-index: 5;
    font-size: 11px;
    color: var(--text-muted);
    text-align: right;
    letter-spacing: 0.1em;
    pointer-events: none;
  }
  .stats .n {
    color: var(--text);
    font-family: 'Fraunces', serif;
    font-size: 18px;
    margin-right: 6px;
  }

  /* Bottom hint */
  .hint {
    position: fixed; bottom: 20px; left: 50%;
    transform: translateX(-50%);
    z-index: 5;
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.3em;
    pointer-events: none;
    transition: opacity 0.3s;
  }

  /* Hover tooltip */
  .tooltip {
    position: fixed;
    z-index: 6;
    background: var(--bg-2);
    border: 1px solid var(--line);
    padding: 8px 12px;
    font-size: 11px;
    color: var(--text);
    pointer-events: none;
    display: none;
    white-space: nowrap;
  }
  .tooltip .ip { color: var(--amber); font-weight: 500; }
  .tooltip .meta { color: var(--text-muted); margin-top: 4px; }

  /* Detail panel */
  .panel {
    position: fixed;
    top: 0; right: 0; bottom: 0;
    width: min(560px, 100vw);
    background: var(--bg-2);
    border-left: 1px solid var(--line);
    z-index: 10;
    transform: translateX(100%);
    transition: transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
    display: flex;
    flex-direction: column;
  }
  .panel.open { transform: translateX(0); }

  .panel-head {
    padding: 24px 28px 20px;
    border-bottom: 1px solid var(--line);
    flex-shrink: 0;
  }
  .panel-head .ip-big {
    font-family: 'Fraunces', serif;
    font-weight: 300;
    font-size: 28px;
    color: var(--amber);
    letter-spacing: -0.01em;
    margin-bottom: 4px;
  }
  .panel-head .summary {
    display: flex;
    gap: 20px;
    margin-top: 14px;
    font-size: 11px;
    color: var(--text-muted);
    letter-spacing: 0.05em;
  }
  .panel-head .summary span strong {
    color: var(--text);
    font-family: 'Fraunces', serif;
    font-size: 14px;
    font-weight: 400;
    margin-right: 4px;
  }
  .close-btn {
    position: absolute;
    top: 20px; right: 20px;
    background: transparent;
    border: 1px solid var(--line);
    color: var(--text);
    width: 28px; height: 28px;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    font-family: inherit;
  }
  .close-btn:hover { border-color: var(--amber); color: var(--amber); }

  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px 8px 24px 28px;
  }

  /* Thread group */
  .thread-group {
    margin-bottom: 24px;
  }
  .thread-label {
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.15em;
    margin-bottom: 8px;
    padding-left: 8px;
    border-left: 2px solid var(--cyan);
  }

  /* Session row */
  .session {
    display: grid;
    grid-template-columns: 80px 1fr auto;
    gap: 12px;
    padding: 10px 12px;
    border-left: 1px solid var(--line);
    margin-left: 4px;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    align-items: baseline;
  }
  .session:hover { background: rgba(232,160,74,0.05); border-left-color: var(--amber); }
  .session.expanded { background: rgba(232,160,74,0.08); border-left-color: var(--amber); }
  .session .ts {
    font-size: 10px;
    color: var(--text-muted);
  }
  .session .fn {
    font-size: 12px;
    color: var(--text);
    word-break: break-all;
  }
  .session .badges {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }
  .badge {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 2px;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    border: 1px solid var(--line);
    text-transform: uppercase;
  }
  .badge.hit { color: var(--amber); border-color: var(--amber); }
  .badge.miss { color: var(--cyan); border-color: var(--cyan); }
  .badge.sql { color: var(--text); }

  /* SQL detail */
  .session-detail {
    grid-column: 1 / -1;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px dashed var(--line);
    display: none;
  }
  .session.expanded .session-detail { display: block; }
  .session-detail .meta-line {
    font-size: 10px;
    color: var(--text-muted);
    margin-bottom: 8px;
    letter-spacing: 0.05em;
  }
  .sql-block {
    background: var(--bg);
    border: 1px solid var(--line);
    padding: 12px;
    margin-bottom: 8px;
    font-size: 11px;
    line-height: 1.5;
    color: var(--text);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 280px;
    overflow-y: auto;
  }
  .sql-block .ds {
    color: var(--amber);
    font-size: 10px;
    letter-spacing: 0.1em;
    display: block;
    margin-bottom: 6px;
  }

  /* IP search box */
  .search-box {
    position: fixed; bottom: 60px; left: 28px;
    z-index: 5;
    background: var(--bg-2);
    border: 1px solid var(--line);
    padding: 6px 10px;
    width: 200px;
  }
  .search-box input {
    background: transparent;
    border: none;
    color: var(--text);
    font-family: inherit;
    font-size: 11px;
    outline: none;
    width: 100%;
  }
  .search-box::before {
    content: '⌕ ';
    color: var(--text-dim);
    font-size: 10px;
  }

  @media (max-width: 700px) {
    .hud h1 { font-size: 18px; }
    .stats { font-size: 10px; }
    .panel { width: 100vw; }
  }
</style>
</head>
<body>

<canvas id="canvas"></canvas>

<div class="hud">
  <h1>User Flows</h1>
  <div class="sub">EACH PARTICLE = ONE IP · CLICK TO EXPLORE</div>
</div>

<div class="stats" id="stats"></div>

<div class="hint" id="hint">CLICK A PARTICLE</div>

<div class="search-box">
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
    <div class="summary" id="p-summary"></div>
  </div>
  <div class="panel-body" id="p-body"></div>
</div>

<script>
// --- DATA (injected by Python) ---
const SESSIONS = __DATA__;

// --- aggregate by IP ---
const byIP = {};
for (const s of SESSIONS) {
  const key = s.ip || 'unknown';
  (byIP[key] = byIP[key] || []).push(s);
}
const ipList = Object.entries(byIP)
  .map(([ip, sess]) => ({ ip, sessions: sess, count: sess.length }))
  .sort((a, b) => b.count - a.count);

// stats
document.getElementById('stats').innerHTML = `
  <span class="n">${ipList.length}</span>IPs &nbsp;·&nbsp;
  <span class="n">${SESSIONS.length.toLocaleString()}</span>SESSIONS
`;

// --- canvas setup ---
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
let W, H;
function resize() {
  W = canvas.width = window.innerWidth * devicePixelRatio;
  H = canvas.height = window.innerHeight * devicePixelRatio;
  canvas.style.width = window.innerWidth + 'px';
  canvas.style.height = window.innerHeight + 'px';
  ctx.scale(devicePixelRatio, devicePixelRatio);
}
window.addEventListener('resize', resize);
resize();

// --- particles ---
const particles = ipList.map((d, i) => {
  const r = Math.log(d.count + 1) * 3 + 4;
  return {
    ...d,
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.25,
    vy: (Math.random() - 0.5) * 0.25,
    r,
    hover: false,
    visible: true,
  };
});

// --- search filter ---
const searchInput = document.getElementById('search');
searchInput.addEventListener('input', (e) => {
  const q = e.target.value.trim().toLowerCase();
  particles.forEach(p => {
    p.visible = !q || p.ip.toLowerCase().includes(q);
  });
});

// --- animation ---
let mouseX = -100, mouseY = -100;
canvas.addEventListener('mousemove', (e) => {
  mouseX = e.clientX;
  mouseY = e.clientY;
});

function loop() {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

  let hoverP = null;
  for (const p of particles) {
    if (!p.visible) continue;
    p.x += p.vx;
    p.y += p.vy;
    if (p.x < p.r || p.x > window.innerWidth - p.r) p.vx *= -1;
    if (p.y < p.r || p.y > window.innerHeight - p.r) p.vy *= -1;

    const d = Math.hypot(p.x - mouseX, p.y - mouseY);
    p.hover = d < p.r + 4;
    if (p.hover) hoverP = p;

    // glow base
    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 2.5);
    grad.addColorStop(0, p.hover ? 'rgba(245,241,232,0.5)' : 'rgba(232,160,74,0.25)');
    grad.addColorStop(1, 'rgba(232,160,74,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r * 2.5, 0, Math.PI * 2);
    ctx.fill();

    // core
    ctx.fillStyle = p.hover ? '#f5f1e8' : 'rgba(232,160,74,0.85)';
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fill();
  }

  // tooltip
  const tt = document.getElementById('tooltip');
  if (hoverP) {
    document.getElementById('tt-ip').textContent = hoverP.ip;
    document.getElementById('tt-meta').textContent = `${hoverP.count.toLocaleString()} sessions`;
    tt.style.display = 'block';
    tt.style.left = (mouseX + 14) + 'px';
    tt.style.top = (mouseY + 14) + 'px';
    canvas.style.cursor = 'pointer';
  } else {
    tt.style.display = 'none';
    canvas.style.cursor = 'crosshair';
  }

  requestAnimationFrame(loop);
}
loop();

// --- click ---
canvas.addEventListener('click', (e) => {
  for (const p of particles) {
    if (!p.visible) continue;
    const d = Math.hypot(e.clientX - p.x, e.clientY - p.y);
    if (d < p.r + 4) {
      openPanel(p);
      return;
    }
  }
});

// --- panel ---
function openPanel(p) {
  document.getElementById('p-ip').textContent = p.ip;
  document.getElementById('hint').style.opacity = 0;

  // summary stats
  const sess = p.sessions;
  const ports = new Set(sess.map(s => s.port));
  const threads = new Set(sess.map(s => s.thread));
  const fns = new Set(sess.map(s => s.function));
  const hits = sess.filter(s => s.cache === 'hit').length;
  const sqls = sess.reduce((sum, s) => sum + (s.n_sqls || 0), 0);

  document.getElementById('p-summary').innerHTML = `
    <span><strong>${sess.length}</strong>sessions</span>
    <span><strong>${ports.size}</strong>ports</span>
    <span><strong>${fns.size}</strong>functions</span>
    <span><strong>${sqls}</strong>sqls</span>
  `;

  // group by thread, sort each by start_ts
  const byThread = {};
  for (const s of sess) {
    (byThread[s.thread] = byThread[s.thread] || []).push(s);
  }
  // sort threads by their first session time
  const threadEntries = Object.entries(byThread).map(([t, arr]) => {
    arr.sort((a, b) => (a.start_ts || '').localeCompare(b.start_ts || ''));
    return [t, arr];
  });
  threadEntries.sort((a, b) => (a[1][0].start_ts || '').localeCompare(b[1][0].start_ts || ''));

  // render
  const body = document.getElementById('p-body');
  body.innerHTML = '';
  for (const [thread, arr] of threadEntries) {
    const group = document.createElement('div');
    group.className = 'thread-group';

    const lbl = document.createElement('div');
    lbl.className = 'thread-label';
    lbl.textContent = `THREAD · ${thread} · ${arr.length} call${arr.length>1?'s':''}`;
    group.appendChild(lbl);

    for (const s of arr) {
      const row = document.createElement('div');
      row.className = 'session';
      const tsShort = (s.start_ts || '').slice(11, 19);
      const cacheBadge = s.cache === 'hit'
        ? '<span class="badge hit">cache</span>'
        : s.cache === 'miss' ? '<span class="badge miss">db</span>' : '';
      const sqlBadge = s.n_sqls ? `<span class="badge sql">${s.n_sqls} sql</span>` : '';

      const main = document.createElement('div');
      main.style.display = 'contents';
      main.innerHTML = `
        <div class="ts">${tsShort}</div>
        <div class="fn">${s.function || '(unknown)'}</div>
        <div class="badges">${cacheBadge}${sqlBadge}</div>
      `;
      row.appendChild(main);

      // detail (lazy)
      const detail = document.createElement('div');
      detail.className = 'session-detail';
      row.appendChild(detail);

      row.addEventListener('click', () => {
        const expanded = row.classList.toggle('expanded');
        if (expanded && !detail.dataset.loaded) {
          detail.dataset.loaded = '1';
          let html = `<div class="meta-line">port ${s.port || '-'} · ${s.duration_ms ? s.duration_ms.toFixed(0)+'ms' : '-'} · guid ${(s.guid||'-').slice(0,12)}</div>`;
          if (s.sqls && s.sqls.length) {
            for (let i = 0; i < s.sqls.length; i++) {
              const ds = (s.datasources && s.datasources[i]) || '-';
              const sqlText = s.sqls[i] || '';
              html += `<div class="sql-block"><span class="ds">[${ds}]</span>${escapeHtml(sqlText)}</div>`;
            }
          } else {
            html += '<div class="meta-line">no sql in this call</div>';
          }
          detail.innerHTML = html;
        }
      });

      group.appendChild(row);
    }
    body.appendChild(group);
  }

  document.getElementById('panel').classList.add('open');
}

function closePanel() {
  document.getElementById('panel').classList.remove('open');
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closePanel();
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
    """Build a self-contained HTML from the sessions DataFrame."""

    # 1) DataFrame -> records (JSON-serializable)
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
            'n_sqls': int(row.get('n_sqls') or 0),
            'duration_ms': float(row['duration_ms']) if pd.notna(row.get('duration_ms')) else None,
            'datasources': list(row.get('datasources') or []),
            'sqls': list(row.get('sqls') or []),
        })

    # 2) Inject into template
    data_json = json.dumps(records, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace('__DATA__', data_json)

    # 3) Save
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = len(html) / 1024 / 1024
    print(f'Saved: {out_path}  ({size_mb:.1f} MB, {len(records):,} sessions)')
    return out_path


# If executed via exec(open(...).read()), df should already be in scope
if __name__ == '__main__' or 'df' in dir():
    try:
        build_user_flows(df, 'user_flows.html')
    except NameError:
        print("df not found. Run: build_user_flows(df, 'user_flows.html')")
