import pandas as pd

base = final_query_df[['username', 'sql_template']].dropna(subset=['sql_template'])

# ── 1) 개인별 사용 template (드릴다운용) ──
def user_templates(name, top=20):
    u = base[base['username'] == name]
    s = u['sql_template'].value_counts().head(top)
    print(f"[{name}] 총 {len(u):,}건 · 고유 template {u['sql_template'].nunique():,}개")
    return s

# 예: user_templates('홍길동')

# 개인별 요약 한 방
per_user = base.groupby('username').agg(
    총건수     = ('sql_template', 'size'),
    고유template = ('sql_template', 'nunique'),
)
per_user['집중도'] = (1 - per_user['고유template'] / per_user['총건수']).round(2)
print(per_user.sort_values('총건수', ascending=False).head(20).to_string())
print()

# ── 2) template별 공유도 (← 카탈로그 직결) ──
tpl = base.groupby('sql_template').agg(
    실행건수   = ('username', 'size'),
    고유사용자 = ('username', 'nunique'),
)

# 권장 쿼리 후보: 여러 사람이 쓰는 template
shared = tpl[tpl['고유사용자'] >= 3].sort_values(
    ['고유사용자', '실행건수'], ascending=False)
print(f"═══ 공유 template (3명 이상) : {len(shared):,}개 ═══")
print(shared.head(20).to_string())
print()

# 1인 전용 고빈도: 개인 자동화 / 배치 의심
solo = tpl[(tpl['고유사용자'] == 1) & (tpl['실행건수'] >= 20)]
print(f"═══ 1인 전용 고빈도 template : {len(solo):,}개 (배치/자동화 의심) ═══")
print(solo.sort_values('실행건수', ascending=False).head(15).to_string())
