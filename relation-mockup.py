import sqlglot
from sqlglot import exp
import pandas as pd
import json

def extract_join_pairs(sql, dialect='spark'):
    """단일 쿼리에서 JOIN ON의 컬럼 페어 추출. alias는 실제 테이블로 해소."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        return {'pairs': [], 'error': str(e)}
    if tree is None:
        return {'pairs': [], 'error': 'empty'}

    # alias / 이름 → catalog.db.table 풀네임
    amap = {}
    for tbl in tree.find_all(exp.Table):
        fq = '.'.join(p for p in (tbl.catalog, tbl.db, tbl.name) if p)
        if tbl.alias_or_name:
            amap[tbl.alias_or_name] = fq
        amap.setdefault(tbl.name, fq)

    pairs = []
    for j in tree.find_all(exp.Join):
        on = j.args.get('on')
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            l, r = eq.this, eq.expression
            if isinstance(l, exp.Column) and isinstance(r, exp.Column):
                lt = amap.get(l.table, l.table or None)
                rt = amap.get(r.table, r.table or None)
                if lt and rt and lt != rt:
                    a, b = (lt, l.name), (rt, r.name)
                    if a > b:                      # 방향 무시 (A-B == B-A)
                        a, b = b, a
                    pairs.append((a[0], a[1], b[0], b[1]))
    return {'pairs': pairs, 'error': None}

# ── 적용 ──
col = 'query_nocomment' if 'query_nocomment' in final_query_df.columns else 'query'
src = final_query_df[['username', col]].dropna(subset=[col]).copy()
res = src[col].map(extract_join_pairs)
src['pairs'] = res.map(lambda d: d['pairs'])

ex = src[['username', 'pairs']]
ex = ex[ex['pairs'].map(lambda x: isinstance(x, list) and len(x) > 0)].explode('pairs')
ex[['tA', 'cA', 'tB', 'cB']] = pd.DataFrame(ex['pairs'].tolist(), index=ex.index)

# ── 엣지 집계 (컬럼 페어 단위) ──
edges = (ex.groupby(['tA', 'cA', 'tB', 'cB'])
           .agg(freq=('username', 'size'), users=('username', 'nunique'))
           .reset_index())

# ── 노드 집계 ──
deg = pd.concat([edges[['tA', 'freq']].rename(columns={'tA': 'id'}),
                 edges[['tB', 'freq']].rename(columns={'tB': 'id'})])
node_stat = deg.groupby('id')['freq'].sum().to_dict()
node_deg = pd.concat([edges['tA'], edges['tB']]).value_counts().to_dict()

graph = {
    'nodes': [{'id': n, 'freq': int(node_stat[n]), 'degree': int(node_deg[n])}
              for n in sorted(node_stat)],
    'links': [{'source': r.tA, 'target': r.tB, 'colA': r.cA, 'colB': r.cB,
               'freq': int(r.freq), 'users': int(r.users)}
              for r in edges.itertuples()]
}

print(f"테이블(노드): {len(graph['nodes']):,}  ·  JOIN 엣지: {len(graph['links']):,}")
print(f"파싱 실패: {res.map(lambda d: d['error'] is not None).sum():,}건")

with open('join_graph.json', 'w', encoding='utf-8') as f:
    json.dump(graph, f, ensure_ascii=False)
print("→ join_graph.json 저장 완료")
