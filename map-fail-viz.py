"""
map_fail_viz.py  —  die fail map visualizer (Jupyter-friendly)

사용법:
    위 셀에서 CSV_PATH 같은 변수를 미리 정의해두면 그 값을 그대로 씁니다.
    정의 안 했으면 아래 디폴트가 적용돼요.

    예) 위 셀:
        CSV_PATH = "/path/to/data.csv"
        # 그다음 셀에 이 파일 내용 붙여넣기

입력 CSV:
    - xdiepos, ydiepos                (die 좌표; 대소문자 무관)
    - fail_cnt_total                  (이 칼럼 '뒤'부터 fail 종류로 인식)
    - optional: LOTID, waferseq       (여러 wafer 합산/필터용)

출력:
    1. Overview wafer map (전체 fail 합)         — matplotlib
    2. Pareto bar chart                          — matplotlib
    3. Per-group small multiples                 — matplotlib
    4. 인터랙티브 HTML (group/column 드롭다운)   — Plotly
"""

# === CONFIG — 위 셀에서 미리 정의했으면 그 값 사용 ===
try: CSV_PATH
except NameError: CSV_PATH = "your_data.csv"

try: WAFER_FILTER
except NameError: WAFER_FILTER = None         # "LOTID:waferseq" 또는 None

try: TOP_PER_GROUP
except NameError: TOP_PER_GROUP = 48          # 그룹당 small multiple 최대 개수

try: POINT_SIZE
except NameError: POINT_SIZE = 18             # matplotlib 마커 크기

try: OUTPUT_HTML
except NameError: OUTPUT_HTML = "fail_interactive.html"  # 인터랙티브 HTML 출력 경로

try: MAX_INTERACTIVE_COLS
except NameError: MAX_INTERACTIVE_COLS = None  # HTML에 포함할 최대 fail 칼럼 수 (None=전부)

try: SKIP_TYPE_ROW
except NameError: SKIP_TYPE_ROW = True         # CSV 2번째 줄이 데이터 타입 표시 행이면 True


# === 코드 ===
import re, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def parse_group(col):
    """
    fail_cnt_bank0   -> ('bank', 0)
    fail_cn_bank12   -> ('bank', 12)
    fail_mat_5       -> ('mat', 5)
    fail_fmat_row_3  -> ('fmat_row', 3)
    """
    s = col.lower()
    s = re.sub(r"^fail_?(cn|cnt)?_?", "", s)
    m = re.match(r"^([a-z][a-z_]*?)_?(\d+)$", s)
    if m:
        g = m.group(1).strip("_") or "misc"
        return g, int(m.group(2))
    return (s or "misc"), None


def wafer_map(ax, xs, ys, values, title, vmax_log=None, point_size=None):
    """matplotlib die 산점도. log1p 컬러 스케일."""
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


# ---------- load ----------
# 헤더(1번째 줄) 다음의 데이터 타입 행(2번째 줄) 처리
if SKIP_TYPE_ROW:
    df = pd.read_csv(CSV_PATH, skiprows=[1], low_memory=False)
    print(f"rows: {len(df):,}   cols: {len(df.columns)}  "
          f"(skipped row 2 as type-annotation row)")
else:
    df = pd.read_csv(CSV_PATH, low_memory=False)
    print(f"rows: {len(df):,}   cols: {len(df.columns)}")
    # 안전망: 첫 데이터 행이 타입 표시처럼 보이면 자동 제거
    _type_words = {"int", "str", "string", "float", "double", "number", "numeric",
                   "object", "date", "datetime", "int64", "float64", "int32",
                   "bool", "boolean", "integer", "text", "char", "varchar"}
    if len(df) > 0:
        _first = set(df.iloc[0].astype(str).str.lower().str.strip().unique())
        _hits = _first & _type_words
        if len(_hits) >= 2:
            print(f"  type-annotation row auto-detected -> dropping (matched: {sorted(_hits)})")
            df = df.iloc[1:].reset_index(drop=True)

cmap = {c.lower(): c for c in df.columns}
x_col = cmap["xdiepos"]
y_col = cmap["ydiepos"]
lot_col  = cmap.get("lotid")
wseq_col = cmap.get("waferseq")

# 좌표 강제 숫자 변환 + 비정상 행 제거
for _c in (x_col, y_col):
    df[_c] = pd.to_numeric(df[_c], errors="coerce")
_before = len(df)
df = df.dropna(subset=[x_col, y_col]).reset_index(drop=True)
if len(df) < _before:
    print(f"  dropped {_before - len(df)} rows with non-numeric coords")
df[x_col] = df[x_col].astype(int)
df[y_col] = df[y_col].astype(int)

# fail 칼럼 = fail_cnt_total 뒤에 있는 모든 numeric 칼럼
total_marker = None
for cand in ("fail_cnt_total", "failcnt_total", "fail_total"):
    if cand in cmap:
        total_marker = cmap[cand]
        break

if total_marker is not None:
    boundary = df.columns.get_loc(total_marker)
    candidate_cols = list(df.columns[boundary:])    # total_marker 포함
    for _c in candidate_cols:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")
    df[candidate_cols] = df[candidate_cols].fillna(0)
    fail_cols = [c for c in candidate_cols[1:]
                 if pd.api.types.is_numeric_dtype(df[c])]
    print(f"'{total_marker}' at col {boundary} -> {len(fail_cols)} fail cols after it")
    has_total = True
else:
    pat = re.compile(r"^fail", re.IGNORECASE)
    candidate_cols = [c for c in df.columns if pat.search(c)]
    for _c in candidate_cols:
        df[_c] = pd.to_numeric(df[_c], errors="coerce")
    df[candidate_cols] = df[candidate_cols].fillna(0)
    fail_cols = [c for c in candidate_cols if pd.api.types.is_numeric_dtype(df[c])]
    print(f"fail_cnt_total not found; regex fallback -> {len(fail_cols)} fail cols")
    has_total = False

assert fail_cols, "no fail columns detected."

# wafer 필터 / 합산
if WAFER_FILTER and lot_col and wseq_col:
    lot, wseq = WAFER_FILTER.split(":", 1)
    keep_cols = ([total_marker] if has_total else []) + fail_cols + [x_col, y_col]
    df = df[(df[lot_col].astype(str) == lot) &
            (df[wseq_col].astype(str) == wseq)].copy()
    print(f"filtered to {WAFER_FILTER}: {len(df):,} rows")
elif lot_col and wseq_col:
    nw = df.groupby([lot_col, wseq_col]).ngroups
    if nw > 1:
        agg_cols = fail_cols + ([total_marker] if has_total else [])
        print(f"{nw} wafers in file -> aggregating (sum) by die position")
        df = df.groupby([x_col, y_col], as_index=False)[agg_cols].sum()

# 그룹 분류
groups = {}
for c in fail_cols:
    g, idx = parse_group(c)
    groups.setdefault(g, []).append((idx if idx is not None else 10**9, c))
for g in groups:
    groups[g].sort()

print("groups:", ", ".join(
    f"{g}({len(v)})"
    for g, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
))

xs, ys = df[x_col].values, df[y_col].values
print(f"x range: {int(xs.min())}..{int(xs.max())}    "
      f"y range: {int(ys.min())}..{int(ys.max())}")


# ---------- 1. Overview ----------
total = df[total_marker].values if has_total else df[fail_cols].sum(axis=1).values
fig, ax = plt.subplots(figsize=(6.5, 6.5))
title = "TOTAL FAIL" + (f" ({total_marker})" if has_total else f" (sum of {len(fail_cols)} cols)")
sc = wafer_map(ax, xs, ys, total, title)
plt.colorbar(sc, ax=ax, shrink=0.75, label="log1p(fail)")
plt.show()


# ---------- 2. Pareto ----------
totals = df[fail_cols].sum().sort_values(ascending=False)
top_n = min(40, len(totals))
fig, ax = plt.subplots(figsize=(12, 4))
ax.bar(range(top_n), totals.head(top_n).values, color="#ffb000")
ax.set_xticks(range(top_n))
ax.set_xticklabels(totals.head(top_n).index, rotation=70, fontsize=7, ha="right")
ax.set_ylabel("total fail (log)")
ax.set_yscale("log")
ax.set_title(f"Top {top_n} of {len(totals)} fail columns")
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()


# ---------- 3. Per-group small multiples ----------
for g, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    cols_in_group = [c for _, c in items]
    n_all = len(cols_in_group)
    plotted = cols_in_group[:TOP_PER_GROUP]
    n = len(plotted)

    ncols = min(6, max(3, int(np.ceil(np.sqrt(n)))))
    nrows = (n + ncols - 1) // ncols

    gmax = df[plotted].to_numpy().max() if n else 0
    gvmax = float(np.log1p(gmax if gmax > 0 else 1))

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 2.2, nrows * 2.4))
    axes = np.atleast_2d(axes).reshape(nrows, ncols)
    last_sc = None
    for i, c in enumerate(plotted):
        r, cc = divmod(i, ncols)
        last_sc = wafer_map(axes[r, cc], xs, ys, df[c].values, c, vmax_log=gvmax)
    for j in range(n, nrows * ncols):
        r, cc = divmod(j, ncols)
        axes[r, cc].axis("off")
    if last_sc is not None:
        fig.colorbar(last_sc, ax=axes.ravel().tolist(),
                     shrink=0.6, label="log1p(fail)")
    suffix = f"  (showing {n} of {n_all})" if n < n_all else ""
    fig.suptitle(f"group: {g}{suffix}", fontsize=10, y=0.995)
    plt.show()


# ---------- 4. Interactive HTML ----------
print("\nbuilding interactive HTML ...")

# HTML 에 포함할 칼럼 선정 (총합 기준 상위)
if MAX_INTERACTIVE_COLS is not None and len(fail_cols) > MAX_INTERACTIVE_COLS:
    selected_cols = list(totals.head(MAX_INTERACTIVE_COLS).index)
    print(f"  HTML에 포함: 상위 {len(selected_cols)} / {len(fail_cols)} 칼럼")
else:
    selected_cols = fail_cols
    print(f"  HTML에 포함: {len(selected_cols)} 칼럼 전체")

# log1p 적용 후 소수점 2자리로 반올림 (파일 크기 절감)
fail_data = {c: [round(float(v), 2) for v in np.log1p(df[c].values.astype(float))]
             for c in selected_cols}
total_log = [round(float(v), 2) for v in np.log1p(total.astype(float))]
fail_data["__TOTAL__"] = total_log

vmax = max((max(arr) for arr in fail_data.values() if arr), default=1.0)

# 선택된 칼럼들만으로 group 재구성
group_options = {}
for c in selected_cols:
    g, _ = parse_group(c)
    group_options.setdefault(g, []).append(c)

html_template = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Fail Map — Interactive</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;background:#0c1118;color:#e6edf3;
       margin:0;padding:20px;max-width:1400px;margin-left:auto;margin-right:auto}
  h1{color:#ffb000;font-size:18px;border-bottom:1px solid #2c3645;padding-bottom:10px;
     letter-spacing:.05em}
  .meta{color:#8b949e;font-size:12px;font-family:ui-monospace,SFMono-Regular,monospace;
        margin-top:8px;line-height:1.6}
  .controls{display:flex;gap:14px;align-items:flex-end;margin:20px 0;flex-wrap:wrap}
  .ctl label{display:block;font-size:10px;color:#8b949e;
             text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}
  select{background:#161d28;color:#e6edf3;border:1px solid #2c3645;padding:7px 10px;
         border-radius:4px;font-family:ui-monospace,monospace;font-size:12px;min-width:220px}
  select:hover{border-color:#ffb000}
  #plot{background:#fff;border-radius:6px;padding:8px;margin-top:8px}
  .stats{color:#8b949e;font-size:11px;font-family:ui-monospace,monospace;
         margin-top:8px;padding:8px 12px;background:#161d28;border-radius:4px}
</style></head>
<body>
<h1>FAIL MAP — INTERACTIVE</h1>
<div class="meta">__META__</div>

<div class="controls">
  <div class="ctl"><label>group</label><select id="groupSel"></select></div>
  <div class="ctl"><label>column</label><select id="colSel"></select></div>
</div>

<div id="plot"></div>
<div class="stats" id="stats"></div>

<script>
const DATA   = __DATA__;
const XS     = __XS__;
const YS     = __YS__;
const GROUPS = __GROUPS__;
const VMAX   = __VMAX__;
const PSIZE  = __PSIZE__;

const groupSel = document.getElementById('groupSel');
const colSel   = document.getElementById('colSel');
const statsEl  = document.getElementById('stats');

const groupNames = Object.keys(GROUPS).sort();
[['__ALL__','— all columns —'],
 ['__TOTAL__','— total only —'],
 ...groupNames.map(g => [g, g])].forEach(([v,t]) => {
  const o = document.createElement('option');
  o.value = v; o.textContent = t;
  groupSel.appendChild(o);
});

function refreshCols() {
  const g = groupSel.value;
  colSel.innerHTML = '';
  let cols;
  if (g === '__ALL__') {
    cols = ['__TOTAL__', ...Object.keys(DATA).filter(k => k !== '__TOTAL__')];
  } else if (g === '__TOTAL__') {
    cols = ['__TOTAL__'];
  } else {
    cols = GROUPS[g];
  }
  cols.forEach(c => {
    const o = document.createElement('option');
    o.value = c;
    o.textContent = c === '__TOTAL__' ? 'TOTAL (all fails summed)' : c;
    colSel.appendChild(o);
  });
  draw();
}

function draw() {
  const c = colSel.value;
  const colors = DATA[c];
  // expm1 로 원본 값 복원 (stats 용)
  let sum = 0, nonzero = 0, maxv = 0;
  for (const v of colors) {
    const orig = Math.expm1(v);
    sum += orig;
    if (orig > 0) nonzero++;
    if (orig > maxv) maxv = orig;
  }
  statsEl.textContent =
    `column: ${c}   ·   die with fails: ${nonzero.toLocaleString()} / ${colors.length.toLocaleString()}` +
    `   ·   total fail: ${Math.round(sum).toLocaleString()}   ·   max per die: ${Math.round(maxv).toLocaleString()}`;

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
    title: { text: c, font: { size: 14 } },
    xaxis: { scaleanchor: 'y', showgrid: false, zeroline: false },
    yaxis: { showgrid: false, zeroline: false },
    height: 720,
    margin: { l: 40, r: 40, t: 50, b: 40 },
    plot_bgcolor: '#fafafa',
    paper_bgcolor: '#fff'
  };
  Plotly.react('plot', [trace], layout, { displaylogo: false, responsive: true });
}

groupSel.addEventListener('change', refreshCols);
colSel.addEventListener('change', draw);
refreshCols();
</script>
</body></html>
"""

meta_str = (f"file: {Path(CSV_PATH).name} &middot; "
            f"rows: {len(df):,} &middot; "
            f"fail cols in HTML: {len(selected_cols)} / {len(fail_cols)} &middot; "
            f"groups: {len(group_options)}")

html_out = (html_template
            .replace("__META__", meta_str)
            .replace("__DATA__", json.dumps(fail_data, separators=(',', ':')))
            .replace("__XS__", json.dumps([int(v) for v in xs]))
            .replace("__YS__", json.dumps([int(v) for v in ys]))
            .replace("__GROUPS__", json.dumps(group_options))
            .replace("__VMAX__", f"{vmax:.3f}")
            .replace("__PSIZE__", str(max(4, POINT_SIZE // 2))))

Path(OUTPUT_HTML).write_text(html_out, encoding="utf-8")
size_mb = Path(OUTPUT_HTML).stat().st_size / 1024 / 1024
print(f"interactive HTML saved -> {OUTPUT_HTML}  ({size_mb:.1f} MB)")
print(f"   브라우저에서 열면 group/column 드롭다운으로 자유롭게 선택 가능")
if size_mb > 100:
    print(f"   * 용량이 커요. MAX_INTERACTIVE_COLS = 100 같이 제한하면 작아집니다.")
