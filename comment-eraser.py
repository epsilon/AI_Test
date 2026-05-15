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
