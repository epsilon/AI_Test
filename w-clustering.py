"""
wafer_cluster_poc.py — wafer fail pattern clustering PoC

목적:
    (wafer × fail_type) 각각을 하나의 'tile' 로 보고, 공간 패턴 feature 를 뽑아
    비슷한 패턴끼리 클러스터링한다. 결과 = signature 카탈로그.

파이프라인:
    1. filter   : fail 거의 없는 tile 제외 (coverage / total threshold)
    2. feature  : radial + angular + moments + Moran's I + coarse grid  (~60 dim)
    3. normalize: tile 별 shape 정규화 + feature z-score
    4. embed    : UMAP 60D -> 2D  (없으면 PCA fallback)
    5. cluster  : HDBSCAN        (없으면 KMeans+silhouette fallback)
    6. catalog  : cluster centroid map + heuristic label + example tiles

설치:
    pip install pandas numpy scikit-learn matplotlib
    pip install umap-learn hdbscan      # 선택 (없으면 자동 fallback)

입력 CSV:
    - 1행 = 헤더, 2행 = 데이터 타입(string/int) -> skip
    - lotid, waferseq, ... , xdiepos, ydiepos, ... , fail_cnt_total, <fail types...>
    - fail_cnt_total 뒤의 모든 numeric 칼럼이 fail type

출력:
    - cluster_report.html  : 카탈로그 (UMAP scatter + 클러스터별 centroid map)
    - tile_clusters.csv    : (wafer, fail_type, cluster, label) join 테이블
"""

# ===================== CONFIG =====================
try: CSV_PATHS
except NameError:
    try: CSV_PATHS = [CSV_PATH]
    except NameError: CSV_PATHS = ["your_data.csv"]
if not isinstance(CSV_PATHS, (list, tuple)): CSV_PATHS = [CSV_PATHS]

try: CSV_GLOB                       # "wafers/*.csv" 처럼 주면 glob 으로 읽음
except NameError: CSV_GLOB = None

try: SKIP_TYPE_ROW
except NameError: SKIP_TYPE_ROW = True       # 2번째 줄(타입행) skip

try: WAFER_KEYS                              # 한 wafer(=tile 맥락)를 정의하는 칼럼
except NameError: WAFER_KEYS = ["lotid", "waferseq", "item", "temp"]

try: TOP_FAIL_TYPES                          # 총합 상위 N개 fail type 만 사용 (Pareto)
except NameError: TOP_FAIL_TYPES = 40

try: MIN_COVERAGE                            # fail die 비율 이 미만이면 clean -> 제외
except NameError: MIN_COVERAGE = 0.02

try: MIN_TOTAL                               # 총 fail 이 미만이면 제외
except NameError: MIN_TOTAL = 8

try: N_RADIAL
except NameError: N_RADIAL = 10
try: N_ANGULAR
except NameError: N_ANGULAR = 8
try: GRID
except NameError: GRID = 5                   # coarse grid GRID x GRID

try: OUTPUT_HTML
except NameError: OUTPUT_HTML = "cluster_report.html"
try: OUTPUT_CSV
except NameError: OUTPUT_CSV = "tile_clusters.csv"

try: RANDOM_STATE
except NameError: RANDOM_STATE = 42
# ==================================================


import re, json, base64, glob, math
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# optional deps
try:
    import umap
    HAS_UMAP = True
except Exception:
    HAS_UMAP = False
try:
    import hdbscan
    HAS_HDBSCAN = True
except Exception:
    HAS_HDBSCAN = False

print(f"umap: {'yes' if HAS_UMAP else 'NO (PCA fallback)'}   "
      f"hdbscan: {'yes' if HAS_HDBSCAN else 'NO (KMeans fallback)'}")


# ---------- load ----------
paths = sorted(glob.glob(CSV_GLOB)) if CSV_GLOB else list(CSV_PATHS)
print(f"reading {len(paths)} file(s)...")
dfs = []
for p in paths:
    p = Path(p)
    if not p.exists():
        print(f"  WARN not found: {p}"); continue
    d = pd.read_csv(p, skiprows=[1] if SKIP_TYPE_ROW else None, low_memory=False)
    d["__source__"] = p.name
    print(f"  {p.name}: {len(d):,} rows × {len(d.columns)} cols")
    dfs.append(d)
assert dfs, "no CSV read"
ref_cols = list(dfs[0].columns)
df = pd.concat(dfs, ignore_index=True, sort=False)
df = df[[c for c in ref_cols if c in df.columns] +
        [c for c in df.columns if c not in ref_cols]]
print(f"combined: {len(df):,} rows × {len(df.columns)} cols")

cmap = {c.lower(): c for c in df.columns}
x_col = cmap["xdiepos"]; y_col = cmap["ydiepos"]

# coerce coords
for c in (x_col, y_col):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=[x_col, y_col]).reset_index(drop=True)
df[x_col] = df[x_col].astype(int); df[y_col] = df[y_col].astype(int)

# fail cols = after fail_cnt_total
marker = None
for cand in ("fail_cnt_total", "failcnt_total", "fail_total"):
    if cand in cmap: marker = cmap[cand]; break
if marker is not None:
    b = list(df.columns).index(marker)
    cands = list(df.columns[b+1:])
else:
    cands = [c for c in df.columns if re.match(r"^fail", c, re.I)]
for c in cands:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df[cands] = df[cands].fillna(0)
fail_cols = [c for c in cands if pd.api.types.is_numeric_dtype(df[c])]
print(f"fail type columns: {len(fail_cols)}")
assert fail_cols, "no fail columns"

# wafer keys present?
wkeys = [cmap[k.lower()] for k in WAFER_KEYS if k.lower() in cmap]
if not wkeys:
    wkeys = ["__source__"]
print(f"wafer keys: {wkeys}")

# top fail types by global total
totals = df[fail_cols].sum().sort_values(ascending=False)
use_types = list(totals.head(TOP_FAIL_TYPES).index)
print(f"using top {len(use_types)} fail types by total")

# canonical positions (union)
canon = sorted(set(map(tuple, df[[x_col, y_col]].drop_duplicates().values.tolist())))
canon_idx = {xy: i for i, xy in enumerate(canon)}
NCAN = len(canon)
cxs = np.array([p[0] for p in canon], float)
cys = np.array([p[1] for p in canon], float)
gcx, gcy = cxs.mean(), cys.mean()
gR = np.sqrt((cxs-gcx)**2 + (cys-gcy)**2).max() or 1.0
print(f"canonical die positions: {NCAN}")


# ---------- featurization ----------
def morans_i(G):
    rows, cols = G.shape
    m = G.mean()
    gm = G - m
    denom = (gm**2).sum()
    if denom == 0: return 0.0
    num = 0.0; W = 0
    for i in range(rows):
        for j in range(cols):
            for di, dj in ((0,1),(1,0),(0,-1),(-1,0)):
                ni, nj = i+di, j+dj
                if 0 <= ni < rows and 0 <= nj < cols:
                    num += gm[i,j]*gm[ni,nj]; W += 1
    if W == 0: return 0.0
    return (G.size / W) * (num / denom)

def tile_features(xs, ys, v, cx, cy, R):
    v = np.asarray(v, float)
    total = v.sum()
    p = v / total                      # shape weights (sum=1)
    dx = xs - cx; dy = ys - cy
    r = np.clip(np.sqrt(dx*dx + dy*dy) / R, 0, 1)
    th = np.arctan2(dy, dx)

    feats = []
    # radial profile — ring 별 '밀도'(die 당 평균). 합계로 하면 바깥 ring 면적이 커서
    # uniform random 도 edge 처럼 보이는 편향이 생김
    rb = np.minimum((r * N_RADIAL).astype(int), N_RADIAL-1)
    rad = np.array([p[rb == b].sum() / max(1, int((rb == b).sum()))
                    for b in range(N_RADIAL)])
    feats += rad.tolist()
    # angular profile — sector 별 밀도
    ab = (((th + np.pi) / (2*np.pi)) * N_ANGULAR).astype(int) % N_ANGULAR
    ang = np.array([p[ab == b].sum() / max(1, int((ab == b).sum()))
                    for b in range(N_ANGULAR)])
    feats += ang.tolist()
    # moments
    xbar = (p*xs).sum(); ybar = (p*ys).sum()
    cen_off = math.hypot(xbar-cx, ybar-cy) / R
    mxx = (p*(xs-xbar)**2).sum(); myy = (p*(ys-ybar)**2).sum()
    mxy = (p*(xs-xbar)*(ys-ybar)).sum()
    C = np.array([[mxx, mxy],[mxy, myy]])
    w, vec = np.linalg.eigh(C)          # ascending
    l2, l1 = float(w[0]), float(w[1])
    spread = math.sqrt(max(l1+l2, 0)) / R
    aniso = (l1-l2)/(l1+l2) if (l1+l2) > 0 else 0.0
    major = vec[:, 1]
    ori = math.atan2(major[1], major[0])
    feats += [cen_off, spread, aniso, math.sin(2*ori), math.cos(2*ori)]
    # coarse grid (over wafer bbox)
    xmin, xmax = xs.min(), xs.max(); ymin, ymax = ys.min(), ys.max()
    xs_g = np.minimum(((xs-xmin)/max(xmax-xmin,1)*GRID).astype(int), GRID-1)
    ys_g = np.minimum(((ys-ymin)/max(ymax-ymin,1)*GRID).astype(int), GRID-1)
    G = np.zeros((GRID, GRID))
    for gi, gj, pv in zip(ys_g, xs_g, p):
        G[gi, gj] += pv
    feats += G.flatten().tolist()
    # Moran's I on coarse grid
    moran = morans_i(G)
    feats.append(moran)

    return np.array(feats, float), rad, aniso, moran, cen_off

# build tiles
print("extracting tiles...")
records = []         # metadata + scalars
F = []               # feature matrix
aligned_maps = []    # normalized tile values on canonical grid (for centroid viz)

for keys, sub in df.groupby(wkeys, dropna=False, sort=True):
    if not isinstance(keys, tuple): keys = (keys,)
    # aggregate duplicate die positions
    agg = sub.groupby([x_col, y_col])[use_types].sum()
    pos = np.array(agg.index.tolist())
    xs = pos[:, 0].astype(float); ys = pos[:, 1].astype(float)
    cx = xs.mean(); cy = ys.mean()
    R = np.sqrt((xs-cx)**2 + (ys-cy)**2).max() or 1.0
    pos_canon = [canon_idx[(int(a), int(b))] for a, b in pos]

    for ft in use_types:
        v = agg[ft].values.astype(float)
        total = v.sum()
        cov = (v > 0).mean()
        if total < MIN_TOTAL or cov < MIN_COVERAGE:
            continue
        feat, rad, aniso, moran, cen_off = tile_features(xs, ys, v, cx, cy, R)
        F.append(feat)
        amap = np.zeros(NCAN, np.float32)
        amap[pos_canon] = (v / total).astype(np.float32)
        aligned_maps.append(amap)
        rec = dict(zip(wkeys, [str(k) for k in keys]))
        rec.update(dict(fail_type=ft, n_fail=float(total), coverage=round(float(cov),3),
                        aniso=round(aniso,3), moran=round(moran,3), cen_off=round(cen_off,3),
                        radial=rad))
        records.append(rec)

F = np.array(F)
print(f"tiles after filter: {len(F)}  (feature dim {F.shape[1] if len(F) else 0})")
assert len(F) >= 10, "tile 이 너무 적음 — MIN_COVERAGE/MIN_TOTAL 낮춰보세요"


# ---------- helpers: labels + centroid render ----------
def label_cluster(radial_mean, aniso_mean, moran_mean, cen_mean):
    # anisotropy(선형성)가 가장 특이적인 신호 → 먼저. scratch 는 중심을 지나도 scratch.
    if aniso_mean > 0.55:
        return "linear / scratch"
    inner = radial_mean[:max(1, N_RADIAL//3)].mean()
    outer = radial_mean[-max(1, N_RADIAL//3):].mean()
    if outer > inner * 1.6:
        return "edge ring"
    if inner > outer * 1.6:
        return "center"
    if moran_mean < 0.15:
        return "random / scattered"
    if cen_mean > 0.25:
        return "off-center / asymmetric"
    return "diffuse / mixed"

def render_map(values, title, vmaxp=None):
    fig = plt.figure(figsize=(2.6, 2.6), dpi=78)
    ax = fig.add_axes([0,0,1,0.9])
    v = np.log1p(values)
    vmax = vmaxp if vmaxp else (v.max() or 1)
    ax.scatter(cxs, cys, c=v, s=max(3, int((180/np.sqrt(NCAN))**2)),
               marker="s", cmap="Reds", vmin=0, vmax=vmax, edgecolors="none")
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_xlim(cxs.min()-1, cxs.max()+1); ax.set_ylim(cys.min()-1, cys.max()+1)
    fig.text(0.5, 0.94, title, ha="center", va="top", fontsize=8, color="#333")
    buf = BytesIO(); fig.savefig(buf, format="png", facecolor="white", dpi=78)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

# ---------- global scaling + precomputed arrays ----------
try: MCS_DIVISOR
except NameError: MCS_DIVISOR = 80          # min_cluster_size = n // MCS_DIVISOR

try: MIN_TILES_PER_VIEW
except NameError: MIN_TILES_PER_VIEW = 30   # 이보다 tile 적은 LOT 은 per-lot 뷰 생략

try: MAX_LOT_VIEWS
except NameError: MAX_LOT_VIEWS = 12        # per-lot 뷰 최대 개수 (tile 많은 순)

Xs = StandardScaler().fit_transform(F)
aligned_maps = np.array(aligned_maps)
radial_all = np.array([r["radial"] for r in records])
aniso_all  = np.array([r["aniso"] for r in records])
moran_all  = np.array([r["moran"] for r in records])
cen_all    = np.array([r["cen_off"] for r in records])

palette = ["#E24B4A","#378ADD","#1D9E75","#EF9F27","#7F77DD","#D8568A",
           "#41B0C4","#9E6B1D","#6FB03A","#C44141","#5A6ACF","#B0843A"]

def run_view(name, idx):
    """idx: global tile indices to cluster together. returns view dict."""
    idx = np.asarray(idx)
    n = len(idx)
    sub = Xs[idx]
    # embed
    if HAS_UMAP and n >= 5:
        nn = min(15, max(2, n-1))
        emb = umap.UMAP(n_neighbors=nn, min_dist=0.1, n_components=2,
                        random_state=RANDOM_STATE).fit_transform(sub)
        em = "UMAP"
    else:
        k = min(2, sub.shape[1])
        emb = PCA(n_components=2, random_state=RANDOM_STATE).fit_transform(sub) \
              if n >= 3 else np.zeros((n, 2))
        em = "PCA"
    # cluster
    if HAS_HDBSCAN and n >= 10:
        mcs = max(5, n // MCS_DIVISOR)
        lab = hdbscan.HDBSCAN(min_cluster_size=mcs).fit_predict(emb)
        cm = f"HDBSCAN(mcs={mcs})"
    elif n >= 6:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        best = (-1, None, None)
        for k in range(2, min(9, n)):
            km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(emb)
            s = silhouette_score(emb, km.labels_)
            if s > best[0]: best = (s, k, km.labels_)
        lab = best[2]; cm = f"KMeans(k={best[1]})"
    else:
        lab = np.zeros(n, int); cm = "single"

    # scatter png
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    for k, c in enumerate(sorted(set(lab))):
        m = lab == c
        col = "#bbbbbb" if c == -1 else palette[k % len(palette)]
        ax.scatter(emb[m,0], emb[m,1], s=14, c=col, edgecolors="none", alpha=0.8,
                   label=("noise" if c==-1 else f"c{c}"))
    ax.set_title(f"{name} · {em} · {cm} · {n} tiles", fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(fontsize=8, markerscale=1.3, loc="best", framealpha=0.9)
    fig.tight_layout()
    buf = BytesIO(); fig.savefig(buf, format="png", dpi=104, facecolor="white")
    plt.close(fig)
    scatter_png = base64.b64encode(buf.getvalue()).decode()

    # clusters
    clusters = []
    members = {}
    for c in sorted(set(lab)):
        local = np.where(lab == c)[0]
        gidx = idx[local]
        centroid = aligned_maps[gidx].mean(axis=0)
        rad_m = radial_all[gidx].mean(axis=0)
        lname = "noise" if c == -1 else label_cluster(
            rad_m, aniso_all[gidx].mean(), moran_all[gidx].mean(), cen_all[gidx].mean())
        clusters.append(dict(
            cid=int(c), label=lname, n=int(len(gidx)),
            aniso=round(float(aniso_all[gidx].mean()),3),
            moran=round(float(moran_all[gidx].mean()),3),
            centroid_png=render_map(centroid, f"{name} · c{c} · {lname} · n={len(gidx)}"),
        ))
        members[int(c)] = [int(g) for g in gidx]
    clusters.sort(key=lambda d: (d["cid"]==-1, -d["n"]))
    return dict(name=name, n=n, embed=em, cluster=cm,
                scatter_png=scatter_png, clusters=clusters, members=members, labels=lab)

# ALL view
print("clustering: ALL")
views = []
all_view = run_view("ALL", np.arange(len(F)))
views.append(all_view)

# assign GLOBAL cluster label back to records (for CSV)
glab = all_view["labels"]
gid2name = {cc["cid"]: cc["label"] for cc in all_view["clusters"]}
for i, r in enumerate(records):
    r["cluster"] = int(glab[i]); r["label"] = gid2name[int(glab[i])]

# per-LOTID views
lot_key = cmap.get("lotid")
if lot_key and lot_key in records[0]:
    from collections import defaultdict
    lot_idx = defaultdict(list)
    for i, r in enumerate(records):
        lot_idx[r[lot_key]].append(i)
    # tile 많은 LOT 우선, 최소 tile 이상만
    lots = sorted([(lot, ix) for lot, ix in lot_idx.items() if len(ix) >= MIN_TILES_PER_VIEW],
                  key=lambda kv: -len(kv[1]))[:MAX_LOT_VIEWS]
    for lot, ix in lots:
        print(f"clustering: LOT {lot}  ({len(ix)} tiles)")
        views.append(run_view(f"LOT {lot}", ix))
else:
    print("lotid 칼럼 없음 — per-lot 뷰 생략")

# 호환용 변수 (이후 코드)
embed_method = all_view["embed"]; cluster_method = all_view["cluster"]
clusters = all_view["clusters"]

# ---------- sparse tile data for interactive member maps ----------
POS = [[int(cxs[i]), int(cys[i])] for i in range(NCAN)]
tiles_js = []
for i, r in enumerate(records):
    amap = aligned_maps[i]
    total = r["n_fail"]
    nz = np.nonzero(amap)[0]
    pairs = [[int(k), int(round(float(amap[k]) * total))] for k in nz]
    pairs = [pq for pq in pairs if pq[1] > 0]
    wid = " · ".join(str(r[k]) for k in wkeys)
    tiles_js.append({"w": wid, "ft": r["fail_type"], "n": int(total), "nz": pairs})


# ---------- CSV ----------
out_rows = []
for r in records:
    row = {k: r[k] for k in wkeys}
    row.update({"fail_type": r["fail_type"], "n_fail": int(r["n_fail"]),
                "coverage": r["coverage"], "moran": r["moran"], "aniso": r["aniso"],
                "cluster": r["cluster"], "label": r["label"]})
    out_rows.append(row)
pd.DataFrame(out_rows).to_csv(OUTPUT_CSV, index=False)
print(f"CSV saved -> {OUTPUT_CSV}  ({len(out_rows)} tiles)")


# ---------- HTML ----------
def img(b): return f"<img src='data:image/png;base64,{b}'>"

view_members = {}
view_blocks = []
for vi, vw in enumerate(views):
    view_members[vw["name"]] = vw["members"]
    blocks = []
    for cc in vw["clusters"]:
        vk = f"{vi}_{cc['cid']}"
        blocks.append(f"""<div class="cl">
          <div class="cen">{img(cc['centroid_png'])}</div>
          <div class="body">
            <h3>cluster {cc['cid']} &mdash; {cc['label']}</h3>
            <div class="st">members: {cc['n']} &middot; Moran's I: {cc['moran']} &middot; anisotropy: {cc['aniso']}</div>
            <button class="showbtn" data-vk="{vk}" data-view="{vw['name']}" data-c="{cc['cid']}">&#9654; \uba64\ubc84 wafer map \ubcf4\uae30 ({cc['n']})</button>
            <div class="members" id="mem-{vk}"></div>
          </div>
        </div>""")
    ncl = len([c for c in vw["clusters"] if c["cid"] != -1])
    view_blocks.append(f"""<div class="view" data-view="{vw['name']}" style="{'display:none' if vi else ''}">
      <div class="vmeta">{vw['name']} &middot; {vw['n']} tiles &middot; {vw['embed']} &middot; {vw['cluster']} &middot; {ncl} clusters (+noise)</div>
      <div class="scatter">{img(vw['scatter_png'])}</div>
      {''.join(blocks)}
    </div>""")

options = "".join(
    f"<option value='{vw['name']}'>"
    f"{'\uc804\uccb4 (ALL)' if vw['name']=='ALL' else vw['name']} &mdash; {vw['n']} tiles</option>"
    for vw in views)

js_payload = {"POS": POS, "TILES": tiles_js, "VIEWMEM": view_members}

H = [f"""<!doctype html><html><head><meta charset="utf-8"><title>Wafer Cluster Report</title>
<style>
body{{font-family:system-ui,sans-serif;background:#ffffff;color:#1a1f29;margin:0;padding:24px;max-width:1300px;margin:auto}}
h1{{color:#b3460f;font-size:20px;border-bottom:1px solid #e2e5ea;padding-bottom:10px}}
.meta{{color:#5c6470;font-size:12px;font-family:ui-monospace,monospace;line-height:1.7;margin-top:8px}}
.viewbar{{margin:20px 0 10px;display:flex;align-items:center;gap:10px}}
.viewbar label{{font-size:12px;color:#b3460f;text-transform:uppercase;letter-spacing:.05em}}
#viewSel{{background:#fff;border:1px solid #d0d4da;color:#1a1f29;padding:8px 12px;border-radius:5px;font-size:13px;font-family:ui-monospace,monospace;min-width:280px}}
#viewSel:hover{{border-color:#b3460f}}
.vmeta{{color:#5c6470;font-size:12px;font-family:ui-monospace,monospace;margin:6px 0}}
img{{background:#fff;border-radius:4px}}
.scatter img{{max-width:100%;margin:8px 0}}
.cl{{display:flex;gap:16px;align-items:flex-start;background:#f6f7f9;border:1px solid #e2e5ea;border-radius:8px;padding:14px;margin:10px 0}}
.cl .cen{{flex-shrink:0}}
.cl .body{{flex:1;min-width:0}}
.cl h3{{margin:0 0 4px;font-size:14px;color:#b3460f}}
.cl .st{{color:#5c6470;font-size:11px;font-family:ui-monospace,monospace;margin-bottom:8px}}
.showbtn{{background:#fff;border:1px solid #d0d4da;color:#b3460f;border-radius:5px;padding:6px 12px;font-size:12px;cursor:pointer;font-family:ui-monospace,monospace}}
.showbtn:hover{{border-color:#b3460f;background:#fff6f0}}
.members{{display:none;margin-top:12px;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}}
.members.open{{display:grid}}
.tile{{text-align:center;cursor:pointer}}
.tile canvas{{width:108px;height:108px;border:1px solid #e2e5ea;border-radius:4px;background:#fff;image-rendering:pixelated}}
.tile:hover canvas{{border-color:#b3460f}}
.tile .cap{{font-size:9px;color:#5c6470;font-family:ui-monospace,monospace;margin-top:3px;line-height:1.3;word-break:break-word}}
.more{{grid-column:1/-1;color:#5c6470;font-size:11px;font-family:ui-monospace,monospace;padding:6px;text-align:center}}
#modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:100;align-items:center;justify-content:center}}
#modal.open{{display:flex}}
#modalBox{{background:#fff;border-radius:8px;padding:18px;text-align:center;max-width:90vw}}
#modalBox canvas{{width:440px;height:440px;max-width:80vw;image-rendering:pixelated;border:1px solid #e2e5ea;border-radius:4px}}
#modalBox .mc{{font-size:12px;color:#1a1f29;font-family:ui-monospace,monospace;margin-top:10px}}
#modalBox .close{{float:right;cursor:pointer;color:#5c6470;font-size:18px;line-height:1}}
</style></head><body>
<h1>WAFER FAIL PATTERN &mdash; CLUSTER CATALOG</h1>
<div class="meta">
files: {len(paths)} &middot; tiles: {len(F)} &middot; feature dim: {F.shape[1]} &middot; fail types: {len(use_types)} &middot; views: {len(views)} (ALL + per-LOT)<br>
filter: coverage &ge; {MIN_COVERAGE}, total &ge; {MIN_TOTAL} &middot; wafer keys: {wkeys} &middot; mcs = n//{MCS_DIVISOR}
</div>
<div class="viewbar"><label>view</label><select id="viewSel">{options}</select></div>
{''.join(view_blocks)}
<div id="modal"><div id="modalBox">
  <span class="close" onclick="document.getElementById('modal').classList.remove('open')">&times;</span>
  <div style="clear:both"></div><canvas id="modalCv" width="440" height="440"></canvas>
  <div class="mc" id="modalCap"></div>
</div></div>
<script>
const D = {json.dumps(js_payload, separators=(',',':'))};
const POS = D.POS, TILES = D.TILES, VIEWMEM = D.VIEWMEM;
const MAX_SHOW = 120;
let XMIN=1e9,XMAX=-1e9,YMIN=1e9,YMAX=-1e9;
for(const [x,y] of POS){{ if(x<XMIN)XMIN=x; if(x>XMAX)XMAX=x; if(y<YMIN)YMIN=y; if(y>YMAX)YMAX=y; }}
const XSPAN=XMAX-XMIN+1, YSPAN=YMAX-YMIN+1;
function heat(t){{
  t=Math.max(0,Math.min(1,t));
  const s=[[255,255,255],[247,206,170],[221,110,80],[150,30,28],[90,12,12]];
  const seg=t*(s.length-1),i=Math.floor(seg),f=seg-i;
  const a=s[i],b=s[Math.min(i+1,s.length-1)];
  return `rgb(${{Math.round(a[0]+(b[0]-a[0])*f)}},${{Math.round(a[1]+(b[1]-a[1])*f)}},${{Math.round(a[2]+(b[2]-a[2])*f)}})`;
}}
function drawTile(cv, tile){{
  const ctx=cv.getContext('2d'), W=cv.width, H=cv.height;
  ctx.fillStyle='#eef0f2'; ctx.fillRect(0,0,W,H);
  const cell=Math.min(W/XSPAN, H/YSPAN);
  let mx=0; for(const [idx,c] of tile.nz){{const l=Math.log1p(c); if(l>mx)mx=l;}} mx=mx||1;
  ctx.fillStyle='#ffffff';
  for(const [x,y] of POS) ctx.fillRect((x-XMIN)*cell,(YMAX-y)*cell,Math.ceil(cell),Math.ceil(cell));
  for(const [idx,c] of tile.nz){{
    const p=POS[idx]; ctx.fillStyle=heat(Math.log1p(c)/mx);
    ctx.fillRect((p[0]-XMIN)*cell,(YMAX-p[1])*cell,Math.ceil(cell),Math.ceil(cell));
  }}
}}
const rendered = {{}};
document.querySelectorAll('.showbtn').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    const vk=btn.dataset.vk, view=btn.dataset.view, c=parseInt(btn.dataset.c);
    const box=document.getElementById('mem-'+vk);
    const open=box.classList.toggle('open');
    const idxs=(VIEWMEM[view] && VIEWMEM[view][c]) ? VIEWMEM[view][c] : [];
    btn.innerHTML=(open?'&#9660;':'&#9654;')+' \uba64\ubc84 wafer map \ubcf4\uae30 ('+idxs.length+')';
    if(open && !rendered[vk]){{
      rendered[vk]=true;
      const show=idxs.slice(0,MAX_SHOW);
      const frag=document.createDocumentFragment();
      show.forEach(ti=>{{
        const t=TILES[ti];
        const d=document.createElement('div'); d.className='tile';
        const cv=document.createElement('canvas'); cv.width=108; cv.height=108;
        const cap=document.createElement('div'); cap.className='cap';
        cap.textContent=t.ft+'  ['+t.w+']';
        d.appendChild(cv); d.appendChild(cap);
        d.addEventListener('click',()=>{{
          drawTile(document.getElementById('modalCv'), t);
          document.getElementById('modalCap').textContent=t.ft+'  \u00b7  '+t.w+'  \u00b7  total '+t.n;
          document.getElementById('modal').classList.add('open');
        }});
        frag.appendChild(d); drawTile(cv, t);
      }});
      if(idxs.length>MAX_SHOW){{
        const m=document.createElement('div'); m.className='more';
        m.textContent='... '+show.length+' / '+idxs.length+' \ud45c\uc2dc (\ub098\uba38\uc9c0\ub294 CSV \ucc38\uace0)';
        frag.appendChild(m);
      }}
      box.appendChild(frag);
    }}
  }});
}});
document.getElementById('viewSel').addEventListener('change',e=>{{
  const v=e.target.value;
  document.querySelectorAll('.view').forEach(d=>{{ d.style.display=(d.dataset.view===v)?'':'none'; }});
}});
document.getElementById('modal').addEventListener('click',e=>{{
  if(e.target.id==='modal') e.currentTarget.classList.remove('open');
}});
</script>
</body></html>"""]
Path(OUTPUT_HTML).write_text("".join(H), encoding="utf-8")
size = Path(OUTPUT_HTML).stat().st_size/1024
print(f"HTML saved -> {OUTPUT_HTML}  ({size:.0f} KB)")
print("\nDONE.")
