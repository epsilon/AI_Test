import sqlglot
from sqlglot import exp

_BINARY_OPS = {
    exp.EQ: '=', exp.NEQ: '!=',
    exp.GT: '>', exp.GTE: '>=',
    exp.LT: '<', exp.LTE: '<=',
}


def _val(node):
    if node is None:
        return None
    if isinstance(node, exp.Literal):
        return node.this
    return node.sql()


def _col_and_value(a, b):
    if isinstance(a, exp.Column) and not isinstance(b, exp.Column):
        return a, b
    if isinstance(b, exp.Column) and not isinstance(a, exp.Column):
        return b, a
    return None, None


def _parse_filter(node):
    for cls, sym in _BINARY_OPS.items():
        if isinstance(node, cls):
            col, val = _col_and_value(node.this, node.expression)
            if col is None:
                return None
            return (col.table or None, col.name, sym, _val(val))

    if isinstance(node, exp.In):
        col = node.this
        if isinstance(col, exp.Column):
            vals = tuple(_val(v) for v in (node.expressions or []))
            return (col.table or None, col.name, 'IN', vals)

    if isinstance(node, (exp.Like, exp.ILike)):
        col, val = node.this, node.expression
        if isinstance(col, exp.Column):
            op = 'ILIKE' if isinstance(node, exp.ILike) else 'LIKE'
            return (col.table or None, col.name, op, _val(val))

    if isinstance(node, exp.Between):
        col = node.this
        if isinstance(col, exp.Column):
            return (col.table or None, col.name, 'BETWEEN',
                    (_val(node.args.get('low')), _val(node.args.get('high'))))

    if isinstance(node, exp.Is):
        col = node.this
        if isinstance(col, exp.Column):
            return (col.table or None, col.name, 'IS', _val(node.expression))

    return None


def _build_alias_map(tree):
    aliases = {}
    for t in tree.find_all(exp.Table):
        full = (t.catalog or None, t.db or None, t.name)
        aliases[t.alias_or_name] = full   # alias 없으면 테이블명이 키
    return aliases


def _resolve(ref, aliases):
    if ref is None:
        return (None, None, None)
    return aliases.get(ref, (None, None, ref))


def parse_sql(sql, dialect='spark'):
    """
    SQL 한 문장에서 카탈로그 분석용 정보 전체 추출.

    Returns
    -------
    {
      'tables':         [(catalog, db, table), ...],
      'select_columns': [(catalog, db, table, column), ...],
      'conditions':     [(catalog, db, table, column, op, value), ...],
      'joins':          [((c,d,t,col), (c,d,t,col)), ...],
      'error':          None or str
    }
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        return {'tables': [], 'select_columns': [], 'conditions': [],
                'joins': [], 'error': str(e)}
    if tree is None:
        return {'tables': [], 'select_columns': [], 'conditions': [],
                'joins': [], 'error': 'empty parse'}

    aliases = _build_alias_map(tree)
    tables = sorted(set(aliases.values()))

    # SELECT 컬럼
    select_columns = []
    select = tree.find(exp.Select)
    if select is not None:
        for proj in select.expressions:
            for c in proj.find_all(exp.Column):
                cat, db, tbl = _resolve(c.table, aliases)
                select_columns.append((cat, db, tbl, c.name))

    # WHERE 조건
    conditions = []
    targets = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
               exp.In, exp.Like, exp.ILike, exp.Between, exp.Is)
    for where in tree.find_all(exp.Where):
        for node in where.find_all(*targets):
            parsed = _parse_filter(node)
            if parsed is None:
                continue
            tref, col, op, val = parsed
            cat, db, tbl = _resolve(tref, aliases)
            conditions.append((cat, db, tbl, col, op, val))

    # JOIN ON 키 쌍
    joins = []
    for join in tree.find_all(exp.Join):
        on = join.args.get('on')
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            l, r = eq.this, eq.expression
            if isinstance(l, exp.Column) and isinstance(r, exp.Column):
                lcat, ldb, ltbl = _resolve(l.table, aliases)
                rcat, rdb, rtbl = _resolve(r.table, aliases)
                joins.append(((lcat, ldb, ltbl, l.name),
                              (rcat, rdb, rtbl, r.name)))

    return {
        'tables': tables,
        'select_columns': select_columns,
        'conditions': conditions,
        'joins': joins,
        'error': None,
    }

#Test
sql = """
SELECT l.lot_id, l.wafer_id, r.recipe_name, m.measure_value
FROM fdc.lot_hist l
JOIN tas.recipe_master r ON l.recipe_id = r.recipe_id
LEFT JOIN fdc.measurement m ON l.lot_id = m.lot_id
WHERE l.process_date >= '2026-01-01'
  AND l.fab_id IN ('M14','M15','M16')
  AND r.recipe_name LIKE 'ETCH_%'
  AND m.measure_value BETWEEN 0.1 AND 0.9
"""
parse_sql(sql)

# DataFrame
parsed = spark_df['paragraph'].dropna().map(parse_sql)

spark_df.loc[parsed.index, 'tables']         = parsed.map(lambda d: d['tables'])
spark_df.loc[parsed.index, 'select_columns'] = parsed.map(lambda d: d['select_columns'])
spark_df.loc[parsed.index, 'conditions']     = parsed.map(lambda d: d['conditions'])
spark_df.loc[parsed.index, 'joins']          = parsed.map(lambda d: d['joins'])
spark_df.loc[parsed.index, 'parse_error']    = parsed.map(lambda d: d['error'])
