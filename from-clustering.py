    import sqlglot
from sqlglot import exp

def normalize_from_clause(sql, dialect='spark'):
    """
    FROM 이하만 템플릿으로 정규화.
    - SELECT 절은 통째로 무시 (액세스 패턴만 본다)
    - 리터럴 → ?, IN (...) → IN (?) 는 normalize_sql과 동일
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return None
    if tree is None or not isinstance(tree, exp.Select):
        return None

    # IN 리스트 길이 흡수
    for in_node in tree.find_all(exp.In):
        if in_node.expressions:
            in_node.set('expressions', [exp.Placeholder()])

    # 리터럴 일괄 치환
    for lit in tree.find_all(exp.Literal):
        lit.replace(exp.Placeholder())

    # FROM 이하 구성요소만 순서대로 뽑아 붙임
    parts = []
    if tree.args.get('from'):
        parts.append(tree.args['from'].sql(dialect=dialect))
    for join in tree.args.get('joins') or []:
        parts.append(join.sql(dialect=dialect))
    for key in ('where', 'group', 'having', 'qualify', 'order', 'limit'):
        node = tree.args.get(key)
        if node:
            parts.append(node.sql(dialect=dialect))

    return ' '.join(parts) if parts else None

spark_df['from_template'] = spark_df['paragraph'].map(normalize_from_clause)

from_clusters = (
    spark_df.dropna(subset=['from_template'])
        .groupby('from_template')
        .agg(count=('paragraph', 'size'),
             distinct_sql_templates=('sql_template', 'nunique'),
             sample=('paragraph', 'first'))
        .sort_values('count', ascending=False)
        .reset_index()
)

q1 = "SELECT lot_id FROM fdc.lot_hist WHERE fab_id = 'M14'"
q2 = "SELECT lot_id, status FROM fdc.lot_hist WHERE fab_id = 'M14'"
q3 = "SELECT COUNT(*) FROM fdc.lot_hist WHERE fab_id = 'M15'"
q4 = "SELECT lot_id FROM fdc.lot_hist WHERE fab_id = 'M14' AND status = 'DONE'"

for q in [q1, q2, q3, q4]:
    print(normalize_from_clause(q))
