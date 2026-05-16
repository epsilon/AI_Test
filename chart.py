import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 한글 폰트 (환경에 맞게)
plt.rcParams['font.family'] = 'Malgun Gothic'  # macOS면 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 컬럼명 매핑
USER_COL, TIME_COL = 'user', 'start_time'

user_counts = df[USER_COL].value_counts()
df['_hour'] = pd.to_datetime(df[TIME_COL]).dt.hour

# 1. Top 30 사용자
top = user_counts.head(30).iloc[::-1]
fig, ax = plt.subplots(figsize=(9, 8))
ax.barh(top.index.astype(str), top.values)
ax.set_xlabel('쿼리 수')
ax.set_title(f'Top 30 사용자 (전체 {len(user_counts):,}명)')
plt.tight_layout(); plt.show()

# 2. 시간대별 활성 사용자
hourly = df.groupby('_hour')[USER_COL].nunique()
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(hourly.index, hourly.values, marker='o', linewidth=2)
ax.set_xticks(range(24))
ax.set_xlabel('시간')
ax.set_ylabel('활성 사용자 수')
ax.set_title('시간대별 활성 사용자')
ax.grid(alpha=0.3)
plt.tight_layout(); plt.show()

# 3. 사용자별 쿼리 수 분포 (로그)
fig, ax = plt.subplots(figsize=(10, 4.5))
bins = np.logspace(0, np.log10(user_counts.max()), 30)
ax.hist(user_counts.values, bins=bins, edgecolor='white')
ax.set_xscale('log')
ax.set_xlabel('쿼리 수 (로그 스케일)')
ax.set_ylabel('사용자 수')
ax.set_title('사용자별 쿼리 수 분포')
for x, label in [(10, '일회성'), (100, '캐주얼'), (1000, '액티브')]:
    ax.axvline(x, color='gray', linestyle='--', alpha=0.5)
    ax.text(x, ax.get_ylim()[1]*0.92, label, ha='right', fontsize=9, alpha=0.7)
plt.tight_layout(); plt.show()
