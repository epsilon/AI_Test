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
