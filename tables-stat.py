import pandas as pd

# tables 컬럼: 행마다 [(catalog, db, table), ...] 리스트
# 1) 행 단위 explode → 참조 1건 = 1행
t = final_query_df[['username', 'tables']].copy()
t = t[t['tables'].map(lambda x: isinstance(x, list) and len(x) > 0)]
t = t.explode('tables')

# 2) 튜플 → 정규화된 풀네임 (None 파트는 생략)
def fq_name(tup):
    if not isinstance(tup, tuple):
        return None
    parts = [p for p in tup if p]            # None/'' 제거
    return '.'.join(parts) if parts else None

t['full']    = t['tables'].map(fq_name)
t['catalog'] = t['tables'].map(lambda x: x[0] if isinstance(x, tuple) else None)
t['db']      = t['tables'].map(lambda x: x[1] if isinstance(x, tuple) else None)
t['table']   = t['tables'].map(lambda x: x[2] if isinstance(x, tuple) and len(x) > 2 else None)
t = t.dropna(subset=['full'])

# ── 핵심 숫자 ──
print(f"총 테이블 참조 건수 : {len(t):,}")
print(f"고유 테이블 수      : {t['full'].nunique():,}")
print(f"고유 catalog 수     : {t['catalog'].dropna().nunique()}")
print()

# 3) 시스템(catalog/db)별 분포 — 도메인 18개 시스템 중 실제로 쓰이는 것
print('═══ catalog별 테이블 참조 ═══')
print(t.groupby('catalog').agg(
    참조건수   = ('full', 'size'),
    고유테이블 = ('full', 'nunique'),
    고유사용자 = ('username', 'nunique'),
).sort_values('참조건수', ascending=False))
print()

# 4) 가장 많이 쓰인 테이블 Top 30
print('═══ Top 30 테이블 ═══')
top_tbl = t.groupby('full').agg(
    참조건수   = ('username', 'size'),
    고유사용자 = ('username', 'nunique'),
).sort_values(['고유사용자', '참조건수'], ascending=False).head(30)
print(top_tbl.to_string())
