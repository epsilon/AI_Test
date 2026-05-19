import sqlglot
from sqlglot import exp

def normalize_sql(sql, dialect='spark'):
    """
    SQL을 템플릿으로 정규화.
    - 모든 리터럴 값 → ?
    - IN (a,b,c,...) → IN (?)   ← 리스트 길이 차이를 흡수
    구조가 같은 질의는 동일한 문자열이 됨.
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return None
    if tree is None:
        return None

    # IN 리스트 길이 정규화 (값 개수가 다른 동일 패턴 흡수)
    for in_node in tree.find_all(exp.In):
        if in_node.expressions:
            in_node.set('expressions', [exp.Placeholder()])

    # 나머지 리터럴 일괄 치환
    for lit in tree.find_all(exp.Literal):
        lit.replace(exp.Placeholder())

    return tree.sql(dialect=dialect)

# clustering
spark_df['sql_template'] = spark_df['query'].map(normalize_sql)

clusters = (
    spark_df.dropna(subset=['sql_template'])
        .groupby('sql_template')
        .agg(count=('query', 'size'),
             sample=('query', 'first'))
        .sort_values('count', ascending=False)
        .reset_index()
)

clusters.head(20)

# test
spark_df['sql_template'] = spark_df['query'].map(normalize_sql)

clusters = (
    spark_df.dropna(subset=['sql_template'])
        .groupby('sql_template')
        .agg(count=('query', 'size'),
             sample=('query', 'first'))
        .sort_values('count', ascending=False)
        .reset_index()
)

clusters.head(20)

d = starrocks_df
n = len(d)
print("note_id 채움률      :", d['note_id'].notna().mean() if 'note_id' in d else "컬럼없음")
print("paragraph_id 채움률 :", d['paragraph_id'].notna().mean() if 'paragraph_id' in d else "컬럼없음")
print("노트당 평균 쿼리 수  :",
      round(d.groupby('note_id').size().mean(),1) if 'note_id' in d else "-")
print("쿼리>=2인 노트 비율  :",
      round((d.groupby('note_id').size()>=2).mean(),2) if 'note_id' in d else "-")
# paragraph_id가 순서를 담는지 — 한 노트 안에서 단조증가/정렬 가능한지
if 'note_id' in d and 'paragraph_id' in d:
    smp = d[d['note_id']==d['note_id'].dropna().iloc[0]][['paragraph_id','execute_time']]
    print("\n샘플 노트의 paragraph_id 값:\n", smp.head(10).to_string(index=False))

import json
import pandas as pd
from collections import Counter, defaultdict, deque

d = starrocks_df.copy()

# ── 0. tables 컬럼 확보 (이전 파이프라인 산출물) ──
assert 'tables' in d.columns, "tables(파싱결과) 컬럼 필요 — extract 파이프라인 먼저"

def fq(t):
    return '.'.join(p for p in t if p) if isinstance(t, tuple) else None

def rep_table(tbls):
    """쿼리 1건의 대표 테이블 1개. 리스트 중 freq 최대(전역) 우선."""
    fs = [fq(x) for x in tbls if fq(x)] if isinstance(tbls, list) else []
    if not fs:
        return None
    return max(fs, key=lambda t: GFREQ.get(t, 0))

# 전역 테이블 빈도 (대표 선정 기준)
GFREQ = Counter()
for lst in d['tables']:
    if isinstance(lst, list):
        for x in lst:
            f = fq(x)
            if f: GFREQ[f] += 1

# ── 1. 노트 내부 정렬 → 대표 테이블 시퀀스 ──
d['_t'] = pd.to_datetime(d['execute_time'], errors='coerce')
d['_rep'] = d['tables'].map(rep_table)

seqs = []   # 노트별 [대표테이블, ...] (연속 중복 제거 전)
for nid, g in d.dropna(subset=['_rep']).groupby('note_id'):
    g = g.sort_values('_t', kind='stable')
    seq = [t for t in g['_rep'].tolist()]
    if len(seq) >= 2:
        seqs.append(seq)

print(f"세트(노트) 수: {len(seqs):,}  ·  평균 길이: "
      f"{sum(len(s) for s in seqs)/max(len(seqs),1):.1f}")

# ── 2. 전이 집계 (A→B). 같은 테이블 연속은 압축 ──
trans = Counter()
note_pairs = defaultdict(set)   # 전이별 등장 노트 수(신뢰도용)
for i, seq in enumerate(seqs):
    comp = [seq[0]]
    for t in seq[1:]:
        if t != comp[-1]:        # 연속 중복 압축 (같은 테이블 반복 조회 제거)
            comp.append(t)
    for a, b in zip(comp, comp[1:]):
        trans[(a, b)] += 1
        note_pairs[(a, b)].add(i)

# ── 3. 방향 그래프 JSON (usage flow) ──
nodes = sorted({t for ab in trans for t in ab})
links = []
for (a, b), c in trans.items():
    links.append({
        'source': a, 'target': b,
        'freq': int(c),
        'notes': len(note_pairs[(a, b)])   # 몇 개 노트에서 이 흐름이 나왔나
    })

# 노드 통계
out_deg = Counter(a for a, b in trans)
in_deg  = Counter(b for a, b in trans)
graph_flow = {
  'nodes': [{'id': n, 'out': int(out_deg.get(n,0)),
             'in': int(in_deg.get(n,0)),
             'total': int(GFREQ.get(n,0))} for n in nodes],
  'links': links
}

with open('usage_flow.json','w',encoding='utf-8') as f:
    json.dump(graph_flow, f, ensure_ascii=False)

print(f"흐름 노드 {len(nodes):,} · 전이 엣지 {len(links):,} → usage_flow.json")

# ── 4. 핵심 흐름 Top (노트 수 기준 = 신뢰도) ──
top = sorted(links, key=lambda x: (x['notes'], x['freq']), reverse=True)[:25]
print("\n═══ 반복되는 테이블 흐름 Top 25 (노트수 · 빈도) ═══")
for l in top:
    print(f"  {l['source']:<28} → {l['target']:<28}  "
          f"노트 {l['notes']:>3} · 빈도 {l['freq']:>4}")

# ── 5. 시작 테이블 / 종착 테이블 (작업 진입·산출점) ──
starts = Counter(s[0] for s in seqs)
ends   = Counter(s[-1] for s in seqs)
print("\n── 작업 시작점 Top 10 (노트가 여기서 출발) ──")
for t, c in starts.most_common(10):
    print(f"  {t:<32} {c}")
print("\n── 작업 종착점 Top 10 (노트가 여기서 끝남) ──")
for t, c in ends.most_common(10):
    print(f"  {t:<32} {c}")

raw = sum(len(s)-1 for s in seqs)
comp_sum = sum(
    len([seq[0]] + [t for t in seq[1:] if t != ([seq[0]]+[x for x in seq[1:]])[-1]])
    for seq in seqs) if False else sum(
    (lambda c=[s[0]]: [c.append(t) for t in s[1:] if t!=c[-1]] and len(c) or len(c))()
    for s in seqs)
print(f"압축 전 전이 {raw:,} → 압축 후 {sum(len(set(zip(s,s[1:]))) for s in seqs):,}")
print("노트별 고유 대표테이블 수 분포:",
      pd.Series([len(set(s)) for s in seqs]).describe()[['mean','50%','max']].to_dict())

import json
import pandas as pd
from collections import Counter, defaultdict

d = starrocks_df.copy()
assert 'tables' in d.columns, "tables 컬럼 필요"

def fqset(tbls):
    """쿼리 1건이 건드린 테이블 집합."""
    if not isinstance(tbls, list):
        return set()
    return {'.'.join(p for p in x if p) for x in tbls
            if isinstance(x, tuple) and any(x)}

d['_t']  = pd.to_datetime(d['execute_time'], errors='coerce')
d['_set'] = d['tables'].map(fqset)

GFREQ = Counter()
for s in d['_set']:
    GFREQ.update(s)

# ── 노트별: 시간순으로 "새로 등장한 테이블"을 흐름 스텝으로 ──
seqs = []          # 노트별 [신규등장 테이블, ...]
seen_sets = []     # (디버그용) 노트별 누적
for nid, g in d[d['_set'].map(bool)].groupby('note_id'):
    g = g.sort_values('_t', kind='stable')
    seen = set()
    step = []
    for s in g['_set']:
        new = s - seen          # 이번 쿼리에서 처음 등장한 테이블
        if new:
            # 같은 쿼리에 여러 개 새로 들어오면 freq 높은 순으로 펼침
            for t in sorted(new, key=lambda x: -GFREQ.get(x, 0)):
                step.append(t)
            seen |= s
    if len(step) >= 2:
        seqs.append(step)

print(f"세트(노트) 수: {len(seqs):,}  ·  평균 흐름 길이: "
      f"{sum(len(s) for s in seqs)/max(len(seqs),1):.1f}")
print("노트별 흐름 길이 분포:",
      pd.Series([len(s) for s in seqs]).describe()[['mean','50%','max']].round(1).to_dict())

# ── 전이 집계 (A→B = A 등장 후 B가 새로 합류) ──
trans = Counter()
note_pairs = defaultdict(set)
for i, seq in enumerate(seqs):
    for a, b in zip(seq, seq[1:]):
        if a != b:
            trans[(a, b)] += 1
            note_pairs[(a, b)].add(i)

nodes = sorted({t for ab in trans for t in ab})
out_deg = Counter(a for a, _ in trans)
in_deg  = Counter(b for _, b in trans)
graph_flow = {
  'nodes': [{'id': n, 'out': int(out_deg.get(n,0)),
             'in': int(in_deg.get(n,0)),
             'total': int(GFREQ.get(n,0))} for n in nodes],
  'links': [{'source': a, 'target': b, 'freq': int(c),
             'notes': len(note_pairs[(a,b)])}
            for (a,b), c in trans.items()]
}
with open('usage_flow.json','w',encoding='utf-8') as f:
    json.dump(graph_flow, f, ensure_ascii=False)
print(f"흐름 노드 {len(nodes):,} · 전이 엣지 {len(graph_flow['links']):,} → usage_flow.json")

# ── 핵심 흐름 (노트 수 = 신뢰도) ──
top = sorted(graph_flow['links'], key=lambda x:(x['notes'],x['freq']), reverse=True)[:25]
print("\n═══ 반복되는 분석 전개 Top 25 (노트수 · 빈도) ═══")
for l in top:
    print(f"  {l['source']:<28} → {l['target']:<28} 노트 {l['notes']:>3} · 빈도 {l['freq']:>4}")

starts = Counter(s[0]  for s in seqs)
ends   = Counter(s[-1] for s in seqs)
print("\n── 분석 진입 테이블 Top 10 ──")
for t,c in starts.most_common(10): print(f"  {t:<32} {c}")
print("\n── 분석 종착 테이블 Top 10 ──")
for t,c in ends.most_common(10):   print(f"  {t:<32} {c}")
