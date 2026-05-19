import pandas as pd, numpy as np, json

df = starrocks_df

# 파싱된 tables / sql_template 있으면 사용 (이전 단계 산출물)
has_tbl = 'tables' in df.columns
has_tpl = 'sql_template' in df.columns
USER = 'real_user_id'

def ntables(x):
    return len({'.'.join(p for p in t if p) for t in x if isinstance(t, tuple)}) if isinstance(x, list) else 0

g = df.groupby(USER)
feat = pd.DataFrame({'q': g.size()})
feat['notes']    = g['note_id'].nunique() if 'note_id' in df else 0
feat['catalogs'] = g['catalog_name'].nunique() if 'catalog_name' in df else 0
if 'status' in df:
    ok = df.assign(_ok=df['status'].astype(str).str.upper().isin(['SUCCESS','FINISHED','OK','COMPLETE']))
    feat['succ'] = ok.groupby(USER)['_ok'].mean()
if 'type' in df:
    feat['spark_ratio'] = df.assign(_s=df['type'].astype(str).str.lower().eq('spark')).groupby(USER)['_s'].mean()

if has_tbl:
    tmp = df[[USER,'tables']].copy()
    tmp['_nt'] = tmp['tables'].map(ntables)
    feat['tables_distinct'] = tmp.groupby(USER)['tables'].apply(
        lambda s: len({'.'.join(p for p in t if p) for lst in s if isinstance(lst,list) for t in lst if isinstance(t,tuple)}))
    feat['join_ratio'] = tmp.assign(_j=tmp['_nt']>=2).groupby(USER)['_j'].mean()
else:
    feat['tables_distinct'] = feat['catalogs']           # 폴백
    feat['join_ratio'] = 0.0

if has_tpl:
    feat['tpl_distinct'] = g['sql_template'].nunique()
    feat['repeat'] = (1 - feat['tpl_distinct'] / feat['q']).clip(0,1)
else:
    feat['repeat'] = (1 - g['query'].nunique() / feat['q']).clip(0,1)

feat = feat.fillna(0).reset_index()

# ── 유형 판정: 데이터 기반 중앙값 분할 (폭 × 반복), 경량 분리 ──
VOL_MIN = max(20, feat['q'].quantile(0.50))              # 경량 컷
core = feat[feat['q'] >= VOL_MIN].copy()
bx = core['tables_distinct'].median()
by = core['repeat'].median()

def label(r):
    if r['q'] < VOL_MIN: return '경량/일회성'
    broad = r['tables_distinct'] >= bx
    rep   = r['repeat'] >= by
    if broad and not rep: return '탐색형 분석가'
    if not broad and rep: return '정형 추출형'
    if broad and rep:     return '광역 모니터'
    return '도메인 심층형'

feat['type_label'] = feat.apply(label, axis=1)

print(f"실사용자 {len(feat):,}명  ·  경량 컷 {VOL_MIN:.0f}쿼리  ·  분할선 폭={bx:.0f} 반복={by:.2f}")
print(feat['type_label'].value_counts())
print("\n유형별 쿼리 비중:")
print(feat.groupby('type_label')['q'].sum().sort_values(ascending=False)
        .pipe(lambda s:(s/s.sum()*100).round(1)))

out = {'medians': {'x': float(bx), 'y': float(by), 'volMin': float(VOL_MIN)},
       'users': [{'id': str(r[USER]), 'q': int(r['q']),
                  'tables': int(r['tables_distinct']), 'repeat': round(float(r['repeat']),3),
                  'joins': round(float(r['join_ratio']),3), 'notes': int(r['notes']),
                  'catalogs': int(r['catalogs']), 'type': r['type_label']}
                 for _, r in feat.iterrows()]}
with open('user_types.json','w',encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
print(f"\n→ user_types.json ({len(out['users']):,}명)")

import pandas as pd, json

df = starrocks_df.copy()
USER = 'real_user_id'

# ── execute_time 파싱 (전부 str 전제) ──
dt = pd.to_datetime(df['execute_time'], errors='coerce')
fail = dt.isna().sum()
print(f"execute_time 파싱: 실패 {fail:,} / {len(df):,} ({fail/len(df):.1%})")
if fail/len(df) > 0.3:
    print("  ⚠ 실패율 높음 — 포맷 직접 지정 필요. 샘플:", 
          df['execute_time'].dropna().head(3).tolist())
df['_hour'] = dt.dt.hour          # 0~23, 파싱 실패는 NaN

tpl_col = 'sql_template' if 'sql_template' in df else 'query'

def fq(t): return '.'.join(p for p in t if p) if isinstance(t,tuple) else None

users_out = []
for uid, gdf in df.groupby(USER):
    # 시간대별 실행 건수 (점 찍을 데이터)
    hist = gdf['_hour'].dropna().astype(int).value_counts().reindex(range(24), fill_value=0)
    # 상위 template (반복 구조)
    tpls = (gdf[tpl_col].fillna('(null)').value_counts().head(8)
              .rename_axis('t').reset_index(name='n'))
    top_tpl = [{'sql': (r.t[:160]+'…') if len(str(r.t))>160 else str(r.t),
                'n': int(r.n)} for r in tpls.itertuples()]
    # 테이블 분포
    tcnt = {}
    if 'tables' in gdf:
        for lst in gdf['tables']:
            if isinstance(lst, list):
                for t in {fq(x) for x in lst if fq(x)}:
                    tcnt[t] = tcnt.get(t,0)+1
    top_tbl = sorted(tcnt.items(), key=lambda kv:-kv[1])[:10]

    users_out.append({
        'id': str(uid),
        'q': int(len(gdf)),
        'hours': [int(hist[h]) for h in range(24)],
        'top_templates': top_tpl,
        'top_tables': [{'t':k,'n':v} for k,v in top_tbl],
        'notes': int(gdf['note_id'].nunique()) if 'note_id' in gdf else 0,
    })

# 앞서 만든 유형/지표(feat)와 병합 — feat가 메모리에 있다고 가정
base = {str(r['real_user_id']): r for _,r in feat.iterrows()}
for u in users_out:
    b = base.get(u['id'])
    if b is not None:
        u.update({'tables':int(b['tables_distinct']),'repeat':round(float(b['repeat']),3),
                  'joins':round(float(b['join_ratio']),3),'catalogs':int(b['catalogs']),
                  'type':b['type_label']})
    else:
        u.update({'tables':0,'repeat':0,'joins':0,'catalogs':0,'type':'경량/일회성'})

out = {'medians': {'x': float(bx), 'y': float(by), 'volMin': float(VOL_MIN)},
       'time_parse_fail': float(fail/len(df)),
       'users': users_out}
with open('user_types_detail.json','w',encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
print(f"→ user_types_detail.json ({len(users_out):,}명, 시간대+template+테이블 포함)")
