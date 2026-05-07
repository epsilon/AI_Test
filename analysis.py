import pandas as pd

def build_select_all(engine, table: str) -> str:
    """
    'catalog.db.table' 주면 모든 컬럼 명시한 SELECT 문 반환 (DESC 기반)
    """
    catalog, schema, tbl = table.split('.')

    df = pd.read_sql(f"DESC `{catalog}`.`{schema}`.`{tbl}`", engine)

    if df.empty:
        raise ValueError(f"컬럼을 찾을 수 없습니다: {table}")

    # DESC 결과에 Comment 컬럼이 있을 수도, 없을 수도 있음
    comment_col = next((c for c in df.columns if c.lower() == 'comment'), None)

    lines = []
    for i, row in df.iterrows():
        comma = ',' if i < len(df) - 1 else ''
        line = f"    `{row['Field']}`{comma}"
        if comment_col and pd.notna(row[comment_col]) and row[comment_col]:
            pad = max(0, 40 - len(line))
            line = f"{line}{' ' * pad}-- {row[comment_col]}"
        lines.append(line)

    return "SELECT\n" + "\n".join(lines) + f"\nFROM `{catalog}`.`{schema}`.`{tbl}`"

def _desc(engine, table: str):
    catalog, schema, tbl = table.split('.')
    df = pd.read_sql(f"DESC `{catalog}`.`{schema}`.`{tbl}`", engine)
    return (catalog, schema, tbl), df


def build_join(engine, table1: str, table2: str,
               join_keys=None,
               join_type: str = "INNER",
               a1: str = "a", a2: str = "b") -> str:
    """
    두 테이블의 JOIN SELECT 문 생성

    join_keys 형식:
      - None                 : 공통 컬럼명 자동 감지 (대소문자 무시)
      - ['USER_ID', 'DT']    : 양쪽 컬럼명이 같을 때
      - {'dt': 'srdt'}       : 이름이 다를 때 {a쪽: b쪽}
      - [('dt','srdt'),
         ('USER_ID','USER_ID')]  : 혼합/순서 보존이 필요할 때
    """
    (c1, s1, t1), df1 = _desc(engine, table1)
    (c2, s2, t2), df2 = _desc(engine, table2)

    cols1 = df1['Field'].tolist()
    cols2 = df2['Field'].tolist()
    cmt_col = next((c for c in df1.columns if c.lower() == 'comment'), None)
    cmt1 = dict(zip(df1['Field'], df1[cmt_col])) if cmt_col else {}
    cmt2 = dict(zip(df2['Field'], df2[cmt_col])) if cmt_col else {}

    # 1) join_keys를 (a컬럼, b컬럼) 페어 리스트로 정규화
    if join_keys is None:
        lower1 = {c.lower(): c for c in cols1}
        lower2 = {c.lower(): c for c in cols2}
        common = set(lower1) & set(lower2)
        if not common:
            raise ValueError("공통 컬럼이 없습니다. join_keys를 명시해주세요.")
        pairs = [(lower1[k], lower2[k]) for k in common]
        print(f"[자동 감지] {pairs}")
    elif isinstance(join_keys, dict):
        pairs = list(join_keys.items())
    elif isinstance(join_keys, list):
        pairs = [(p, p) if isinstance(p, str) else tuple(p) for p in join_keys]
    else:
        raise TypeError("join_keys는 None / list / dict 만 가능")

    # 2) SELECT 컬럼 조립
    b_join_keys = {bk.lower() for _, bk in pairs}
    cols1_set = {c.lower() for c in cols1}

    lines = []
    for c in cols1:
        line = f"    {a1}.`{c}`"
        if cmt1.get(c):
            line += f"  -- {cmt1[c]}"
        lines.append(line)

    for c in cols2:
        if c.lower() in b_join_keys:
            continue                          # b쪽 조인 키는 중복이라 제외
        if c.lower() in cols1_set:            # 이름 충돌 시 별칭
            line = f"    {a2}.`{c}` AS `{a2}_{c}`"
        else:
            line = f"    {a2}.`{c}`"
        if cmt2.get(c):
            line += f"  -- {cmt2[c]}"
        lines.append(line)

    select_clause = ",\n".join(lines)

    # 3) ON 절
    on = " AND ".join(f"{a1}.`{ak}` = {a2}.`{bk}`" for ak, bk in pairs)

    return (
        f"SELECT\n{select_clause}\n"
        f"FROM `{c1}`.`{s1}`.`{t1}` {a1}\n"
        f"{join_type} JOIN `{c2}`.`{s2}`.`{t2}` {a2}\n"
        f"  ON {on}"
    )

