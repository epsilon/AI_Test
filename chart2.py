import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# ── 분류 함수 (앞에 만든 거 그대로) ──
def classify_shape(values):
    total = values.sum()
    if total == 0:
        return {'shape': '데이터 없음', 'business_share': 0, 'night_share': 0,
                'gini': 0, 'n_peaks': 0, 'peak_hours': [], 'peak_ratio': 0}
    
    p = values / total
    night_share    = p[0:6].sum()
    business_share = p[9:18].sum()
    evening_share  = p[18:24].sum()
    
    sorted_p = np.sort(p)
    cum = np.cumsum(sorted_p)
    gini = 1 - 2 * np.trapz(cum, dx=1/24)
    
    peaks, _ = find_peaks(values, height=values.mean()*1.3, distance=2)
    n_peaks = len(peaks)
    peak_ratio = values.max() / values.mean() if values.mean() > 0 else 0
    
    if gini < 0.15:
        shape = '24시간 평탄형'
    elif business_share >= 0.75 and night_share < 0.10:
        shape = '업무시간형'
    elif night_share + evening_share*0.5 >= 0.50:
        shape = '야간 집중형'
    elif n_peaks >= 2:
        shape = '쌍봉형'
    elif peak_ratio >= 4.0:
        shape = '단일 피크형'
    elif business_share >= 0.55:
        shape = '업무시간 중심+일부 야간'
    else:
        shape = '혼합형'
    
    return {
        'shape': shape,
        'business_share': business_share,
        'night_share': night_share,
        'gini': gini,
        'n_peaks': n_peaks,
        'peak_hours': peaks.tolist(),
        'peak_ratio': peak_ratio,
    }

# ── 계정별 분류 ──
MIN_QUERIES = 50  # 임계값 — 50개 미만은 제외

final_query_df['_hour'] = pd.to_datetime(final_query_df['execute_time']).dt.hour

user_counts = final_query_df['username'].value_counts()
target_users = user_counts[user_counts >= MIN_QUERIES].index

# 사용자 × 시간 피벗 (행=사용자, 열=0~23시, 값=쿼리수)
pivot = (final_query_df[final_query_df['username'].isin(target_users)]
         .groupby(['username', '_hour']).size()
         .unstack(fill_value=0)
         .reindex(columns=range(24), fill_value=0))

# 각 행에 분류 적용
results = []
for user, row in pivot.iterrows():
    r = classify_shape(row.values)
    r['username'] = user
    r['total_queries'] = int(row.sum())
    results.append(r)

result_df = pd.DataFrame(results)[
    ['username', 'total_queries', 'shape', 'business_share',
     'night_share', 'gini', 'n_peaks', 'peak_hours', 'peak_ratio']
].sort_values('total_queries', ascending=False)

# 1. 분포 모양별 인원수
print('═══ 모양별 사용자 수 ═══')
print(result_df['shape'].value_counts())
print()

# 2. 모양별 쿼리 수 합계 — 임팩트 측면
print('═══ 모양별 쿼리 비중 ═══')
impact = result_df.groupby('shape')['total_queries'].agg(['count', 'sum'])
impact['query_share'] = (impact['sum'] / impact['sum'].sum() * 100).round(1)
print(impact.sort_values('sum', ascending=False))
print()

# 3. 상위 사용자 분류 결과 보기
print('═══ Top 20 사용자 분류 ═══')
print(result_df.head(20)[['username', 'total_queries', 'shape',
                          'business_share', 'night_share', 'peak_hours']]
      .to_string(index=False))


import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# 분류별 색
SHAPE_COLORS = {
    '업무시간형':            '#2E5BFF',
    '업무시간 중심+일부 야간': '#5B8DEF',
    '야간 집중형':           '#FF6B35',
    '24시간 평탄형':         '#9B59B6',
    '쌍봉형':               '#16A085',
    '단일 피크형':           '#E67E22',
    '혼합형':               '#95A5A6',
    '데이터 없음':           '#D0D5DD',
}

# result_df 순서(쿼리 많은 순)대로 그림
order = result_df['username'].tolist()
shape_map = dict(zip(result_df['username'], result_df['shape']))
total_map = dict(zip(result_df['username'], result_df['total_queries']))

NCOLS = 4
PER_PAGE = 28               # 페이지당 7행 x 4열
n = len(order)
n_pages = int(np.ceil(n / PER_PAGE))

print(f'총 {n}명 · {n_pages}페이지로 출력')

for page in range(n_pages):
    chunk = order[page*PER_PAGE : (page+1)*PER_PAGE]
    nrows = int(np.ceil(len(chunk) / NCOLS))

    fig, axes = plt.subplots(nrows, NCOLS,
                             figsize=(NCOLS*4, nrows*2.6),
                             squeeze=False)

    for idx, user in enumerate(chunk):
        ax = axes[idx // NCOLS][idx % NCOLS]
        vals = pivot.loc[user].reindex(range(24), fill_value=0).values
        shape = shape_map[user]
        color = SHAPE_COLORS.get(shape, '#95A5A6')

        ax.bar(range(24), vals, color=color, width=0.85)

        # 피크 시간 점선
        peak_h = int(np.argmax(vals))
        ax.axvline(peak_h, color=color, linestyle='--', alpha=0.4, linewidth=1)

        ax.set_title(f'{user}\n{shape} · {total_map[user]:,}건 · 피크 {peak_h}시',
                     fontsize=9, fontweight='bold', pad=6)
        ax.set_xlim(-0.5, 23.5)
        ax.set_xticks([0, 6, 12, 18])
        ax.set_xticklabels(['0', '6', '12', '18'], fontsize=7)
        ax.tick_params(axis='y', labelsize=7)
        for s in ['top', 'right']:
            ax.spines[s].set_visible(False)

    # 남는 칸 숨기기
    for j in range(len(chunk), nrows*NCOLS):
        axes[j // NCOLS][j % NCOLS].axis('off')

    # 범례 (페이지마다 상단)
    handles = [plt.Rectangle((0,0),1,1, color=c) for c in SHAPE_COLORS.values()]
    fig.legend(handles, SHAPE_COLORS.keys(), loc='upper center',
               ncol=len(SHAPE_COLORS), frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 1.0))

    fig.suptitle(f'계정별 시간대 분포  ·  {page+1}/{n_pages} 페이지',
                 fontsize=13, fontweight='bold', y=1.0, x=0.02, ha='left')
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()

