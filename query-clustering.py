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
