import pandas as pd

def build_select_all(engine, table: str, with_comment: bool = True,
                     method: str = "info_schema") -> str:
    """
    테이블의 모든 컬럼을 명시한 SELECT 문 생성

    Parameters
    ----------
    table : 'catalog.db.table' / 'db.table' / 'table' 형식 모두 지원
    with_comment : True이면 컬럼 옆에 -- 주석 표시
    method : 'info_schema' (기본) 또는 'desc'
    """
    # 1) 식별자 파싱
    parts = table.split('.')
    if len(parts) == 3:
        catalog, schema, tbl = parts
    elif len(parts) == 2:
        catalog, schema, tbl = None, parts[0], parts[1]
    elif len(parts) == 1:
        catalog, schema, tbl = None, None, parts[0]
    else:
        raise ValueError(f"잘못된 테이블 식별자: {table}")

    # 2) 컬럼 정보 가져오기
    if method == "info_schema":
        where = [f"table_name = '{tbl}'"]
        if schema:  where.append(f"table_schema = '{schema}'")
        if catalog: where.append(f"table_catalog = '{catalog}'")
        sql = f"""
            SELECT column_name, data_type, column_comment
            FROM information_schema.columns
            WHERE {' AND '.join(where)}
            ORDER BY ordinal_position
        """
        df = pd.read_sql(sql, engine)
        cols = df['column_name'].tolist()
        comments = dict(zip(df['column_name'], df['column_comment'].fillna('')))
    elif method == "desc":
        df = pd.read_sql(f"DESC {table}", engine)
        cols = df['Field'].tolist()
        comments = dict(zip(df['Field'], df.get('Comment', pd.Series([''] * len(df)))))
    else:
        raise ValueError("method는 'info_schema' 또는 'desc'")

    if not cols:
        raise ValueError(f"컬럼을 찾을 수 없습니다: {table}")

    # 3) SELECT 절 조립
    lines = []
    for i, c in enumerate(cols):
        comma = ',' if i < len(cols) - 1 else ''
        line = f"    `{c}`{comma}"
        if with_comment and comments.get(c):
            # 주석은 컬럼 폭 맞춰서 정렬
            pad = max(0, 40 - len(line))
            line = f"{line}{' ' * pad}-- {comments[c]}"
        lines.append(line)

    # 4) FROM 절 (입력 형태 그대로 백틱 처리)
    from_parts = [f"`{p}`" for p in [catalog, schema, tbl] if p]
    from_clause = f"FROM {'.'.join(from_parts)}"

    return "SELECT\n" + "\n".join(lines) + "\n" + from_clause
