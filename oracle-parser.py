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

# A) 1위 서비스 확인 + logger 시퀀스 템플릿 추출
top_service = sess_df['service'].value_counts().index[0]
print('TOP:', top_service)

def session_signature(s):
    # logger 시퀀스를 튜플로 — 같은 시퀀스면 같은 템플릿
    return tuple(r['logger'] for r in s['records'])

sig_counter = Counter(session_signature(s) for s in sessions)
print(f'\n총 {len(sig_counter)}개 템플릿')
for sig, cnt in sig_counter.most_common(10):
    print(f'\n[{cnt}회] {len(sig)}라인')
    for logger in sig:
        print(f'  {logger}')

# B) outlier 세션 직접 보기
short = [s for s in sessions if len(s['records']) == 1]
long = [s for s in sessions if len(s['records']) >= 20]
print(f'1라인 세션 {len(short)}개, 20+라인 세션 {len(long)}개')

# 1라인짜리 샘플
for s in short[:3]:
    print(s['service'], '|', s['records'][0]['logger'], '|', s['records'][0]['message'][:200])

# 가장 긴 세션 logger 시퀀스
longest = max(sessions, key=lambda s: len(s['records']))
print('\n가장 긴 세션:', longest['service'])
for r in longest['records']:
    print(' ', r['logger'])

with open('top10_templates.txt', 'w', encoding='utf-8') as f:
    for i, (sig, cnt) in enumerate(sig_counter.most_common(10), 1):
        f.write(f'\n=== #{i} [{cnt}회, {len(sig)}라인] ===\n')
        for logger in sig:
            f.write(f'  {logger}\n')


# SQL 발생 세션만 추출 → (service, sql) pair
sql_records = []
for s in sessions:
    sqls = [r['message'] for r in s['records'] 
            if 'LoggingPlugin#logStatement' in r['logger']]
    for sql in sqls:
        sql_records.append({
            'guid': s['guid'],
            'service': s['service'],
            'sql': sql,
        })

print(len(sql_records), '개 SQL 추출')
pd.DataFrame(sql_records).to_csv('service_sql_pairs.csv', index=False)

# 5/25 parsing 성공율
import sqlglot
from sqlglot import exp

def extract_tables(sql):
    try:
        parsed = sqlglot.parse_one(sql, dialect='oracle')
        return list({t.name for t in parsed.find_all(exp.Table)})
    except Exception:
        return None  # 파싱 실패는 따로 카운트

# sql_records: 셀에서 만들었던 12,099개 list
import pandas as pd
df = pd.DataFrame(sql_records)
df['tables'] = df['sql'].apply(extract_tables)

print('파싱 실패:', df['tables'].isna().sum())
print('테이블 추출 예시:')
print(df[['service', 'tables']].head(10))

# prefix 제거
import re

def split_sql(msg):
    m = re.match(r'\s*\[([^\]]+)\]\s*(.*)', msg, re.DOTALL)
    if m:
        return m.group(1), m.group(2).strip()
    return None, msg.strip()

df[['datasource', 'sql_clean']] = df['sql'].apply(
    lambda x: pd.Series(split_sql(x))
)

# datasource 분포 확인
print(df['datasource'].value_counts(dropna=False))

# 속성 파악
sql_records_v2 = []
for s in sessions:
    for r in s['records']:
        if 'LoggingPlugin#logStatement' in r['logger']:
            ds, sql = split_sql(r['message'])
            sql_records_v2.append({
                'guid': s['guid'],
                'service': s['service'],
                'datasource': ds,
                'sql': sql,
            })

# prefix를 섞어서 사용하는지 여부 파악
df.groupby('service')['datasource'].value_counts().head(20)

# 모델 다시 확인
def extract_tables(sql):
    try:
        parsed = sqlglot.parse_one(sql, dialect='oracle')
        return list({t.name for t in parsed.find_all(exp.Table)})
    except Exception:
        return None

df['tables'] = df['sql_clean'].apply(extract_tables)
print('파싱 실패:', df['tables'].isna().sum(), '/', len(df))
print(df[['service', 'datasource', 'tables']].head(10))

#service entity 만들기
from collections import defaultdict, Counter

# 1) 파싱 성공만
ok = df.dropna(subset=['tables']).copy()
ok['tables'] = ok['tables'].apply(lambda x: [t.lower() for t in x])  # 정규화

# 2) 서비스 단위 집계 — business_calls는 session 기반, db_calls는 SQL 발생 기반
# session 기반 카운트 (캐시 hit 포함)
service_business = Counter(s['service'] for s in sessions)
# SQL 발생 카운트 (DB까지 내려온 호출)
service_db = ok.groupby('service').size()

# 3) (service, datasource, table) 호출 수
# 한 SQL row의 tables 리스트 explode → 각 테이블에 1씩 attribute (Equal attribution)
exploded = ok.explode('tables').rename(columns={'tables': 'table'})
service_table_calls = (
    exploded.groupby(['service', 'datasource', 'table'])
    .size()
    .reset_index(name='calls')
)

# 4) service entity 빌드
services = {}
for svc, group in service_table_calls.groupby('service'):
    biz = service_business.get(svc, 0)
    db = int(service_db.get(svc, 0))
    services[svc] = {
        '_source': 'smartpms_log',
        '_inferred': True,
        'business_calls': biz,
        'db_calls': db,
        'cache_hit_rate': round(1 - db / biz, 3) if biz > 0 else None,
        'tables_used': group[['datasource', 'table', 'calls']].to_dict('records'),
    }

# 5) table entity 빌드 (usage 블록)
tables = defaultdict(lambda: {'db_calls': 0, 'used_by_services': []})
for _, row in service_table_calls.iterrows():
    key = (row['datasource'], row['table'])
    tables[key]['db_calls'] += row['calls']
    tables[key]['used_by_services'].append({
        'service': row['service'],
        'calls': int(row['calls']),
    })

# 6) 검증용 출력
print('서비스 entity:', len(services))
print('테이블 entity:', len(tables))
print('\n=== top 서비스 ===')
for svc, info in sorted(services.items(), key=lambda x: -x[1]['business_calls'])[:5]:
    print(f"{svc}: biz={info['business_calls']}, db={info['db_calls']}, cache={info['cache_hit_rate']}")
print('\n=== top 테이블 (db_calls 기준) ===')
for (ds, t), info in sorted(tables.items(), key=lambda x: -x[1]['db_calls'])[:10]:
    print(f"{ds}.{t}: {info['db_calls']} calls from {len(info['used_by_services'])} services")
