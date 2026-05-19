import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope
import pandas as pd

def _base_tables(scope):
    """이 스코프(또는 CTE 스코프)가 최종적으로 의존하는 실제 베이스 테이블 fq 집합."""
    out = set()
    for src_name, src in scope.sources.items():
        if isinstance(src, exp.Table):
            out.add('.'.join(p for p in (src.catalog, src.db, src.name) if p))
        else:
            # 서브쿼리/CTE 스코프 → 재귀로 내부 베이스까지
            try:
                out |= _base_tables(src)
            except Exception:
                pass
    return out

def extract_join_pairs(sql, dialect='spark'):
    st = {'eq_cols':0,'resolved':0,'no_prefix':0,'cte_unwrapped':0,
          'multi_ambig':0,'unknown':0}
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        return {'pairs': [], 'stats': st, 'error': str(e)}
    if tree is None:
        return {'pairs': [], 'stats': st, 'error': 'empty'}
    try:
        root = build_scope(tree)
    except Exception as e:
        return {'pairs': [], 'stats': st, 'error': f'scope:{e}'}
    if root is None:
        return {'pairs': [], 'stats': st, 'error': 'no scope'}

    def resolve(col, scope):
        """컬럼 → 실제 테이블 fq 리스트. CTE/서브쿼리면 내부 베이스로 펼침."""
        pref = col.table
        if not pref:
            return [], 'no_prefix'
        src = scope.sources.get(pref)
        if src is None:
            return [], 'unknown'
        if isinstance(src, exp.Table):
            return ['.'.join(p for p in (src.catalog, src.db, src.name) if p)], 'resolved'
        # CTE 또는 파생 스코프 → 내부 베이스 테이블로 unwrap
        bases = _base_tables(src)
        if not bases:
            return [], 'unknown'
        if len(bases) == 1:
            return [next(iter(bases))], 'cte_unwrapped'
        return list(bases), 'multi_ambig'   # CTE 안에서 이미 join된 경우 다중

    pairs = []
    for scope in root.traverse():
        sel = scope.expression
        if not isinstance(sel, exp.Select):
            continue
        for j in (sel.args.get('joins') or []):
            on = j.args.get('on')
            if on is None:
                continue
            for eq in on.find_all(exp.EQ):
                l, r = eq.this, eq.expression
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
                    continue
                st['eq_cols'] += 2
                lts, lr = resolve(l, scope)
                rts, rr = resolve(r, scope)
                st[lr] += 1; st[rr] += 1
                if not lts or not rts:
                    continue
                # 다중(ambiguous)이면 모든 조합을 약하게 잇기보단,
                # 단일로 해소된 쪽이 있을 때만 명확한 페어 생성
                for lt in lts:
                    for rt in rts:
                        if lt and rt and lt != rt:
                            a, b = (lt, l.name), (rt, r.name)
                            if a > b:
                                a, b = b, a
                            pairs.append((a[0], a[1], b[0], b[1]))
    return {'pairs': pairs, 'stats': st, 'error': None}


col = 'query_nocomment' if 'query_nocomment' in final_query_df.columns else 'query'
src = final_query_df[['username', col]].dropna(subset=[col]).copy()
res = src[col].map(extract_join_pairs)
src['pairs'] = res.map(lambda d: d['pairs'])

# ── 해소불가 진단 (전체 합산) ──
agg = {'eq_cols':0,'resolved':0,'no_prefix':0,'derived':0,'unknown':0}
for s in res.map(lambda d: d['stats']):
    for k in agg: agg[k] += s[k]

tot = agg['eq_cols'] or 1
print("═══ JOIN ON 컬럼 참조 해소 결과 ═══")
print(f"총 컬럼 참조      : {agg['eq_cols']:,}")
print(f"  해소 성공       : {agg['resolved']:,}  ({agg['resolved']/tot:.1%})")
print(f"  접두어 없음     : {agg['no_prefix']:,}  ({agg['no_prefix']/tot:.1%})  ← 스키마 있어야 풀림")
print(f"  파생소스(CTE등) : {agg['derived']:,}  ({agg['derived']/tot:.1%})")
print(f"  미상 alias      : {agg['unknown']:,}  ({agg['unknown']/tot:.1%})")
print(f"파싱 실패 쿼리    : {res.map(lambda d: d['error'] is not None).sum():,}건")

# ── 그래프 재생성 (해소된 페어만) ──
ex = src[['username','pairs']]
ex = ex[ex['pairs'].map(lambda x: isinstance(x,list) and len(x)>0)].explode('pairs')
ex[['tA','cA','tB','cB']] = pd.DataFrame(ex['pairs'].tolist(), index=ex.index)

edges = (ex.groupby(['tA','cA','tB','cB'])
           .agg(freq=('username','size'), users=('username','nunique'))
           .reset_index())
deg = pd.concat([edges[['tA','freq']].rename(columns={'tA':'id'}),
                 edges[['tB','freq']].rename(columns={'tB':'id'})])
node_stat = deg.groupby('id')['freq'].sum().to_dict()
node_deg = pd.concat([edges['tA'], edges['tB']]).value_counts().to_dict()

graph = {
  'nodes':[{'id':n,'freq':int(node_stat[n]),'degree':int(node_deg[n])} for n in sorted(node_stat)],
  'links':[{'source':r.tA,'target':r.tB,'colA':r.cA,'colB':r.cB,
            'freq':int(r.freq),'users':int(r.users)} for r in edges.itertuples()]
}
import json
with open('join_graph.json','w',encoding='utf-8') as f:
    json.dump(graph, f, ensure_ascii=False)
print(f"\n테이블 {len(graph['nodes']):,} · 엣지 {len(graph['links']):,} → join_graph.json")

from collections import defaultdict, deque

def add_groups(graph):
    adj = defaultdict(set)
    for l in graph['links']:
        adj[l['source']].add(l['target'])
        adj[l['target']].add(l['source'])
    comp, cid = {}, 0
    for n in graph['nodes']:
        s = n['id']
        if s in comp:
            continue
        cid += 1
        q = deque([s]); comp[s] = cid
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in comp:
                    comp[v] = cid; q.append(v)
    for n in graph['nodes']:
        n['group'] = comp[n['id']]
    return graph

add_groups(graph)

# 그룹 크기 분포 — 이게 핵심 판단 지표
from collections import Counter
sizes = Counter(n['group'] for n in graph['nodes'])
big = sizes.most_common()
print(f"총 그룹 수: {len(sizes)}")
for gid, cnt in big[:15]:
    members = [n['id'] for n in graph['nodes'] if n['group'] == gid]
    cats = Counter(m.split('.')[0] for m in members if '.' in m)
    print(f"  G{gid}: {cnt:3d}개  · 주 catalog={dict(cats.most_common(3))}")

import json
with open('join_graph.json','w',encoding='utf-8') as f:
    json.dump(graph, f, ensure_ascii=False)
print("→ group 필드 추가해서 저장")