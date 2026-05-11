import pandas as pd
import matplotlib.pyplot as plt
import calendar


def plot_query_timetable(df, start_col='start_time', end_col='end_time',
                         year=None, month=None):
    """
    한 달치 query 실행 히트맵.
    세로축: 시간(0~23), 가로축: 일(1~월말).
    셀 값 = 그 시각에 실행 중이던 query 수.
    """
    # 1) 시각 컬럼 정리
    s = pd.to_datetime(df[start_col], errors='coerce')
    e = pd.to_datetime(df[end_col], errors='coerce')
    valid = s.notna() & e.notna() & (e >= s)
    s, e = s[valid], e[valid]

    # 2) 대상 월 자동 결정 (가장 많이 등장한 연·월)
    if year  is None: year  = int(s.dt.year.mode()[0])
    if month is None: month = int(s.dt.month.mode()[0])
    n_days = calendar.monthrange(year, month)[1]

    # 3) 각 query가 걸친 1시간 단위 시각 모두 펼치기
    s_hr = s.dt.floor('h')
    e_hr = e.dt.floor('h')
    hours = pd.Series([pd.date_range(a, b, freq='h') for a, b in zip(s_hr, e_hr)])
    exploded = hours.explode().dropna()

    # 4) 대상 월만 추려서 day × hour 카운트
    m = (exploded.dt.year == year) & (exploded.dt.month == month)
    exploded = exploded[m]

    grid = (
        pd.crosstab(exploded.dt.hour, exploded.dt.day)
          .reindex(index=range(24), columns=range(1, n_days + 1), fill_value=0)
    )

    # 5) plot
    fig, ax = plt.subplots(figsize=(max(8, n_days * 0.45), 7))
    im = ax.imshow(grid.values, aspect='auto', cmap='Blues', origin='upper')
    ax.set_xticks(range(n_days))
    ax.set_xticklabels(range(1, n_days + 1))
    ax.set_yticks(range(24))
    ax.set_yticklabels([f'{h:02d}' for h in range(24)])
    ax.set_xlabel('Day')
    ax.set_ylabel('Hour')
    ax.set_title(f'{year}-{month:02d} Query Execution')
    plt.colorbar(im, ax=ax, label='# queries running')
    plt.tight_layout()
    return fig, grid

# Usage
fig, grid = plot_query_timetable(spark_df,
                                 start_col='start_time',   # 실제 컬럼명으로
                                 end_col='end_time')
plt.show()
