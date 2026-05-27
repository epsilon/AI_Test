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

# 확인 프로그램
from collections import Counter

# 1) preqp_mst_pmm을 쓰는 호출의 hourly 분포
# 비즈니스 호출 (캐시 hit 포함) = getEquipmentList 서비스 전체
preqp_sessions = [s for s in sessions 
                  if s['service'] == 'SMARTPMS.PREQUIPMENT#getEquipmentList']

hourly_business = Counter()
for s in preqp_sessions:
    hour = int(s['start_ts'][11:13])  # 'YYYY-MM-DD HH:MM:SS,mmm'에서 HH
    hourly_business[hour] += 1

# 2) DB 호출만 (cache miss + SQL 발생한 것)
preqp_db_sessions = [s for s in preqp_sessions 
                     if any('LoggingPlugin#logStatement' in r['logger'] 
                            for r in s['records'])]
hourly_db = Counter()
for s in preqp_db_sessions:
    hour = int(s['start_ts'][11:13])
    hourly_db[hour] += 1

# 3) 출력 — 24시간 분포
print('hour | business | db | cache_hit_rate')
for h in range(24):
    b = hourly_business.get(h, 0)
    d = hourly_db.get(h, 0)
    rate = f'{1-d/b:.0%}' if b > 0 else '-'
    print(f'  {h:2d} | {b:7d}  | {d:4d} | {rate}')

# source dataframe 만들기
import re
import pandas as pd

CLIENT_RE = re.compile(r'CLIENT=([\d.]+):(\d+)')
PREFIX_RE = re.compile(r'^\s*\[([^\]]+)\]\s*(.*)', re.DOTALL)

def session_to_row(s):
    head = s['records'][0]
    m = CLIENT_RE.search(head['message'])
    ip, port = (m.group(1), m.group(2)) if m else (None, None)

    # 캐시 상태 (MonitoringCache#get 한 줄만 보고 판정)
    cache = None
    for r in s['records']:
        if 'MonitoringCache#get' in r['logger']:
            msg = r['message']
            cache = 'miss' if ('Noot' in msg or 'Not Exist' in msg) else 'hit'
            break

    # 한 세션의 모든 SQL과 datasource
    datasources, sqls = [], []
    for r in s['records']:
        if 'LoggingPlugin#logStatement' in r['logger']:
            pm = PREFIX_RE.match(r['message'])
            if pm:
                datasources.append(pm.group(1))
                sqls.append(pm.group(2).strip())
            else:
                datasources.append(None)
                sqls.append(r['message'].strip())

    return {
        'ip': ip,
        'port': port,
        'function': s['service'],
        'start_ts': head['ts'],
        'end_ts': s['records'][-1]['ts'],
        'thread': s['thread'],
        'guid': s['guid'],
        'cache': cache,
        'n_sqls': len(sqls),
        'datasources': datasources,
        'sqls': sqls,
    }

df = pd.DataFrame([session_to_row(s) for s in sessions])
df['start_ts'] = pd.to_datetime(df['start_ts'], format='%Y-%m-%d %H:%M:%S,%f')
df['end_ts']   = pd.to_datetime(df['end_ts'],   format='%Y-%m-%d %H:%M:%S,%f')
df['duration_ms'] = (df['end_ts'] - df['start_ts']).dt.total_seconds() * 1000

df = df.sort_values('start_ts').reset_index(drop=True)
print(df.shape)
df.head()

# 확인하기
print('고유 IP:', df['ip'].nunique())
print('고유 IP:Port:', df.groupby(['ip','port']).ngroups)
print('함수당 호출 분포:')
print(df['function'].value_counts().head(10))

# 분석 포인트
# 1) 한 사람(ip:port)의 시간순 행동
df[(df['ip']=='10.145.77.61') & (df['port']=='10144')] \
    .sort_values('start_ts') \
    [['start_ts','function','cache','duration_ms','n_sqls']]

# 2) 각 사람이 마지막으로 멈춘 지점
df.sort_values('start_ts').groupby(['ip','port']).tail(1) \
    [['ip','port','function','start_ts','cache']]

# 3) 한 사람이 한 SQL 다 펼치기
sample = df[df['ip']=='10.145.77.61'].iloc[0]
for ds, sql in zip(sample['datasources'], sample['sqls']):
    print(f'[{ds}] {sql[:200]}')

# 시간 내용 추가
import re

CACHE_RE = re.compile(r'(.+?) is (Noot Exist|Not Exist|Exist) in Cache')

def session_to_row(s):
    head = s['records'][0]
    m = CLIENT_RE.search(head['message'])
    ip, port = (m.group(1), m.group(2)) if m else (None, None)

    cache, cache_key = None, None
    for r in s['records']:
        if 'MonitoringCache#get' in r['logger']:
            cm = CACHE_RE.search(r['message'])
            if cm:
                cache_key = cm.group(1).strip()
                cache = 'hit' if cm.group(2) == 'Exist' else 'miss'
            break

    datasources, sqls = [], []
    for r in s['records']:
        if 'LoggingPlugin#logStatement' in r['logger']:
            pm = PREFIX_RE.match(r['message'])
            if pm:
                datasources.append(pm.group(1))
                sqls.append(pm.group(2).strip())
            else:
                datasources.append(None)
                sqls.append(r['message'].strip())

    return {
        'ip': ip, 'port': port,
        'function': s['service'],
        'start_ts': head['ts'], 'end_ts': s['records'][-1]['ts'],
        'thread': s['thread'], 'guid': s['guid'],
        'cache': cache, 'cache_key': cache_key,
        'n_sqls': len(sqls),
        'datasources': datasources, 'sqls': sqls,
    }

df = pd.DataFrame([session_to_row(s) for s in sessions])
df['start_ts'] = pd.to_datetime(df['start_ts'], format='%Y-%m-%d %H:%M:%S,%f')
df['end_ts']   = pd.to_datetime(df['end_ts'],   format='%Y-%m-%d %H:%M:%S,%f')
df['duration_ms'] = (df['end_ts'] - df['start_ts']).dt.total_seconds() * 1000
df = df.sort_values('start_ts').reset_index(drop=True)

# table column 추가
import sqlglot
from sqlglot import exp

def _extract(sql):
    try:
        return list({t.name.lower() for t in sqlglot.parse_one(sql, dialect='oracle').find_all(exp.Table)})
    except Exception:
        return []

df['tables'] = df['sqls'].apply(
    lambda sqls: list({t for sql in (sqls or []) for t in _extract(sql)})
)

# 계정 열결 가능 여부 확인
import re
import pandas as pd

# 1) user_id 추출 (= 'x' 형태 + IN (...) 형태)
USER_ID_EQ = re.compile(r"user_id\s*=\s*'([^']+)'", re.IGNORECASE)
USER_ID_IN = re.compile(r"user_id\s+in\s*\(([^)]+)\)", re.IGNORECASE)

def extract_user_ids(sqls):
    found = set()
    for sql in (sqls or []):
        for m in USER_ID_EQ.finditer(sql):
            found.add(m.group(1))
        for m in USER_ID_IN.finditer(sql):
            for v in m.group(1).split(','):
                v = v.strip().strip("'\"")
                if v: found.add(v)
    return sorted(found)

# 2) 두 가지 user_id 컬럼
df['user_ids_all'] = df['sqls'].apply(extract_user_ids)
df['is_login'] = df['function'].fillna('').str.lower().str.contains('login|sso')
df['user_ids_login'] = df.apply(
    lambda r: r['user_ids_all'] if r['is_login'] else [], axis=1
)

# 3) 세션 (ip, port) 단위 집계
sess = df.groupby(['ip', 'port']).agg(
    n_calls=('function', 'size'),
    user_ids_all=('user_ids_all', lambda L: sorted({u for l in L for u in l})),
    user_ids_login=('user_ids_login', lambda L: sorted({u for l in L for u in l})),
    has_login=('is_login', 'any'),
).reset_index()
sess['n_users_all'] = sess['user_ids_all'].apply(len)
sess['n_users_login'] = sess['user_ids_login'].apply(len)

# 4) 리포트
total = len(sess)
print(f'총 세션 (ip,port): {total:,}')
print(f'login function 호출이 있는 세션: {sess["has_login"].sum():,} ({sess["has_login"].mean()*100:.1f}%)')
print()
print('--- 관대 (모든 SQL의 user_id) ---')
mapped_all = (sess['n_users_all'] > 0).sum()
print(f'매핑된 세션: {mapped_all:,} ({mapped_all/total*100:.1f}%)')
print(f'매핑 안 된 세션: {total - mapped_all:,}')
print('세션당 user_id 수 분포:')
print(sess['n_users_all'].value_counts().sort_index().head(10))
print()
print('--- 엄격 (login function의 user_id) ---')
mapped_login = (sess['n_users_login'] > 0).sum()
print(f'매핑된 세션: {mapped_login:,} ({mapped_login/total*100:.1f}%)')
print(f'매핑 안 된 세션: {total - mapped_login:,}')
print('세션당 user_id 수 분포:')
print(sess['n_users_login'].value_counts().sort_index().head(10))

# user mapping 추가
import re

USER_ID_EQ = re.compile(r"user_id\s*=\s*'([^']+)'", re.IGNORECASE)
USER_ID_IN = re.compile(r"user_id\s+in\s*\(([^)]+)\)", re.IGNORECASE)

def extract_login_user(row):
    fn = (row['function'] or '').lower()
    if 'login' not in fn and 'sso' not in fn:
        return None
    for sql in (row['sqls'] or []):
        m = USER_ID_EQ.search(sql)
        if m: return m.group(1)
        m = USER_ID_IN.search(sql)
        if m:
            vals = [v.strip().strip("'\"") for v in m.group(1).split(',')]
            if vals: return vals[0]
    return None

df['login_user_id'] = df.apply(extract_login_user, axis=1)

# 세션 (ip, port) 단위로 전파
session_user = df.dropna(subset=['login_user_id']).groupby(['ip','port'])['login_user_id'].first().to_dict()
df['session_user_id'] = df.apply(lambda r: session_user.get((r['ip'], r['port'])), axis=1)

print(f"매핑된 calls: {df['session_user_id'].notna().sum():,} / {len(df):,}")
print(f"고유 user: {df['session_user_id'].nunique()}")

# union 추가
def _union_one(sql):
    pairs = set()
    try: parsed = sqlglot.parse_one(sql, dialect='oracle')
    except: return list(pairs)
    for u in parsed.find_all(exp.Union):
        left = u.left
        right = u.right
        lt = {(t.name or '').lower() for t in (left.find_all(exp.Table) if left else [])}
        rt = {(t.name or '').lower() for t in (right.find_all(exp.Table) if right else [])}
        for a in lt:
            for b in rt:
                if a and b and a != b:
                    pairs.add(tuple(sorted([a, b])))
    return [list(p) for p in pairs]

df['union_pairs'] = df['sqls'].apply(lambda sqls: [p for s in (sqls or []) for p in _union_one(s)])
print(f"union 추출된 call: {(df['union_pairs'].str.len() > 0).sum():,}")

# join 점검
# 1) 전체 통계
total_calls = len(df)
calls_with_joins = (df['join_pairs'].str.len() > 0).sum()
print(f"join_pairs 있는 call: {calls_with_joins:,} / {total_calls:,} ({calls_with_joins/total_calls*100:.1f}%)")

# 2) 샘플 — 어떻게 추출됐는지
sample = df[df['join_pairs'].str.len() > 0].head(5)
for _, row in sample.iterrows():
    print(f"\nfunction: {row['function']}")
    print(f"tables: {row['tables']}")
    print(f"join_pairs: {row['join_pairs']}")
    print(f"sqls[0]: {(row['sqls'] or [''])[0][:300]}")
    print("---")

# 3) 매칭 검증 — join_pairs의 table이 같은 call의 tables에 실제로 있는지
matched = 0
unmatched_examples = []
total_pairs = 0
for _, row in df.iterrows():
    tables_set = set(row['tables'] or [])
    for pair in (row['join_pairs'] or []):
        total_pairs += 1
        ta, ka, tb, kb = pair
        if ta in tables_set and tb in tables_set:
            matched += 1
        elif len(unmatched_examples) < 5:
            unmatched_examples.append({
                'function': row['function'],
                'tables': list(tables_set),
                'pair': pair,
            })
print(f"\njoin_pairs 매칭률: {matched}/{total_pairs} ({matched/max(total_pairs,1)*100:.1f}%)")
if unmatched_examples:
    print("\n매칭 실패 샘플:")
    for ex in unmatched_examples:
        print(f"  {ex}")
