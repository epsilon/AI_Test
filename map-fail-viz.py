"""
map_fail_viz.py — multi-CSV die fail map visualizer
단일 HTML 리포트로 출력. 여러 CSV 읽어서 type별로 집계·비교 가능.

사용법 (Jupyter 셀에서):
    CSV_PATHS = ["wafer_01.csv", "wafer_02.csv", ...]   # 여러 개 가능
    # 또는 단일: CSV_PATH = "data.csv"
    TYPE_COL  = "item"        # 'item' / 'temp' 등 그룹화 기준 (있으면 자동 감지)
    # 이 파일 내용 붙여넣고 실행

출력: OUTPUT_HTML (기본 'fail_report.html') 단일 파일
    1. Overview wafer map (전체 합산)
    2. Pareto chart
    3. Per-group small multiples
    4. Interactive explorer (type/group/column 드롭다운, Plotly)
"""

# === CONFIG — 위 셀에서 미리 정의했으면 그 값 사용 ===
try: CSV_PATHS
except NameError:
    try: CSV_PATHS = [CSV_PATH]
    except NameError: CSV_PATHS = ["your_data.csv"]
if not isinstance(CSV_PATHS, (list, tuple)):
    CSV_PATHS = [CSV_PATHS]

try: TYPE_COL
except NameError: TYPE_COL = "item"          # 'item' 또는 'temp' 등

try: WAFER_FILTER
except NameError: WAFER_FILTER = None

try: TOP_PER_GROUP
except NameError: TOP_PER_GROUP = 36

try: POINT_SIZE
except NameError: POINT_SIZE = 18

try: OUTPUT_HTML
except NameError: OUTPUT_HTML = "fail_report.html"

try: MAX_INTERACTIVE_COLS
except NameError: MAX_INTERACTIVE_COLS = None

try: SKIP_TYPE_ROW
except NameError: SKIP_TYPE_ROW = True


# === imports ===
import re, json, base64
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")               # 인라인 표시 안 함 — 전부 HTML 에 박음
import matplotlib.pyplot as plt


# === helpers ===
def parse_group(col):
    s = col.lower()
    s = re.sub(r"^fail_?(cn|cnt)?_?", "", s)
    m = re.match(r"^([a-z][a-z_]*?)_?(\d+)$", s)
    if m:
        return (m.group(1).strip("_") or "misc"), int(m.group(2))
    return (s or "misc"), None


def wafer_map(ax, xs, ys, values, title, vmax_log=None, point_size=None):
    if point_size is None:
        point_size = POINT_SIZE
    v = np.log1p(np.asarray(values, dtype=float))
    if vmax_log is None:
        vmax_log = float(v.max()) if v.size and v.max() > 0 else 1.0
    sc = ax.scatter(xs, ys, c=v, s=point_size, marker="s", cmap="inferno",
                    vmin=0.0, vmax=vmax_log, edgecolors="none")
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])
    return sc


def fig_to_b64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110, facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# === load CSVs ===
print(f"reading {len(CSV_PATHS)} CSV file(s)...")
dfs = []
for path in CSV_PATHS:
    p = Path(path)
    if not p.exists():
        print(f"  WARN: not found, skipping: {p}")
        continue
    if SKIP_TYPE_ROW:
        d = pd.read_csv(p, skiprows=[1], low_memory=False)
    else:
        d = pd.read_csv(p, low_memory=False)
    d["__source__"] = p.name
    print(f"  {p.name}: {len(d):,} rows × {len(d.columns)} cols")
    dfs.append(d)

assert dfs, "no CSV files read"

# 첫 CSV의 칼럼 순서를 표준으로
ref_cols = list(dfs[0].columns)
df = pd.concat(dfs, ignore_index=True, sort=False)
ordered = [c for c in ref_cols if c in df.columns] + \
          [c for c in df.columns if c not in ref_cols]
df = df[ordered]
print(f"combined: {len(df):,} rows × {len(df.columns)} cols")


# === detect cols ===
cmap = {c.lower(): c for c in df.columns}
x_col   = cmap["xdiepos"]
y_col   = cmap["ydiepos"]
lot_col  = cmap.get("lotid")
wseq_col = cmap.get("waferseq")
type_col = cmap.get(TYPE_COL.lower())
if type_col:
    print(f"  type column: '{type_col}'")
else:
    print(f"  '{TYPE_COL}' column not found — type filtering disabled")

# 좌표 강제 숫자화
for _c in (x_col, y_col):
    df[_c] = pd.to_numeric(df[_c], errors="coerce")
_before = len(df)
df = df.dropna(subset=[x_col, y_col]).reset_index(drop=True)
if len(df) < _before:
    print(f"  dropped {_before - len(df)} rows with non-numeric coords")
df[x_col] = df[x_col].astype(int)
df[y_col] = df[y_col].astype(int)


# === detect fail cols (fail_cnt_total 뒤) ===
total_marker = None
for cand in ("fail_cnt_total", "failcnt_total", "fail_total"):
    if cand in cmap:
        total_marker = cmap[cand]
        break

if total_marker is not None:
    boundary = list(df.columns).index(total_marker)
    candidate_cols = list(df.columns[boundary:])
    for _c in candidate_cols:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")
    df[candidate_cols] = df[candidate_cols].fillna(0)
    fail_cols = [c for c in candidate_cols[1:]
                 if pd.api.types.is_numeric_dtype(df[c])]
    print(f"'{total_marker}' at col {boundary} -> {len(fail_cols)} fail cols")
else:
    pat = re.compile(r"^fail", re.IGNORECASE)
    candidate_cols = [c for c in df.columns if pat.search(c)]
    for _c in candidate_cols:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")
    df[candidate_cols] = df[candidate_cols].fillna(0)
    fail_cols = [c for c in candidate_cols if pd.api.types.is_numeric_dtype(df[c])]
    print(f"fail_cnt_total not found; regex fallback -> {len(fail_cols)} fail cols")

assert fail_cols, "no fail columns detected"


# === optional wafer filter ===
if WAFER_FILTER and lot_col and wseq_col:
    lot, wseq = WAFER_FILTER.split(":", 1)
    df = df[(df[lot_col].astype(str) == lot) &
            (df[wseq_col].astype(str) == wseq)].copy()
    print(f"  filtered to wafer {WAFER_FILTER}: {len(df):,} rows")


# === group fail cols by prefix ===
groups = {}
for c in fail_cols:
    g, idx = parse_group(c)
    groups.setdefault(g, []).append((idx if idx is not None else 10**9, c))
for g in groups:
    groups[g].sort()
print("groups:", ", ".join(
    f"{g}({len(v)})" for g, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
))


# === canonical positions (union across all rows) ===
positions = (df[[x_col, y_col]].drop_duplicates()
             .sort_values([y_col, x_col]).reset_index(drop=True))
xs_full = positions[x_col].values
ys_full = positions[y_col].values
n_pos = len(positions)
print(f"  unique die positions: {n_pos:,}")


# === aggregate per type ===
def aggregate(sub):
    g = sub.groupby([x_col, y_col])[fail_cols].sum()
    g = g.reindex(pd.MultiIndex.from_arrays(
        [xs_full, ys_full], names=[x_col, y_col])).fillna(0)
    return g

type_values = []
sources = [("__ALL__", df)]
if type_col:
    type_values = sorted(df[type_col].astype(str).dropna().unique().tolist())
    type_values = [t for t in type_values if t and t.lower() != "nan"]
    sources += [(t, df[df[type_col].astype(str) == t]) for t in type_values]

print(f"aggregating across {len(sources)} type bucket(s): "
      f"{[name for name, _ in sources]}")
agg_dfs = {}
for name, sub in sources:
    if len(sub) == 0:
        continue
    agg_dfs[name] = aggregate(sub)


# === static plots (use __ALL__) ===
g_all = agg_dfs["__ALL__"]
plot_b64 = {}
group_plots = []

# 1. Overview
total = g_all.sum(axis=1).values
fig, ax = plt.subplots(figsize=(6.5, 6.5))
sc = wafer_map(ax, xs_full, ys_full, total,
               f"TOTAL FAIL (all data, {len(fail_cols)} cols)")
plt.colorbar(sc, ax=ax, shrink=0.75, label="log1p(fail)")
plot_b64["overview"] = fig_to_b64(fig)

# 2. Pareto
totals = g_all.sum().sort_values(ascending=False)
top_n = min(40, len(totals))
fig, ax = plt.subplots(figsize=(12, 4))
ax.bar(range(top_n), totals.head(top_n).values, color="#ffb000")
ax.set_xticks(range(top_n))
ax.set_xticklabels(totals.head(top_n).index, rotation=70, fontsize=7, ha="right")
ax.set_ylabel("total fail (log)"); ax.set_yscale("log")
ax.set_title(f"Top {top_n} of {len(totals)} fail columns")
ax.grid(axis="y", alpha=0.3); fig.tight_layout()
plot_b64["pareto"] = fig_to_b64(fig)

# 3. Per-group small multiples
print("rendering per-group small multiples...")
for g_name, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    cols_in_group = [c for _, c in items]
    n_all = len(cols_in_group)
    plotted = cols_in_group[:TOP_PER_GROUP]
    n = len(plotted)
    if n == 0:
        continue
    ncols = min(6, max(3, int(np.ceil(np.sqrt(n)))))
    nrows = (n + ncols - 1) // ncols
    gmax = float(g_all[plotted].to_numpy().max() or 1)
    gvmax = float(np.log1p(gmax))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols*2.2, nrows*2.4))
    axes = np.atleast_2d(axes).reshape(nrows, ncols)
    last_sc = None
    for i, c in enumerate(plotted):
        r, cc = divmod(i, ncols)
        last_sc = wafer_map(axes[r, cc], xs_full, ys_full,
                            g_all[c].values, c, vmax_log=gvmax)
    for j in range(n, nrows*ncols):
        r, cc = divmod(j, ncols); axes[r, cc].axis("off")
    if last_sc is not None:
        fig.colorbar(last_sc, ax=axes.ravel().tolist(),
                     shrink=0.6, label="log1p(fail)")
    suffix = f" (showing {n} of {n_all})" if n < n_all else ""
    fig.suptitle(f"group: {g_name}{suffix}", fontsize=10, y=0.995)
    group_plots.append((g_name, n_all, fig_to_b64(fig)))


# === interactive data ===
if MAX_INTERACTIVE_COLS is not None and len(fail_cols) > MAX_INTERACTIVE_COLS:
    selected_cols = list(totals.head(MAX_INTERACTIVE_COLS).index)
    print(f"  interactive: top {len(selected_cols)} / {len(fail_cols)} cols")
else:
    selected_cols = fail_cols
    print(f"  interactive: all {len(selected_cols)} cols included")

agg_data = {}
for name, g in agg_dfs.items():
    d = {c: np.round(np.log1p(g[c].values.astype(float)), 2).tolist()
         for c in selected_cols}
    d["__TOTAL__"] = np.round(np.log1p(g.sum(axis=1).values.astype(float)), 2).tolist()
    agg_data[name] = d

group_options_interactive = {}
for c in selected_cols:
    g, _ = parse_group(c)
    group_options_interactive.setdefault(g, []).append(c)

vmax_global = 0.0
for d in agg_data.values():
    for arr in d.values():
        if arr:
            m = max(arr)
            if m > vmax_global:
                vmax_global = m


# === build HTML ===
print("building HTML...")

js_data = {
    "AGG": agg_data,
    "XS": [int(v) for v in xs_full],
    "YS": [int(v) for v in ys_full],
    "GROUPS": group_options_interactive,
    "TYPES": ["__ALL__"] + type_values,
    "VMAX": float(vmax_global),
    "PSIZE": max(4, POINT_SIZE // 2),
}

sources_str = ", ".join(Path(p).name for p in CSV_PATHS)
meta_html = (
    f"files ({len(CSV_PATHS)}): {sources_str}<br>"
    f"rows: {len(df):,} &middot; "
    f"unique die positions: {n_pos:,} &middot; "
    f"fail cols: {len(fail_cols)} &middot; "
    f"groups: {len(groups)} &middot; "
    f"types: {len(type_values) if type_values else 'n/a'}"
)

html_parts = ["""<!doctype html>
<html><head><meta charset="utf-8">
<title>Fail Map Report</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;background:#0c1118;color:#e6edf3;
       margin:0;padding:24px;max-width:1400px;margin-left:auto;margin-right:auto}
  h1{color:#ffb000;font-size:20px;border-bottom:1px solid #2c3645;padding-bottom:10px;
     letter-spacing:.05em}
  h2{color:#ffb000;font-size:13px;margin-top:36px;letter-spacing:.05em;
     text-transform:uppercase}
  h3{color:#8b949e;font-size:12px;margin-top:24px;font-weight:500}
  .meta{color:#8b949e;font-size:12px;font-family:ui-monospace,SFMono-Regular,monospace;
        margin-top:8px;line-height:1.7}
  .controls{display:flex;gap:14px;align-items:flex-end;margin:20px 0;flex-wrap:wrap}
  .ctl label{display:block;font-size:10px;color:#8b949e;text-transform:uppercase;
             letter-spacing:.08em;margin-bottom:4px}
  select{background:#161d28;color:#e6edf3;border:1px solid #2c3645;padding:7px 10px;
         border-radius:4px;font-family:ui-monospace,monospace;font-size:12px;min-width:240px}
  select:hover{border-color:#ffb000}
  img{display:block;max-width:100%;background:#fff;border-radius:6px;margin:8px 0}
  #plot{background:#fff;border-radius:6px;padding:8px;margin-top:8px}
  .stats{color:#8b949e;font-size:11px;font-family:ui-monospace,monospace;
         margin-top:8px;padding:10px 14px;background:#161d28;border-radius:4px}
  .note{color:#8b949e;font-size:11px;margin:4px 0 12px}
  nav{position:sticky;top:0;background:#0c1118;border-bottom:1px solid #2c3645;
      padding:8px 0;margin:0 0 16px;z-index:10}
  nav a{color:#8b949e;text-decoration:none;font-size:12px;margin-right:18px}
  nav a:hover{color:#ffb000}
</style></head>
<body>
<h1>FAIL MAP REPORT</h1>"""]
html_parts.append(f"<div class='meta'>{meta_html}</div>")
html_parts.append("""
<nav>
  <a href="#overview">1. Overview</a>
  <a href="#pareto">2. Pareto</a>
  <a href="#groups">3. Per-group</a>
  <a href="#interactive">4. Interactive</a>
</nav>
""")

html_parts.append("<h2 id='overview'>1. Overview &mdash; total fail per die</h2>")
html_parts.append("<div class='note'>모든 입력 파일과 모든 type 합산. color = log(1 + fail).</div>")
html_parts.append(f"<img src='data:image/png;base64,{plot_b64['overview']}'>")

html_parts.append("<h2 id='pareto'>2. Pareto &mdash; top fail columns</h2>")
html_parts.append(f"<img src='data:image/png;base64,{plot_b64['pareto']}'>")

html_parts.append("<h2 id='groups'>3. Per-group small multiples</h2>")
for g_name, n_all, b64 in group_plots:
    html_parts.append(f"<h3>group '{g_name}' &mdash; {n_all} columns</h3>")
    html_parts.append(f"<img src='data:image/png;base64,{b64}'>")

html_parts.append("<h2 id='interactive'>4. Interactive explorer</h2>")
html_parts.append("<div class='note'>type / group / column 드롭다운으로 자유롭게 탐색. "
                  "type 은 여러 CSV 의 같은 type 끼리 합쳐서 보여줌.</div>")
html_parts.append("""
<div class="controls">
  <div class="ctl"><label>type</label><select id="typeSel"></select></div>
  <div class="ctl"><label>group</label><select id="groupSel"></select></div>
  <div class="ctl"><label>column</label><select id="colSel"></select></div>
</div>
<div id="plot"></div>
<div class="stats" id="stats"></div>
""")

html_parts.append("<script>")
html_parts.append("const D = " + json.dumps(js_data, separators=(",", ":")) + ";")
html_parts.append(r"""
const AGG = D.AGG, XS = D.XS, YS = D.YS, GROUPS = D.GROUPS,
      TYPES = D.TYPES, VMAX = D.VMAX, PSIZE = D.PSIZE;

const typeSel  = document.getElementById('typeSel');
const groupSel = document.getElementById('groupSel');
const colSel   = document.getElementById('colSel');
const statsEl  = document.getElementById('stats');

TYPES.forEach(t => {
  const o = document.createElement('option');
  o.value = t;
  o.textContent = (t === '__ALL__') ? '\u2014 all (combined) \u2014' : t;
  typeSel.appendChild(o);
});

const groupNames = Object.keys(GROUPS).sort();
[['__ALL__','\u2014 all columns \u2014'],
 ['__TOTAL__','\u2014 total only \u2014'],
 ...groupNames.map(g => [g, g])].forEach(([v, t]) => {
  const o = document.createElement('option');
  o.value = v; o.textContent = t;
  groupSel.appendChild(o);
});

function refreshCols() {
  const g = groupSel.value;
  colSel.innerHTML = '';
  let cols;
  if (g === '__ALL__') {
    cols = ['__TOTAL__', ...Object.keys(AGG['__ALL__']).filter(k => k !== '__TOTAL__')];
  } else if (g === '__TOTAL__') {
    cols = ['__TOTAL__'];
  } else {
    cols = GROUPS[g];
  }
  cols.forEach(c => {
    const o = document.createElement('option');
    o.value = c;
    o.textContent = c === '__TOTAL__' ? 'TOTAL (sum of all cols)' : c;
    colSel.appendChild(o);
  });
  draw();
}

function draw() {
  const t = typeSel.value;
  const c = colSel.value;
  if (!AGG[t] || !AGG[t][c]) return;
  const colors = AGG[t][c];

  let nonzero = 0, sumOrig = 0, maxLog = 0;
  for (const v of colors) {
    if (v > 0) { nonzero++; sumOrig += Math.expm1(v); }
    if (v > maxLog) maxLog = v;
  }
  const maxOrig = Math.round(Math.expm1(maxLog));

  statsEl.textContent =
    'type: ' + (t === '__ALL__' ? '(all)' : t) +
    '   \u00b7   column: ' + c +
    '   \u00b7   die with fails: ' + nonzero.toLocaleString() + ' / ' + colors.length.toLocaleString() +
    '   \u00b7   total fail: ' + Math.round(sumOrig).toLocaleString() +
    '   \u00b7   max per die: ' + maxOrig.toLocaleString();

  const trace = {
    x: XS, y: YS,
    mode: 'markers',
    type: 'scattergl',
    marker: {
      color: colors,
      colorscale: 'Inferno',
      size: PSIZE,
      symbol: 'square',
      cmin: 0, cmax: VMAX,
      colorbar: { title: 'log1p(fail)', thickness: 14 }
    },
    hovertemplate: 'x=%{x}, y=%{y}<br>log1p=%{marker.color:.2f}<extra></extra>'
  };
  const layout = {
    title: { text: (t === '__ALL__' ? '(all)' : t) + '  |  ' + c, font: { size: 13 } },
    xaxis: { scaleanchor: 'y', showgrid: false, zeroline: false },
    yaxis: { showgrid: false, zeroline: false },
    height: 720,
    margin: { l: 40, r: 40, t: 50, b: 40 },
    plot_bgcolor: '#fafafa',
    paper_bgcolor: '#fff'
  };
  Plotly.react('plot', [trace], layout, { displaylogo: false, responsive: true });
}

typeSel.addEventListener('change', draw);
groupSel.addEventListener('change', refreshCols);
colSel.addEventListener('change', draw);
refreshCols();
""")
html_parts.append("</script></body></html>")

Path(OUTPUT_HTML).write_text("\n".join(html_parts), encoding="utf-8")
size_mb = Path(OUTPUT_HTML).stat().st_size / 1024 / 1024
print(f"\nHTML saved -> {OUTPUT_HTML}  ({size_mb:.1f} MB)")
if size_mb > 100:
    print("  * 용량이 큽니다. MAX_INTERACTIVE_COLS = 100 같이 제한하면 작아집니다.")
