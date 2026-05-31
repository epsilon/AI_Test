"""
column_profiler.py — fail 칼럼 진단

클러스터링 전에 각 fail 칼럼이 실제로 어떻게 생겼는지 파악한다.
- fill_rate : 값이 0이 아닌 die 비율 (희소도)
- nonzero_wafers : 그 칼럼에 fail 이 하나라도 있는 wafer 비율
- spatial_score : die 별 분포가 공간적 패턴을 갖는지 (Moran's I 근사)
출력: column_profile.csv  +  콘솔 요약

목적: 어떤 칼럼이 (A) 공간 맵 / (B) 희소 플래그 / (C) 거의 안 쓰임 인지 자동 분류
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

import re, glob
import numpy as np, pandas as pd

paths = sorted(glob.glob(CSV_GLOB)) if CSV_GLOB else list(CSV_PATHS)
print(f"reading {len(paths)} file(s)...")
dfs=[]
for p in paths:
    d=pd.read_csv(p, skiprows=[1] if SKIP_TYPE_ROW else None, low_memory=False)
    d["__source__"]=p
    dfs.append(d)
df=pd.concat(dfs,ignore_index=True,sort=False)
print(f"rows: {len(df):,}  cols: {len(df.columns)}")

cmap={c.lower():c for c in df.columns}
x_col,y_col=cmap["xdiepos"],cmap["ydiepos"]
df[x_col]=pd.to_numeric(df[x_col],errors="coerce")
df[y_col]=pd.to_numeric(df[y_col],errors="coerce")
df=df.dropna(subset=[x_col,y_col])
df[x_col]=df[x_col].astype(int); df[y_col]=df[y_col].astype(int)

# fail 칼럼 = fail_cnt_total 뒤
marker=None
for cand in ("fail_cnt_total","failcnt_total","fail_total"):
    if cand in cmap: marker=cmap[cand]; break
if marker is not None:
    b=list(df.columns).index(marker); fail_cols=list(df.columns[b+1:])
else:
    fail_cols=[c for c in df.columns if re.match(r"^fail",c,re.I)]
fail_cols=[c for c in fail_cols if c!="__source__"]
print(f"fail columns: {len(fail_cols)}")

# 칼럼명 기반 1차 분류
def name_class(c):
    cl=c.lower()
    if cl.startswith("i_"): return "i_ (집계 추정)"
    if cl.startswith("g_"): return "g_ (geometry)"
    if cl.startswith("mfm"): return "mfm_ (특수)"
    if "total" in cl: return "denominator(total)"
    return "spatial(추정)"

# fail mode 축 1차 분류
def fail_axis(c):
    cl=c.lower()
    for k in ["srow","frow","row"]:
        if cl.startswith(k) or cl.startswith("i_row") or cl.startswith("i_srow"): return "row(WL)"
    for k in ["scol","fcol","col"]:
        if cl.startswith(k) or cl.startswith("i_col") or cl.startswith("i_scol"): return "col(BL)"
    if cl.startswith("fmat") or cl.startswith("block"): return "mat/block"
    if cl.startswith("bank") or "bnk" in cl or "bkg" in cl or cl=="chip": return "bank/chip"
    if any(cl.startswith(k) for k in ["bx2","by2","biso","snbrg","iso","i_iso","s_iso","s_snc","s_nfc"]): return "bridge/iso"
    if cl.startswith("g_") or cl.startswith("mfm") or cl.startswith("nfc"): return "geometry/etc"
    if cl.startswith("i_bit") or cl.startswith("i_group"): return "bit/group"
    return "other"

# 좌표 그리드(공간성 측정용)
pos = df[[x_col,y_col]].drop_duplicates().sort_values([y_col,x_col]).reset_index(drop=True)
xs=pos[x_col].values; ys=pos[y_col].values
xmin,ymin=xs.min(),ys.min()
GRID=8
def coarse(vals_by_pos):
    G=np.zeros((GRID,GRID)); cnt=np.zeros((GRID,GRID))
    xspan=xs.max()-xmin+1; yspan=ys.max()-ymin+1
    for (x,y),v in vals_by_pos.items():
        gi=min(int((y-ymin)/yspan*GRID),GRID-1); gj=min(int((x-xmin)/xspan*GRID),GRID-1)
        G[gi,gj]+=v
    return G
def morans(G):
    g=G.flatten(); m=g.mean(); gm=G-m; den=(gm**2).sum()
    if den==0: return 0.0
    num=0;W=0
    for i in range(GRID):
        for j in range(GRID):
            for di,dj in((0,1),(1,0),(0,-1),(-1,0)):
                ni,nj=i+di,j+dj
                if 0<=ni<GRID and 0<=nj<GRID: num+=gm[i,j]*gm[ni,nj];W+=1
    return (G.size/W)*(num/den) if (W and den) else 0.0

wkeys=[cmap[k.lower()] for k in WAFER_KEYS if k.lower() in cmap] or ["__source__"]
n_wafers=df.groupby(wkeys).ngroups
N=len(df)

rows=[]
for c in fail_cols:
    v=pd.to_numeric(df[c],errors="coerce").fillna(0).values
    nz=(v>0)
    fill=nz.mean()
    # wafer 단위로 값이 있는 비율
    tmp=df[wkeys].copy(); tmp["_v"]=v
    wnz=tmp.groupby(wkeys)["_v"].max()
    wafer_hit=(wnz>0).mean()
    # 공간성: 전체 die 합쳐서 좌표별 평균 → Moran's I (대표값)
    sp=np.nan
    if fill>0.005:
        agg=tmp.groupby([df[x_col],df[y_col]])["_v"].sum().to_dict()
        sp=round(morans(coarse(agg)),3)
    rows.append(dict(column=c, name_class=name_class(c), fail_axis=fail_axis(c),
                     fill_rate=round(float(fill),4), wafer_hit=round(float(wafer_hit),3),
                     total=int(v.sum()), max_die=int(v.max()), spatial_moran=sp))

prof=pd.DataFrame(rows).sort_values("total",ascending=False)
prof.to_csv(OUTPUT_CSV,index=False)
print(f"\nsaved -> {OUTPUT_CSV}  ({len(prof)} columns)\n")

print("=== name_class 별 칼럼 수 ===")
print(prof["name_class"].value_counts(), "\n")
print("=== fail_axis 별 칼럼 수 ===")
print(prof["fail_axis"].value_counts(), "\n")
print("=== fill_rate 분포 (die 중 0 아닌 비율) ===")
print("  거의 빈 칼럼 (fill<0.5%):", (prof["fill_rate"]<0.005).sum())
print("  희소 (0.5~5%)         :", ((prof["fill_rate"]>=0.005)&(prof["fill_rate"]<0.05)).sum())
print("  중간 (5~30%)          :", ((prof["fill_rate"]>=0.05)&(prof["fill_rate"]<0.30)).sum())
print("  조밀 (>30%)           :", (prof["fill_rate"]>=0.30).sum())
print()
print("=== 클러스터링에 쓸만한 칼럼 (fill>2% & spatial_moran>0.2) ===")
good=prof[(prof["fill_rate"]>0.02)&(prof["spatial_moran"]>0.2)]
print(f"  {len(good)} 개")
print(good[["column","fail_axis","fill_rate","total","spatial_moran"]].head(25).to_string(index=False))
print(f"\n총 wafer 수: {n_wafers}, 총 die-row: {N:,}")
