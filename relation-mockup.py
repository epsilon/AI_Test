import sqlglot
from sqlglot import exp
import pandas as pd
import json

def extract_join_pairs(sql, dialect='spark'):
    """단일 쿼리에서 JOIN ON의 컬럼 페어 추출. alias는 실제 테이블로 해소."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        return {'pairs': [], 'error': str(e)}
    if tree is None:
        return {'pairs': [], 'error': 'empty'}

    # alias / 이름 → catalog.db.table 풀네임
    amap = {}
    for tbl in tree.find_all(exp.Table):
        fq = '.'.join(p for p in (tbl.catalog, tbl.db, tbl.name) if p)
        if tbl.alias_or_name:
            amap[tbl.alias_or_name] = fq
        amap.setdefault(tbl.name, fq)

    pairs = []
    for j in tree.find_all(exp.Join):
        on = j.args.get('on')
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            l, r​​​​​​​​​​​​​​​​
