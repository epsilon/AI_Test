import pandas as pd

def build_select_all(engine, table: str) -> str:
    """
    'catalog.db.table' 주면 모든 컬럼 명시한 SELECT 문 반환
    """
    catalog, schema, tbl = table.split('.')

    df = pd.read_sql(f"""
        SELECT column_name, column_comment
        FROM information_schema.columns
        WHERE table_catalog = '{catalog}'
          AND table_schema  = '{schema}'
          AND table_name    = '{tbl}'
        ORDER BY ordinal_position
    """, engine)

    if df.empty:
        raise ValueError(f"컬럼을 찾을 수 없습니다: {table}")

    lines = []
    for i, row in df.iterrows():
        comma = ',' if i < len(df) - 1 else ''
        line = f"    `{row['column_name']}`{comma}"
        if row['column_comment']:
            pad = max(0, 40 - len(line))
            line = f"{line}{' ' * pad}-- {row['column_comment']}"
        lines.append(line)

    return f"SELECT\n" + "\n".join(lines) + f"\nFROM `{catalog}`.`{schema}`.`{tbl}`"
