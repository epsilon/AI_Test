# 공통 파서
import re
from collections import Counter, defaultdict
import pandas as pd

LOG_LINE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+'
    r'\[(?P<level>\w+)\s*\]\s+'
    r'\((?P<thread>[^)]+)\)\s+'
    r'(?P<logger>\S+)\s+-\s+'
    r'(?P<message>.*)$'
)

def parse_log(path, encoding='utf-8'):
    """라인 파싱 + 다음 timestamp 전까지 continuation 합침."""
    with open(path, encoding=encoding, errors='replace') as f:
        current = None
        for line in f:
            line = line.rstrip('\n')
            m = LOG_LINE.match(line)
            if m:
                if current:
                    yield current
                current = m.groupdict()
            elif current:
                current['message'] += '\n' + line
        if current:
            yield current

# 어휘 사전
def build_vocabulary(path, n_samples=3):
    counter = Counter()
    samples = defaultdict(list)
    for rec in parse_log(path):
        key = rec['logger']
        counter[key] += 1
        if len(samples[key]) < n_samples:
            samples[key].append(rec['message'][:300])
    rows = [
        {'logger': k, 'count': c, 'samples': samples[k]}
        for k, c in counter.most_common()
    ]
    return pd.DataFrame(rows)

vocab = build_vocabulary('your_log_path.log')
vocab  # 등장 빈도 내림차순으로 logger#method 전체 종류 + 샘플

# session grouping
GUID_RE = re.compile(r'GUID=([a-f0-9-]+)', re.IGNORECASE)
SERVICE_RE = re.compile(r'SERVICE[-=]([^\s]+)')

def group_sessions(path):
    open_sessions = {}
    completed = []
    for rec in parse_log(path):
        thread = rec['thread']
        if 'TcpWorker#run' in rec['logger']:
            if thread in open_sessions:
                completed.append(open_sessions[thread])
            g = GUID_RE.search(rec['message'])
            s = SERVICE_RE.search(rec['message'])
            open_sessions[thread] = {
                'thread': thread,
                'guid': g.group(1) if g else None,
                'service': s.group(1) if s else None,
                'start_ts': rec['ts'],
                'records': [rec],
            }
        elif thread in open_sessions:
            open_sessions[thread]['records'].append(rec)
    completed.extend(open_sessions.values())
    return completed

sessions = group_sessions('your_log_path.log')
print(f'{len(sessions)} sessions')
sessions[0]  # 한 세션 살펴보기

# 1) 어휘 79종 CSV 저장 (samples는 길어서 따로 빼고)
vocab[['logger', 'count']].to_csv('vocab.csv', index=False)

# 2) 세션 요약 DataFrame
sess_df = pd.DataFrame([
    {
        'guid': s['guid'],
        'service': s['service'],
        'n_records': len(s['records']),
        'thread': s['thread'],
        'start_ts': s['start_ts'],
    }
    for s in sessions
])
sess_df.to_csv('sessions_summary.csv', index=False)

# 3) 화면 확인
print('=== 서비스별 호출 수 top 20 ===')
print(sess_df['service'].value_counts(dropna=False).head(20))

print('\n=== 세션당 라인 수 분포 ===')
print(sess_df['n_records'].describe())

print('\n=== GUID/service 누락 세션 ===')
print('guid 없음:', sess_df['guid'].isna().sum())
print('service 없음:', sess_df['service'].isna().sum())
