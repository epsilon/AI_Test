"""
map_fail_viz.py — multi-CSV die fail map visualizer (visual workbench)

위 셀에서 정의:
    CSV_PATHS = ["w1.csv", "w2.csv", ...]   # 또는 CSV_PATH = "data.csv"
    # 그다음 셀에 이 파일 내용 붙여넣고 실행

출력 OUTPUT_HTML (기본 'fail_report.html') 한 파일에:
    1. Overview wafer map
    2. Pareto
    3. Per-group small multiples
    4. Workbench
       - 좌측: 각 wafer 의 썸네일(전체 fault map) + 이름
       - 드래그/클릭으로 워크벤치로 '이동'
       - 우측 상단: 합쳐진(SUM/MEAN/MAX) 컬럼별 wafer map
       - 우측 하단: 활성 wafer 각각의 현재 컬럼 미니 플롯 (비교용)
"""

# === CONFIG ===
try: CSV_PATHS
except NameError:
    try: CSV_PATHS = [CSV_PATH]
    except NameError: CSV_PATHS = ["your_data.csv"]
if not isinstance(CSV_PATHS, (list, tuple)):
    CSV_PATHS = [CSV_PATHS]

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

try: SHOW_THUMBNAILS
except NameError: SHOW_THUMBNAILS = True


# === imports ===
import re, json, base64
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


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


def fig_to_b64(fig, dpi=110, tight=True):
    buf = BytesIO()
    if tight:
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi, facecolor="white")
    else:
        fig.savefig(buf, format="png", dpi=dpi, facecolor="black")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# === load CSVs ===
print(f"reading {len(CSV_PATHS)} CSV file(s)...")
dfs = []
for path in CSV_PATHS:
    p = Path(path)
    if not p.exists():
        print(f"  WARN: not found: {p}"); continue
    if SKIP_TYPE_ROW:
        d = pd.read_csv(p, skiprows=[1], low_memory=False)
    else:
        d = pd.read_csv(p, low_memory=False)
    d["__source__"] = p.name
    print(f"  {p.name}: {len(d):,} rows × {len(d.columns)} cols")
    dfs.append(d)
assert dfs, "no CSV files read"

ref_cols = list(dfs[0].columns)
df = pd.concat(dfs, ignore_index=True, sort=False)
ordered = [c for c in ref_cols if c in df.columns] + \
          [c for c in df.columns if c not in ref_cols]
df = df[ordered]
print(f"combined: {len(df):,} rows × {len(df.columns)} cols")


# === detect columns ===
cmap = {c.lower(): c for c in df.columns}
x_col   = cmap["xdiepos"]; y_col = cmap["ydiepos"]
lot_col  = cmap.get("lotid")
wseq_col = cmap.get("waferseq")
item_col = cmap.get("item")
temp_col = cmap.get("temp")

for _c in (x_col, y_col):
    df[_c] = pd.to_numeric(df[_c], errors="coerce")
_before = len(df)
df = df.dropna(subset=[x_col, y_col]).reset_index(drop=True)
if len(df) < _before:
    print(f"  dropped {_before - len(df)} rows with non-numeric coords")
df[x_col] = df[x_col].astype(int)
df[y_col] = df[y_col].astype(int)


# === detect fail cols ===
total_marker = None
for cand in ("fail_cnt_total", "failcnt_total", "fail_total"):
    if cand in cmap:
        total_marker = cmap[cand]; break

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


# === canonical positions ===
positions = (df[[x_col, y_col]].drop_duplicates()
             .sort_values([y_col, x_col]).reset_index(drop=True))
xs_full = positions[x_col].values
ys_full = positions[y_col].values
n_pos = len(positions)
print(f"  unique die positions: {n_pos:,}")
pos_idx = pd.MultiIndex.from_arrays([xs_full, ys_full], names=[x_col, y_col])


def aggregate(sub):
    g = sub.groupby([x_col, y_col])[fail_cols].sum()
    return g.reindex(pos_idx).fillna(0)


# === per-wafer aggregation ===
entity_cols = [c for c in [lot_col, wseq_col, item_col, temp_col] if c]
if not entity_cols:
    entity_cols = ["__source__"]
print(f"  wafer entity keys: {entity_cols}")

wafers = {}
g_all = aggregate(df)

for keys, sub in df.groupby(entity_cols, dropna=False, sort=True):
    if not isinstance(keys, tuple):
        keys = (keys,)
    wid = f"w{len(wafers):04d}"
    label_parts = []
    for kcol, kval in zip(entity_cols, keys):
        if pd.isna(kval):
            s = "?"
        else:
            s = str(kval)
        if kcol == wseq_col:    s = f"W{s}"
        elif kcol == temp_col:  s = f"{s}\u00b0"
        label_parts.append(s)
    label = " · ".join(label_parts)
    wafers[wid] = {
        "label": label,
        "n_rows": len(sub),
        "agg": aggregate(sub),
    }
print(f"  enumerated {len(wafers)} wafer entries")


# === thumbnails (per wafer, total-fail map) ===
def make_thumb(values, vmax_log, s_pts, size_inch=1.55, dpi=72):
    fig = plt.figure(figsize=(size_inch, size_inch), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    v = np.log1p(np.asarray(values, dtype=float))
    ax.scatter(xs_full, ys_full, c=v, s=s_pts, marker="s",
               cmap="inferno", vmin=0, vmax=vmax_log, edgecolors="none")
    ax.set_aspect("equal")
    ax.set_xlim(xs_full.min() - 1, xs_full.max() + 1)
    ax.set_ylim(ys_full.min() - 1, ys_full.max() + 1)
    ax.axis("off"); ax.set_facecolor("black")
    return fig_to_b64(fig, dpi=dpi, tight=False)

if SHOW_THUMBNAILS:
    print(f"rendering {len(wafers)} thumbnails...")
    # 공통 vmax (모든 wafer 비교 가능하도록)
    max_total = max((float(w["agg"].sum(axis=1).max()) for w in wafers.values()),
                    default=1.0)
    thumb_vmax_log = float(np.log1p(max_total or 1))
    # 마커 크기 자동
    thumb_px = 1.55 * 72
    thumb_s = max(3, min(40, int((thumb_px / max(1.0, np.sqrt(n_pos))) ** 2)))
    for wid, w in wafers.items():
        total = w["agg"].sum(axis=1).values
        w["thumb"] = make_thumb(total, thumb_vmax_log, thumb_s)
else:
    for w in wafers.values():
        w["thumb"] = ""


# === static plots ===
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
    if n == 0: continue
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


# === workbench JSON ===
if MAX_INTERACTIVE_COLS is not None and len(fail_cols) > MAX_INTERACTIVE_COLS:
    selected_cols = list(totals.head(MAX_INTERACTIVE_COLS).index)
    print(f"  workbench: top {len(selected_cols)} / {len(fail_cols)} cols")
else:
    selected_cols = fail_cols
    print(f"  workbench: all {len(selected_cols)} cols included")

def encode_arr(arr):
    return [int(v) if v == int(v) else round(float(v), 2)
            for v in np.nan_to_num(arr, nan=0.0)]

print("encoding wafer arrays...")
wafers_json = {}
for wid, w in wafers.items():
    g = w["agg"]
    data = {c: encode_arr(g[c].values) for c in selected_cols}
    data["__TOTAL__"] = encode_arr(g.sum(axis=1).values)
    wafers_json[wid] = {
        "label": w["label"],
        "nRows": int(w["n_rows"]),
        "thumb": w["thumb"],
        "data": data,
    }

group_options_interactive = {}
for c in selected_cols:
    g, _ = parse_group(c)
    group_options_interactive.setdefault(g, []).append(c)

# 미니 플롯용 vmax (개별 wafer 단일 값의 최대)
mini_vmax = 0.0
for w in wafers.values():
    g = w["agg"]
    if selected_cols:
        m = float(g[selected_cols].to_numpy().max())
        if m > mini_vmax: mini_vmax = m
    mt = float(g.sum(axis=1).max())
    if mt > mini_vmax: mini_vmax = mt
mini_vmax_log = float(np.log1p(mini_vmax or 1))


# === build HTML ===
print("building HTML...")

js_data = {
    "WAFERS": wafers_json,
    "XS": [int(v) for v in xs_full],
    "YS": [int(v) for v in ys_full],
    "GROUPS": group_options_interactive,
    "PSIZE": max(4, POINT_SIZE // 2),
    "MINI_VMAX": mini_vmax_log,
}

sources_str = ", ".join(Path(p).name for p in CSV_PATHS)
meta_html = (
    f"files ({len(CSV_PATHS)}): {sources_str}<br>"
    f"rows: {len(df):,} &middot; die positions: {n_pos:,} &middot; "
    f"fail cols: {len(fail_cols)} &middot; groups: {len(groups)} &middot; "
    f"wafers: {len(wafers)}"
)

html = ["""<!doctype html>
<html><head><meta charset="utf-8">
<title>Fail Map Report</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;background:#0c1118;color:#e6edf3;
       margin:0;padding:24px;max-width:1500px;margin-left:auto;margin-right:auto}
  h1{color:#ffb000;font-size:20px;border-bottom:1px solid #2c3645;padding-bottom:10px;
     letter-spacing:.05em}
  h2{color:#ffb000;font-size:13px;margin-top:36px;letter-spacing:.05em;text-transform:uppercase}
  h3{color:#8b949e;font-size:11px;margin:18px 0 8px;font-weight:500;
     text-transform:uppercase;letter-spacing:.06em}
  .meta{color:#8b949e;font-size:12px;font-family:ui-monospace,SFMono-Regular,monospace;
        margin-top:8px;line-height:1.7}
  img.staticImg{display:block;max-width:100%;background:#fff;border-radius:6px;margin:8px 0}
  nav{position:sticky;top:0;background:#0c1118;border-bottom:1px solid #2c3645;
      padding:8px 0;margin:0 0 16px;z-index:20}
  nav a{color:#8b949e;text-decoration:none;font-size:12px;margin-right:18px}
  nav a:hover{color:#ffb000}
  .note{color:#8b949e;font-size:11px;margin:4px 0 12px}

  /* workbench grid */
  .wb-grid{display:grid;grid-template-columns:320px 1fr;gap:16px;margin-top:12px}
  .lib,.bench{background:#161d28;border:1px solid #2c3645;border-radius:6px;padding:14px}
  #libFilter{width:100%;background:#0c1118;border:1px solid #2c3645;color:#e6edf3;
             padding:6px 8px;border-radius:4px;font-size:12px;margin-bottom:6px;box-sizing:border-box}
  .lib-actions{display:flex;gap:6px;margin-bottom:10px}
  .lib-actions button{flex:1;background:#0c1118;color:#8b949e;border:1px solid #2c3645;
                      padding:5px 8px;border-radius:4px;font-size:11px;cursor:pointer;
                      font-family:ui-monospace,monospace}
  .lib-actions button:hover{color:#ffb000;border-color:#ffb000}

  .wafer-list{max-height:780px;overflow-y:auto;padding-right:4px}
  .wafer-card{display:flex;gap:10px;align-items:center;background:#0c1118;
              border:1px solid #2c3645;border-radius:4px;padding:6px;margin:4px 0;
              cursor:grab;transition:border-color .12s}
  .wafer-card:hover{border-color:#ffb000}
  .wafer-card.dragging{opacity:.4}
  .wafer-card.hidden{display:none}
  .wafer-card img.thumb{width:54px;height:54px;border-radius:3px;flex-shrink:0;
                        image-rendering:pixelated;background:#000}
  .wafer-card .info{flex:1;min-width:0}
  .wafer-card .info .title{font-size:11px;color:#e6edf3;font-weight:500;line-height:1.35;
                           word-break:break-word}
  .wafer-card .info .meta{font-size:10px;color:#8b949e;margin-top:3px;
                          font-family:ui-monospace,monospace}

  .drop-zone{min-height:96px;border:2px dashed #2c3645;border-radius:5px;padding:10px;
             display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;
             transition:all .12s}
  .drop-zone.over{border-color:#ffb000;background:#1a2230}
  .drop-zone.empty::before{content:'\2014  드래그하거나 카드 클릭으로 wafer 추가  \2014';
                           color:#4b5563;font-size:11px;margin:auto;
                           font-family:ui-monospace,monospace}
  .dz-tile{background:#0c1118;border:1px solid #ffb000;border-radius:5px;padding:6px;
           display:flex;flex-direction:column;align-items:center;gap:4px;
           position:relative;width:84px}
  .dz-tile img{width:64px;height:64px;border-radius:3px;image-rendering:pixelated;background:#000}
  .dz-tile .lbl{font-size:9px;color:#e6edf3;font-family:ui-monospace,monospace;
                text-align:center;line-height:1.2;max-width:74px;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dz-tile .x{position:absolute;top:-7px;right:-7px;background:#2c3645;color:#e6edf3;
              width:18px;height:18px;border-radius:50%;text-align:center;
              font-size:12px;line-height:18px;cursor:pointer;font-weight:bold;
              border:1px solid #ffb000}
  .dz-tile .x:hover{background:#ff6b6b}

  .controls{display:flex;gap:14px;align-items:flex-end;margin:14px 0;flex-wrap:wrap}
  .ctl label{display:block;font-size:10px;color:#8b949e;text-transform:uppercase;
             letter-spacing:.08em;margin-bottom:4px}
  select{background:#0c1118;color:#e6edf3;border:1px solid #2c3645;padding:7px 10px;
         border-radius:4px;font-family:ui-monospace,monospace;font-size:12px;min-width:180px}
  select:hover{border-color:#ffb000}
  #plot{background:#fff;border-radius:6px;padding:8px;margin-top:8px}
  .stats{color:#8b949e;font-size:11px;font-family:ui-monospace,monospace;
         margin-top:8px;padding:10px 14px;background:#0c1118;border-radius:4px;
         border:1px solid #2c3645}

  /* mini plots */
  .mini-section{margin-top:18px;padding-top:14px;border-top:1px solid #2c3645}
  .mini-plots{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
  .mini-plot{background:#fff;border-radius:4px;overflow:hidden}
  .mini-plot .mp-title{background:#161d28;color:#e6edf3;font-size:10px;padding:5px 8px;
                       font-family:ui-monospace,monospace;border-bottom:1px solid #2c3645;
                       white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mini-plot .mp-plot{height:200px}
  .mini-empty{color:#4b5563;font-size:11px;font-family:ui-monospace,monospace;padding:12px}
</style></head>
<body>
<h1>FAIL MAP REPORT</h1>"""]
html.append(f"<div class='meta'>{meta_html}</div>")
html.append("""
<nav>
  <a href="#overview">1. Overview</a>
  <a href="#pareto">2. Pareto</a>
  <a href="#groups">3. Per-group</a>
  <a href="#workbench">4. Workbench</a>
</nav>
""")

html.append("<h2 id='overview'>1. Overview &mdash; total fail per die</h2>")
html.append("<div class='note'>모든 입력 파일·모든 wafer 합산. color = log(1 + fail).</div>")
html.append(f"<img class='staticImg' src='data:image/png;base64,{plot_b64['overview']}'>")

html.append("<h2 id='pareto'>2. Pareto &mdash; top fail columns</h2>")
html.append(f"<img class='staticImg' src='data:image/png;base64,{plot_b64['pareto']}'>")

html.append("<h2 id='groups'>3. Per-group small multiples</h2>")
for g_name, n_all, b64 in group_plots:
    html.append(f"<h3>group '{g_name}' &mdash; {n_all} columns</h3>")
    html.append(f"<img class='staticImg' src='data:image/png;base64,{b64}'>")

html.append("""
<h2 id='workbench'>4. Workbench</h2>
<div class='note'>왼쪽 라이브러리의 wafer(썸네일은 전체 fault 합산)를 드래그하거나 클릭해서 워크벤치로 옮기세요. 워크벤치에 올라간 wafer 들은 SUM/MEAN/MAX 로 합쳐서 큰 plot 으로, 그리고 아래쪽에 wafer 별 미니 plot 으로 같이 보여줍니다.</div>
<div class="wb-grid">
  <div class="lib">
    <h3>Library</h3>
    <input type="search" id="libFilter" placeholder="filter (label 검색)...">
    <div class="lib-actions">
      <button id="addAll">+ all visible</button>
      <button id="clearAll">clear bench</button>
    </div>
    <div class="wafer-list" id="waferList"></div>
  </div>
  <div class="bench">
    <h3>Workbench</h3>
    <div class="drop-zone empty" id="dropZone"></div>
    <div class="controls">
      <div class="ctl"><label>operation</label><select id="opSel">
        <option value="sum">SUM</option>
        <option value="mean">MEAN</option>
        <option value="max">MAX</option>
      </select></div>
      <div class="ctl"><label>group</label><select id="groupSel"></select></div>
      <div class="ctl"><label>column</label><select id="colSel"></select></div>
    </div>
    <div id="plot"></div>
    <div class="stats" id="stats">(워크벤치가 비어있음)</div>
    <div class="mini-section">
      <h3>Individual wafer maps · current column</h3>
      <div class="mini-plots" id="miniPlots">
        <div class="mini-empty">wafer 를 워크벤치에 올리면 여기에 개별 plot 이 나타납니다.</div>
      </div>
    </div>
  </div>
</div>
""")

html.append("<script>")
html.append("const D = " + json.dumps(js_data, separators=(",", ":")) + ";")
html.append(r"""
const WAFERS = D.WAFERS, XS = D.XS, YS = D.YS, GROUPS = D.GROUPS,
      PSIZE = D.PSIZE, MINI_VMAX = D.MINI_VMAX;

const waferList = document.getElementById('waferList');
const dropZone  = document.getElementById('dropZone');
const groupSel  = document.getElementById('groupSel');
const colSel    = document.getElementById('colSel');
const opSel     = document.getElementById('opSel');
const statsEl   = document.getElementById('stats');
const filterEl  = document.getElementById('libFilter');
const miniBox   = document.getElementById('miniPlots');

const active = new Set();

// library cards
Object.entries(WAFERS).forEach(([wid, w]) => {
  const card = document.createElement('div');
  card.className = 'wafer-card';
  card.draggable = true;
  card.dataset.id = wid;
  card.dataset.search = w.label.toLowerCase();
  const thumbHtml = w.thumb
    ? `<img class="thumb" src="data:image/png;base64,${w.thumb}">`
    : `<div class="thumb" style="background:#222"></div>`;
  card.innerHTML = thumbHtml +
                   `<div class="info"><div class="title">${w.label}</div>` +
                   `<div class="meta">${w.nRows.toLocaleString()} rows</div></div>`;
  card.addEventListener('dragstart', e => {
    e.dataTransfer.setData('text/plain', wid);
    card.classList.add('dragging');
  });
  card.addEventListener('dragend', () => card.classList.remove('dragging'));
  card.addEventListener('click', () => addWafer(wid));
  waferList.appendChild(card);
});

// group / col dropdowns
const groupNames = Object.keys(GROUPS).sort();
[['__ALL__','\u2014 all columns \u2014'],
 ['__TOTAL__','\u2014 total only \u2014'],
 ...groupNames.map(g => [g, g])].forEach(([v, t]) => {
  const o = document.createElement('option');
  o.value = v; o.textContent = t; groupSel.appendChild(o);
});

function refreshCols() {
  const g = groupSel.value;
  colSel.innerHTML = '';
  let cols;
  if (g === '__ALL__') {
    const sample = Object.values(WAFERS)[0].data;
    cols = ['__TOTAL__', ...Object.keys(sample).filter(k => k !== '__TOTAL__')];
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
  drawAll();
}

// drag-drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('over');
  const wid = e.dataTransfer.getData('text/plain');
  if (wid) addWafer(wid);
});

function addWafer(wid) {
  if (active.has(wid) || !WAFERS[wid]) return;
  active.add(wid);
  updateLibraryVisibility();
  renderTiles();
  drawAll();
}
function removeWafer(wid) {
  active.delete(wid);
  updateLibraryVisibility();
  renderTiles();
  drawAll();
}

function renderTiles() {
  dropZone.innerHTML = '';
  if (active.size === 0) {
    dropZone.classList.add('empty');
    return;
  }
  dropZone.classList.remove('empty');
  active.forEach(wid => {
    const w = WAFERS[wid];
    const tile = document.createElement('div');
    tile.className = 'dz-tile';
    const thumbHtml = w.thumb
      ? `<img src="data:image/png;base64,${w.thumb}">`
      : `<div style="width:64px;height:64px;background:#222;border-radius:3px"></div>`;
    tile.innerHTML = `<span class="x" title="remove">\u00d7</span>` +
                     thumbHtml +
                     `<span class="lbl" title="${w.label}">${w.label}</span>`;
    tile.querySelector('.x').addEventListener('click', () => removeWafer(wid));
    dropZone.appendChild(tile);
  });
}

function updateLibraryVisibility() {
  const q = filterEl.value.toLowerCase();
  document.querySelectorAll('.wafer-card').forEach(card => {
    const inBench = active.has(card.dataset.id);
    const matches = card.dataset.search.includes(q);
    card.classList.toggle('hidden', inBench || !matches);
  });
}

filterEl.addEventListener('input', updateLibraryVisibility);

document.getElementById('addAll').addEventListener('click', () => {
  document.querySelectorAll('.wafer-card').forEach(card => {
    if (!card.classList.contains('hidden')) addWafer(card.dataset.id);
  });
});
document.getElementById('clearAll').addEventListener('click', () => {
  active.clear();
  updateLibraryVisibility(); renderTiles(); drawAll();
});

// ---- aggregation ----
function aggregateActive() {
  const col = colSel.value, op = opSel.value;
  const N = XS.length;
  if (active.size === 0) return null;
  const out = new Array(N).fill(0);
  let cnt = 0;
  for (const wid of active) {
    const arr = WAFERS[wid].data[col];
    if (!arr) continue;
    if (op === 'max') {
      for (let i = 0; i < N; i++) if (arr[i] > out[i]) out[i] = arr[i];
    } else {
      for (let i = 0; i < N; i++) out[i] += arr[i];
    }
    cnt++;
  }
  if (op === 'mean' && cnt > 0) {
    for (let i = 0; i < N; i++) out[i] /= cnt;
  }
  return out;
}

// ---- combined draw ----
function drawCombined() {
  const values = aggregateActive();
  if (!values) {
    Plotly.purge('plot');
    statsEl.textContent = '(워크벤치가 비어있음)';
    return;
  }
  const col = colSel.value, op = opSel.value;
  const colors = values.map(v => Math.log1p(Math.max(0, v)));
  const vmax = Math.max(1, ...colors);

  let nz = 0, sum = 0, mx = 0;
  for (const v of values) {
    if (v > 0) { nz++; sum += v; }
    if (v > mx) mx = v;
  }
  statsEl.textContent =
    'wafers: ' + active.size + '   \u00b7   op: ' + op.toUpperCase() +
    '   \u00b7   column: ' + col +
    '   \u00b7   die with fails: ' + nz.toLocaleString() + ' / ' + values.length.toLocaleString() +
    '   \u00b7   total: ' + Math.round(sum).toLocaleString() +
    '   \u00b7   max per die: ' + Math.round(mx).toLocaleString();

  Plotly.react('plot', [{
    x: XS, y: YS, mode: 'markers', type: 'scattergl',
    marker: {
      color: colors, colorscale: 'Inferno',
      size: PSIZE, symbol: 'square',
      cmin: 0, cmax: vmax,
      colorbar: { title: 'log1p(fail)', thickness: 14 }
    },
    hovertemplate: 'x=%{x}, y=%{y}<br>log1p=%{marker.color:.2f}<extra></extra>'
  }], {
    title: { text: active.size + ' wafer' + (active.size > 1 ? 's' : '') + ' \u00b7 ' + op + ' \u00b7 ' + col, font: { size: 13 } },
    xaxis: { scaleanchor: 'y', showgrid: false, zeroline: false },
    yaxis: { showgrid: false, zeroline: false },
    height: 620,
    margin: { l: 40, r: 40, t: 50, b: 40 },
    plot_bgcolor: '#fafafa', paper_bgcolor: '#fff'
  }, { displaylogo: false, responsive: true });
}

// ---- mini plots ----
function drawMinis() {
  miniBox.innerHTML = '';
  if (active.size === 0) {
    miniBox.innerHTML = '<div class="mini-empty">wafer 를 워크벤치에 올리면 여기에 개별 plot 이 나타납니다.</div>';
    return;
  }
  const col = colSel.value;
  active.forEach(wid => {
    const w = WAFERS[wid];
    const arr = w.data[col];
    if (!arr) return;
    const wrap = document.createElement('div');
    wrap.className = 'mini-plot';
    const t = document.createElement('div');
    t.className = 'mp-title';
    t.title = w.label;
    t.textContent = w.label;
    const p = document.createElement('div');
    p.className = 'mp-plot';
    wrap.appendChild(t); wrap.appendChild(p);
    miniBox.appendChild(wrap);

    const colors = arr.map(v => Math.log1p(Math.max(0, v)));
    Plotly.newPlot(p, [{
      x: XS, y: YS, mode: 'markers', type: 'scattergl',
      marker: {
        color: colors, colorscale: 'Inferno',
        size: Math.max(2, PSIZE / 3), symbol: 'square',
        cmin: 0, cmax: MINI_VMAX, showscale: false
      },
      hovertemplate: 'x=%{x}, y=%{y}<br>log1p=%{marker.color:.2f}<extra></extra>'
    }], {
      xaxis: { scaleanchor: 'y', showgrid: false, zeroline: false, visible: false },
      yaxis: { showgrid: false, zeroline: false, visible: false },
      margin: { l: 4, r: 4, t: 4, b: 4 },
      paper_bgcolor: '#fff', plot_bgcolor: '#fafafa'
    }, { displayModeBar: false, responsive: true, staticPlot: false });
  });
}

function drawAll() { drawCombined(); drawMinis(); }

groupSel.addEventListener('change', refreshCols);
colSel.addEventListener('change', drawAll);
opSel.addEventListener('change', drawAll);

refreshCols();
""")
html.append("</script></body></html>")

Path(OUTPUT_HTML).write_text("\n".join(html), encoding="utf-8")
size_mb = Path(OUTPUT_HTML).stat().st_size / 1024 / 1024
print(f"\nHTML saved -> {OUTPUT_HTML}  ({size_mb:.1f} MB)")
if size_mb > 100:
    print("  * 용량 큼. MAX_INTERACTIVE_COLS = 100 등으로 제한 가능.")
