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

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

hour_series = pd.to_datetime(final_query_df['execution_time']).dt.hour
hourly = final_query_df.groupby(hour_series)['username'].nunique().reindex(range(24), fill_value=0)

# 24시간을 각도로 (0시 = 12시 방향, 시계방향)
angles = np.linspace(0, 2*np.pi, 24, endpoint=False)
peak_h = hourly.idxmax()

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'projection': 'polar'})

# 피크는 진한 색, 나머지는 연한 색
colors = ['#2E5BFF' if h == peak_h else '#B8C3D9' for h in range(24)]

bars = ax.bar(angles, hourly.values, width=2*np.pi/24*0.9,
              color=colors, edgecolor='white', linewidth=1.5)

# 시계 방향, 12시(=0시) 위로
ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)

# 시간 라벨
ax.set_xticks(angles)
ax.set_xticklabels([f'{h}시' for h in range(24)], fontsize=10)

# 반지름축 정리
ax.set_yticklabels([])
ax.grid(alpha=0.3)

ax.set_title(f'시간대별 활성 사용자  ·  피크 {peak_h}시 ({hourly[peak_h]:,}명)',
             fontsize=13, fontweight='bold', pad=25, loc='center')

plt.tight_layout(); plt.show()
