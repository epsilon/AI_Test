import pandas as pd
from collections import Counter

def table_signature(tables):
    """[(cat, db, tbl), ...] → 'db.tbl|db.tbl' 형태의 정렬된 시그니처."""
    if not isinstance(tables, list) or not tables:
        return None
    parts = sorted(f"{db or ''}.{tbl}" for _, db, tbl in tables)
    return '|'.join(parts)


def _ngrams(seq, n):
    return [tuple(seq[i:i+n]) for i in range(len(seq) - n + 1)]


def analyze_sequences(df,
                      user_col='account_id',
                      ts_col='start_time',
                      tables_col='tables',
                      gap_minutes=30,
                      ngram_range=(2, 3, 4),
                      min_count=5,
                      collapse_repeats=True):
    """
    질의 로그의 앞뒤 연관성 분석.

    Returns
    -------
    {
      'sessions':    DataFrame  -- 원본 + session_id, seq_no, tbl_sig
      'transitions': DataFrame  -- (prev, next, count) 2-gram 전이표
      'ngrams':      dict[int -> DataFrame]  -- n별 패턴 카운트 (count >= min_count)
      'stats':       dict       -- 세션 수, 평균 길이 등 요약
    }
    """
    # 1) 세션화
    d = df.dropna(subset=[user_col, ts_col, tables_col]).copy()
    d[ts_col] = pd.to_datetime(d[ts_col])
    d = d.sort_values([user_col, ts_col]).reset_index(drop=True)

    gap = d.groupby(user_col)[ts_col].diff()
    new_session = gap.isna() | (gap > pd.Timedelta(minutes=gap_minutes))
    d['session_id'] = new_session.groupby(d[user_col]).cumsum()
    d['seq_no'] = d.groupby([user_col, 'session_id']).cumcount() + 1

    # 2) 테이블 시그니처
    d['tbl_sig'] = d[tables_col].map(table_signature)
    d = d.dropna(subset=['tbl_sig'])

    # 3) 2-gram 전이표
    d['prev_sig'] = d.groupby([user_col, 'session_id'])['tbl_sig'].shift()
    trans = d.dropna(subset=['prev_sig'])
    if collapse_repeats:
        trans = trans[trans['prev_sig'] != trans['tbl_sig']]
    transitions = (
        trans.groupby(['prev_sig', 'tbl_sig']).size()
             .reset_index(name='count')
             .sort_values('count', ascending=False)
             .reset_index(drop=True)
    )

    # 4) n-gram 패턴
    session_seqs = (
        d.groupby([user_col, 'session_id'])['tbl_sig']
         .apply(list)
    )
    if collapse_repeats:
        session_seqs = session_seqs.map(
            lambda s: [x for i, x in enumerate(s) if i == 0 or x != s[i-1]]
        )

    ngrams_out = {}
    for n in ngram_range:
        c = Counter()
        for seq in session_seqs:
            c.update(_ngrams(seq, n))
        rows = [(' → '.join(k), k, v) for k, v in c.items() if v >= min_count]
        ngrams_out[n] = (
            pd.DataFrame(rows, columns=['pattern', 'tuple', 'count'])
              .sort_values('count', ascending=False)
              .reset_index(drop=True)
        )

    # 5) 요약 통계
    stats = {
        'queries':           len(d),
        'users':             d[user_col].nunique(),
        'sessions':          d.groupby([user_col, 'session_id']).ngroups,
        'avg_session_len':   session_seqs.map(len).mean(),
        'median_session_len':session_seqs.map(len).median(),
        'unique_signatures': d['tbl_sig'].nunique(),
    }

    return {
        'sessions': d,
        'transitions': transitions,
        'ngrams': ngrams_out,
        'stats': stats,
    }

#usage
result = analyze_sequences(spark_df)   # 컬럼명 다르면 user_col/ts_col/tables_col 지정

print(result['stats'])

# 가장 흔한 직후 이동 Top 20
result['transitions'].head(20)

# 길이별 패턴
result['ngrams'][2].head(10)
result['ngrams'][3].head(10)
result['ngrams'][4].head(10)
