import re

def strip_sql_comments(s):
    if not isinstance(s, str):
        return s
    s = re.sub(r'/\*.*?\*/', ' ', s, flags=re.DOTALL)   # /* ... */ 다중라인
    s = re.sub(r'--[^\n]*', ' ', s)                     # -- ... 줄 끝까지
    s = re.sub(r'\s+', ' ', s).strip()                  # 연속 공백 정리
    return s

final_query_df['query_nocomment'] = final_query_df['query'].map(strip_sql_comments)

per_user = final_query_df.groupby('username').agg(
    total_queries  = ('sql_template', 'size'),
    unique_queries = ('sql_template', 'nunique'),
).sort_values('total_queries', ascending=False)

per_user.head(20)

import re

KEYWORDS = (r'SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|'
            r'GROUP|ORDER|HAVING|LIMIT|OFFSET|UNION|INTERSECT|EXCEPT|WITH|'
            r'AND|OR|VALUES|INSERT|UPDATE|DELETE|SET')

def fix_inline_comments(sql):
    """-- 주석 뒤에 SQL 키워드가 같은 줄에 붙어있으면 그 앞에 \\n 삽입."""
    if not isinstance(sql, str):
        return sql
    pattern = re.compile(
        r'(--[^\n]*?)\s+(?=(?:' + KEYWORDS + r')\b)',
        re.IGNORECASE
    )
    return pattern.sub(r'\1\n', sql)

import re

SQL_KEYWORDS = {
    'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE',
    'SHOW', 'DESC', 'DESCRIBE', 'USE', 'SET', 'EXPLAIN', 'ALTER', 'DROP'
}

def classify_prefix(sql):
    """
    쿼리 맨 앞 식별자를 (kind, label)로 반환.
    - ('tag', 'SUBQUERY')    : --SUBQUERY, /*[TOF 같은 도구 태그
    - ('keyword', 'SELECT')  : 일반 SQL 시작
    - ('comment', '--')      : 태그 없는 주석만
    - ('unknown', None)
    """
    if not isinstance(sql, str):
        return ('unknown', None)
    
    # 앞 공백 + 떠도는 따옴표(스마트따옴표 포함) 제거
    s = sql.lstrip().lstrip("'\"\u2018\u2019\u201C\u201D")
    
    # 1) 라인 주석 + 바로 붙은 태그: --SUBQUERY, --FQC, -- TAG
    m = re.match(r'--\s*\[?\s*([A-Za-z_][A-Za-z0-9_]*)', s)
    if m:
        tag = m.group(1).upper()
        if tag in SQL_KEYWORDS:           # `-- SELECT ...` 처럼 사람 주석
            return ('comment', '--')
        return ('tag', tag)
    
    # 2) 블록 주석 + 태그: /*[TOF, /* TAG */
    m = re.match(r'/\*\s*\[?\s*([A-Za-z_][A-Za-z0-9_]*)', s)
    if m:
        tag = m.group(1).upper()
        if tag in SQL_KEYWORDS:
            return ('comment', '/*')
        return ('tag', tag)
    
    # 3) 태그 없는 주석만 있는 경우
    if s.startswith('--'): return ('comment', '--')
    if s.startswith('/*'): return ('comment', '/*')
    
    # 4) 일반 SQL 키워드로 시작
    m = re.match(r'([A-Za-z_]+)', s)
    if m:
        kw = m.group(1).upper()
        return ('keyword', kw) if kw in SQL_KEYWORDS else ('unknown', kw)
    
    return ('unknown', None)

spark_df[['prefix_kind', 'prefix_label']] = (
    spark_df['paragraph'].map(classify_prefix).apply(pd.Series)
)

(spark_df.groupby(['prefix_kind', 'prefix_label'])
        .size()
        .sort_values(ascending=False)
        .head(20))
