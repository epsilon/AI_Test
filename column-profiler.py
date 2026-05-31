"""
column_profiler.py  (v2) — fail 칼럼 진단 + 클러스터링 칼럼 자동 선별

핵심 추가: between-wafer 변별력(discrimination).
  total 이 커도 모든 wafer 에 비슷하게 나오면 wafer 구분에 쓸모없다.
  wafer 마다 '다르게' 나오는 칼럼이 진짜 신호.

출력:
  - column_profile.csv     : 전체 칼럼 진단표 (파일로 저장, 칠 필요 없음)
  - selected_columns.txt   : 클러스터링 추천 칼럼 (wafer_cluster_poc 가 자동으로 읽음)
  - 콘솔에는 요약 몇 줄만
"""

# === CONFIG ===
try: CSV_PATHS
except NameError:
    try: CSV_PATHS = [CSV_PATH]
    except NameError: CSV_PATHS = ["your_data.csv"]
if not isinstance(CSV_PATHS,(list,tuple)): CSV_PATHS=[CSV_PATHS]
try: CSV_GLOB
except NameError: CSV_GLOB=None
try: SKIP_TYPE_ROW
except NameError: SKIP_TYPE_ROW=True
try: WAFER_KEYS
except NameError: WAFER_KEYS=["lotid","waferseq","item","temp"]
try: OUTPUT_CSV
except NameError: OUTPUT_CSV="column_profile.csv"
try: SELECTED_TXT
except NameError: SELECTED_TXT="selected_columns.txt"

# 선별 기준
try: MIN_FILL
except NameError: MIN_FILL = 0.02       # die 채움 최소
try: MIN_MORAN
except NameError: MIN_MORAN = 0.15      # 공간 패턴 최소
try: MIN_DISCRIM
except NameError: MIN_DISCRIM = 0.6     # between-wafer 변별력 최소 (CV)
try: MAX_UBIQUITY
except NameError: MAX_UBIQUITY = 0.97   # 이 비율 이상의 wafer 에 나오면 '배경'으로 보고 제외
try: N_SELECT
except NameError: N_SELECT = 80         # 최대 추천 칼럼 수

import re, glob
import numpy as np, pandas as pd

paths = sorted(glob.glob(CSV_GLOB)) if CSV_GLOB else list(CSV_PATHS)
print(f"reading {len(paths)} file(s)...")
dfs=[]
for p in paths:
    d=pd.read_csv(p, skiprows=[1] if SKIP_TYPE_ROW else None, low_memory=False)
    dfs.append(d)
df=pd.concat(dfs,ignore_index=True,sort=False)
print(f"rows: {len(df):,}  cols: {len(df.columns)}")

cmap={c.lower():c for c in df.columns}
x_col,y_col=cmap["xdiepos"],cmap["ydiepos"]
df[x_col]=pd.to_numeric(df[x_col],errors="coerce")
df[y_col]=pd.to_numeric(df[y_col],errors="coerce")
df=df.dropna(subset=[x_col,y_col]).reset_index(drop=True)
df[x_col]=df[x_col].astype(int); df[y_col]=df[y_col].astype(int)

marker=None
for cand in ("fail_cnt_total","failcnt_total","fail_total"):
    if cand in cmap: marker=cmap[cand]; break
if marker is not None:
    b=list(df.columns).index(marker); fail_cols=list(df.columns[b+1:])
else:
    fail_cols=[c for c in df.columns if re.match(r"^fail",c,re.I)]

def name_class(c):
    cl=c.lower()
    if cl.startswith("i_"): return "i_"
    if cl.startswith("g_"): return "g_"
    if cl.startswith("mfm"): return "mfm_"
    if "total" in cl: return "total"
    return "spatial"

def fail_axis(c):
    cl=c.lower()
    # i_single_bank / halfbank 도 bank 로
    if "bank" in cl or "halfbank" in cl or "bnk" in cl or "bkg" in cl or cl=="chip":
        if "row" in cl: return "row(WL)"
        if "col" in cl: return "col(BL)"
        return "bank/chip"
    if cl.startswith(("srow","frow","row")) or cl.startswith(("i_row","i_srow")): return "row(WL)"
    if cl.startswith(("scol","fcol","col")) or cl.startswith(("i_col","i_scol")): return "col(BL)"
    if cl.startswith(("fmat","block")): return "mat/block"
    if cl.startswith(("bx2","by2","biso","snbrg","iso","i_iso","s_iso","s_snc","s_nfc","ee_","oe_","oo_","eo_","snc","sn_","triple","single","dual")): return "bridge/iso"
    if cl.startswith(("g_","mfm","nfc")): return "geometry/etc"
    if cl.startswith(("i_bit","i_group","group")): return "bit/group"
    return "other"

# 좌표 그리드(공간성)
pos=df[[x_col,y_col]].drop_duplicates().sort_values([y_col,x_col]).reset_index(drop=True)
xs=pos[x_col].values; ys=pos[y_col].values; xmin,ymin=xs.min(),ys.min()
xspan=xs.max()-xmin+1; yspan=ys.max()-ymin+1
GRID=8
def morans_of(agg):
    G=np.zeros((GRID,GRID))
    for (x,y),v in agg.items():
        gi=min(int((y-ymin)/yspan*GRID),GRID-1); gj=min(int((x-xmin)/xspan*GRID),GRID-1)
        G[gi,gj]+=v
    g=G.flatten(); m=g.mean(); gm=G-m; den=(gm**2).sum()
    if den==0: return 0.0
    num=0;W=0
    for i in range(GRID):
        for j in range(GRID):
            for di,dj in((0,1),(1,0),(0,-1),(-1,0)):
                ni,nj=i+di,j+dj
                if 0<=ni<GRID and 0<=nj<GRID: num+=gm[i,j]*gm[ni,nj];W+=1
    return (G.size/W)*(num/den) if (W and den) else 0.0

wkeys=[cmap[k.lower()] for k in WAFER_KEYS if k.lower() in cmap] or None
if wkeys is None:
    df["__w__"]="all"; wkeys=["__w__"]
n_wafers=df.groupby(wkeys).ngroups
wafer_id=df.groupby(wkeys).ngroup().values   # 각 row 의 wafer index

print(f"wafers: {n_wafers}, fail columns: {len(fail_cols)}  — profiling...")

rows=[]
for c in fail_cols:
    v=pd.to_numeric(df[c],errors="coerce").fillna(0).values.astype(float)
    fill=(v>0).mean()
    # wafer 별 합
    ws=np.bincount(wafer_id, weights=v, minlength=n_wafers)
    wafer_hit=(ws>0).mean()
    # between-wafer 변별력 = CV (std/mean) of wafer sums
    mean_w=ws.mean()
    discrim = (ws.std()/mean_w) if mean_w>0 else 0.0
    # 공간성 (fill 있을 때만)
    sp=0.0
    if fill>0.005:
        agg={}
        # 좌표별 합 (빠르게)
        tmpx=df[x_col].values; tmpy=df[y_col].values
        # 합산
        key=tmpx.astype(np.int64)*100000+tmpy.astype(np.int64)
        order=np.argsort(key)
        ks=key[order]; vs=v[order]
        uniq_k, idx_start=np.unique(ks, return_index=True)
        sums=np.add.reduceat(vs, idx_start)
        for kk,ss in zip(uniq_k,sums):
            agg[(int(kk//100000), int(kk%100000))]=ss
        sp=round(morans_of(agg),3)
    rows.append(dict(column=c, name_class=name_class(c), fail_axis=fail_axis(c),
                     fill_rate=round(float(fill),4), wafer_hit=round(float(wafer_hit),3),
                     discrim=round(float(discrim),3), spatial_moran=sp,
                     total=int(v.sum()), max_die=int(v.max())))

prof=pd.DataFrame(rows)
prof.to_csv(OUTPUT_CSV,index=False)

# 선별: 공간성 있고 + wafer 변별력 있고 + 배경(거의 모든 wafer) 아닌 것
sel = prof[(prof["fill_rate"]>=MIN_FILL) &
           (prof["spatial_moran"]>=MIN_MORAN) &
           (prof["discrim"]>=MIN_DISCRIM) &
           (prof["wafer_hit"]<=MAX_UBIQUITY)].copy()
sel = sel.sort_values("discrim", ascending=False).head(N_SELECT)
sel["column"].to_csv(SELECTED_TXT, index=False, header=False)

# ===== 콘솔 요약 (짧게) =====
print(f"\nsaved: {OUTPUT_CSV} (전체 {len(prof)}), {SELECTED_TXT} (선별 {len(sel)})")
print(f"\n[선별 칼럼 axis 분포]")
for ax,n in sel["fail_axis"].value_counts().items():
    print(f"  {ax}: {n}")
print(f"\n[선별 상위 20 — wafer 변별력 순]")
for _,r in sel.head(20).iterrows():
    print(f"  {r['column'][:28]:28s} {r['fail_axis'][:10]:10s} "
          f"discrim={r['discrim']:.2f} fill={r['fill_rate']:.2f} moran={r['spatial_moran']:.2f}")
print(f"\n[참고] 제외된 '배경' 칼럼 예시 (total 큰데 변별력 낮은 것):")
bg=prof[(prof["fill_rate"]>0.3)&(prof["discrim"]<MIN_DISCRIM)].sort_values("total",ascending=False)
for _,r in bg.head(8).iterrows():
    print(f"  {r['column'][:28]:28s} total={r['total']:>14,} discrim={r['discrim']:.2f}  <- 거의 모든 wafer 에 비슷")
