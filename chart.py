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

hour_series = pd.to_datetime(final_query_df['execute_time']).dt.hour

# 두 가지 집계
users_per_hour = final_query_df.groupby(hour_series)['username'].nunique().reindex(range(24), fill_value=0)
queries_per_hour = final_query_df.groupby(hour_series).size().reindex(range(24), fill_value=0)

angles = np.linspace(0, 2*np.pi, 24, endpoint=False)

def draw_polar(ax, series, title, accent='#2E5BFF'):
    peak_h = series.idxmax()
    colors = [accent if h == peak_h else '#B8C3D9' for h in range(24)]
    ax.bar(angles, series.values, width=2*np.pi/24*0.9,
           color=colors, edgecolor='white', linewidth=1.5)

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels([f'{h}시' for h in range(24)], fontsize=9)
    ax.set_yticklabels([])
    ax.grid(alpha=0.3)
    ax.set_ylim(0, series.max() * 1.22)

    offset = series.max() * 0.08
    for angle, val, h in zip(angles, series.values, range(24)):
        if val == 0:
            continue
        ax.text(angle, val + offset, f'{val:,}',
                ha='center', va='center', fontsize=8,
                fontweight='bold' if h == peak_h else 'normal',
                color=accent if h == peak_h else '#2A2F45')

    ax.set_title(f'{title}\n피크 {peak_h}시 · {series[peak_h]:,}',
                 fontsize=12, fontweight='bold', pad=20)

fig, axes = plt.subplots(1, 2, figsize=(16, 8), subplot_kw={'projection': 'polar'})
draw_polar(axes[0], users_per_hour,   '시간대별 활성 사용자', accent='#2E5BFF')
draw_polar(axes[1], queries_per_hour, '시간대별 쿼리 수',    accent='#FF6B35')

plt.tight_layout(); plt.show()

# dual y chart
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

hour_series = pd.to_datetime(final_query_df['execute_time']).dt.hour
users_per_hour   = final_query_df.groupby(hour_series)['username'].nunique().reindex(range(24), fill_value=0)
queries_per_hour = final_query_df.groupby(hour_series).size().reindex(range(24), fill_value=0)

USER_COLOR  = '#2E5BFF'
QUERY_COLOR = '#FF6B35'

fig, ax1 = plt.subplots(figsize=(13, 5.5))

# 왼쪽 Y축 — 활성 사용자
l1 = ax1.plot(users_per_hour.index, users_per_hour.values,
              color=USER_COLOR, linewidth=2.4, marker='o', markersize=6,
              markerfacecolor='white', markeredgewidth=1.8,
              label='활성 사용자 수')
ax1.set_xlabel('시간', fontsize=11)
ax1.set_ylabel('활성 사용자 수', color=USER_COLOR, fontsize=11)
ax1.tick_params(axis='y', labelcolor=USER_COLOR)
ax1.set_xticks(range(24))
ax1.set_xlim(-0.5, 23.5)
ax1.set_ylim(0, users_per_hour.max() * 1.20)
ax1.grid(axis='y', alpha=0.25, linestyle='--')
ax1.set_axisbelow(True)

# 사용자 값 라벨
for h, v in users_per_hour.items():
    if v > 0:
        ax1.text(h, v + users_per_hour.max()*0.03, f'{v:,}',
                 ha='center', fontsize=8, color=USER_COLOR)

# 오른쪽 Y축 — 쿼리 수
ax2 = ax1.twinx()
l2 = ax2.plot(queries_per_hour.index, queries_per_hour.values,
              color=QUERY_COLOR, linewidth=2.4, marker='s', markersize=6,
              markerfacecolor='white', markeredgewidth=1.8,
              label='쿼리 수')
ax2.set_ylabel('쿼리 수', color=QUERY_COLOR, fontsize=11)
ax2.tick_params(axis='y', labelcolor=QUERY_COLOR)
ax2.set_ylim(0, queries_per_hour.max() * 1.20)

# 쿼리 값 라벨
for h, v in queries_per_hour.items():
    if v > 0:
        ax2.text(h, v + queries_per_hour.max()*0.03, f'{v:,}',
                 ha='center', fontsize=8, color=QUERY_COLOR)

# 스파인 정리
for s in ['top']:
    ax1.spines[s].set_visible(False)
    ax2.spines[s].set_visible(False)
ax1.spines['left'].set_color(USER_COLOR)
ax2.spines['right'].set_color(QUERY_COLOR)

# 범례 합치기
lines = l1 + l2
ax1.legend(lines, [l.get_label() for l in lines],
           loc='upper left', frameon=False, fontsize=10)

plt.title('시간대별 활성 사용자 & 쿼리 수', fontsize=13, fontweight='bold',
          loc='left', pad=15)
plt.tight_layout(); plt.show()


