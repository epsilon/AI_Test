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
