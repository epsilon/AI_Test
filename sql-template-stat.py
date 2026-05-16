# t에 sql_template 다시 붙이기 (explode 전 인덱스 기준)
t2 = final_query_df[['username', 'tables', 'sql_template']].copy()
t2 = t2[t2['tables'].map(lambda x: isinstance(x, list) and len(x) > 0)]
t2 = t2.explode('tables')
t2['full'] = t2['tables'].map(
    lambda x: '.'.join(p for p in x if p) if isinstance(x, tuple) else None
)
t2 = t2.dropna(subset=['full', 'sql_template'])

# 많이 쓰인 테이블 상위 N개로 한정 (고유사용자 기준)
top_tables = (t2.groupby('full')['username'].nunique()
                .sort_values(ascending=False).head(30).index)

sub = t2[t2['full'].isin(top_tables)]

stat = sub.groupby('full').agg(
    참조건수      = ('sql_template', 'size'),
    고유template  = ('sql_template', 'nunique'),
    고유사용자    = ('username', 'nunique'),
)
# 정형도: 1에 가까울수록 소수 template 반복, 0에 가까울수록 매번 다름
stat['정형도'] = 1 - stat['고유template'] / stat['참조건수']
# 사용자당 template 다양성
stat['사용자당_template'] = (stat['고유template'] / stat['고유사용자']).round(2)

stat = stat.sort_values('고유사용자', ascending=False)
print(stat.to_string())
