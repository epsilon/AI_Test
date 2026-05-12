import re

def strip_sql_comments(s):
    if not isinstance(s, str):
        return s
    s = re.sub(r'/\*.*?\*/', ' ', s, flags=re.DOTALL)   # /* ... */ 다중라인
    s = re.sub(r'--[^\n]*', ' ', s)                     # -- ... 줄 끝까지
    s = re.sub(r'\s+', ' ', s).strip()                  # 연속 공백 정리
    return s

final_query_df['query_nocomment'] = final_query_df['query'].map(strip_sql_comments)
