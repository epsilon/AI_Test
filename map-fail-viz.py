"""
map_fail_viz.py  —  die fail map visualizer (Jupyter-friendly)

사용법:
    1. 아래 CONFIG 섹션에서 CSV_PATH 등을 본인 환경에 맞게 수정
    2. Jupyter 셀에 통째로 붙여넣고 실행  (또는 `python map_fail_viz.py`)

입력 CSV:
    - xdiepos, ydiepos                (die 좌표; 대소문자 무관)
    - fail_* 숫자 칼럼 다수            (die-internal 위치별 fail 카운트)
    - optional: LOTID, waferseq       (여러 wafer 합산/필터용)

출력:
    1. Overview wafer map (전체 fail 합)
    2. Pareto bar chart (칼럼별 총 fail)
    3. Per-group small multiples (prefix 그룹별 격자)
"""

# === CONFIG — 여기만 편집 ===
CSV_PATH       = "your_data.csv"   # 본인 CSV 경로
WAFER_FILTER   = None              # 한 장만: "LOTID:waferseq",  전체 합산: None
TOP_PER_GROUP  = 48                # 그룹당 최대 몇 개까지 그릴지
FAIL_PATTERN   = r"^fail"          # fail 칼럼 정규식 (case-insensitive)
POINT_SIZE     = 18                # 산점도 마커 크기. 작으면 6, 크면 40

# === 코드 (아래는 건드릴 필요 없음) ===
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def parse_group(col):
    """
    fail_cnt_bank0   -> ('bank', 0)
    fail_cn_bank12   -> ('bank', 12)
    fail_mat_5       -> ('mat', 5)
    fail_fmat_row_3  -> ('fmat_row', 3)
    fail_total       -> ('total', None)
    """
    s = col.lower()
    s = re.sub(r"^fail_?(cn|cnt)?_?", "", s)
    m = re.match(r"^([a-z][a-z_]*?)_?(\d+)$", s)
    if m:
        g = m.group(1).strip("_") or "misc"
        return g, int(m.group(2))
    return (s or "misc"), None


def wafer_map(ax, xs, ys, values, title, vmax_log=None, point_size=None):
    """die 산점도. log1p 컬러 스케일, 0은 floor."""
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
df = pd.read_csv(CSV_PATH, low_memory=False)
print(f"rows: {len(df):,}   cols: {len(df.columns)}")

cmap = {c.lower(): c for c in df.columns}
x_col = cmap["xdiepos"]
y_col = cmap["ydiepos"]
lot_col  = cmap.get("lotid")
wseq_col = cmap.get("waferseq")

pat = re.compile(FAIL_PATTERN, re.IGNORECASE)
fail_cols = [c for c in df.columns
             if pat.search(c) and pd.api.types.is_numeric_dtype(df[c])]
print(f"fail columns: {len(fail_cols)}")
assert fail_cols, "no fail columns matched. FAIL_PATTERN 을 바꿔보세요."

# wafer filter / aggregate
if WAFER_FILTER and lot_col and wseq_col:
    lot, wseq = WAFER_FILTER.split(":", 1)
    df = df[(df[lot_col].astype(str) == lot) &
            (df[wseq_col].astype(str) == wseq)].copy()
    print(f"filtered to {WAFER_FILTER}: {len(df):,} rows")
elif lot_col and wseq_col:
    nw = df.groupby([lot_col, wseq_col]).ngroups
    if nw > 1:
        print(f"{nw} wafers in file -> aggregating (sum) by die position")
        df = df.groupby([x_col, y_col], as_index=False)[fail_cols].sum()

# group fail cols
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
total = df[fail_cols].sum(axis=1).values
fig, ax = plt.subplots(figsize=(6.5, 6.5))
sc = wafer_map(ax, xs, ys, total, f"TOTAL FAIL  (sum of {len(fail_cols)} cols)")
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

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols*2.2, nrows*2.4))
    axes = np.atleast_2d(axes).reshape(nrows, ncols)
    last_sc = None
    for i, c in enumerate(plotted):
        r, cc = divmod(i, ncols)
        last_sc = wafer_map(axes[r, cc], xs, ys, df[c].values, c, vmax_log=gvmax)
    for j in range(n, nrows*ncols):
        r, cc = divmod(j, ncols)
        axes[r, cc].axis("off")
    if last_sc is not None:
        fig.colorbar(last_sc, ax=axes.ravel().tolist(),
                     shrink=0.6, label="log1p(fail)")
    suffix = f"  (showing {n} of {n_all})" if n < n_all else ""
    fig.suptitle(f"group: {g}{suffix}", fontsize=10, y=0.995)
    plt.show()
