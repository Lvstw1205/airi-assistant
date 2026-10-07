"""Real, persistent text jobs. Shared by AIRI HQ and the local M1 workroom."""
import contextlib,fcntl,json,os,re,secrets,sqlite3,time
from pathlib import Path
DEPARTMENTS=[
 {'id':'planning','name':'기획실','person':'기획 담당','initial':'P','color':'#d2bdff','description':'아이디어를 목표·순서·산출물로 구체화','instruction':'사용자의 목표를 구체적인 기획안으로 작성한다. 대상, 차별점, 순서, 산출물과 확인할 사항을 제시한다.'},
 {'id':'documents','name':'문서실','person':'문서 담당','initial':'D','color':'#9edbc8','description':'붙여넣은 자료 요약·번역·정리','instruction':'제공한 자료만 근거로 요약, 번역 또는 정리한다. 원문에 없는 사실은 추가하지 않는다. 요청한 형식과 언어를 지킨다.'},
 {'id':'research','name':'분석실','person':'분석 담당','initial':'R','color':'#abcafa','description':'자료의 쟁점·근거·반론 분석','instruction':'제공한 자료의 주장, 근거, 반론, 부족한 정보를 구분한다. 실시간 웹 검색 도구는 없다. 최신 정보나 가격을 확인했다고 말하지 않는다.'},
 {'id':'review','name':'검수실','person':'검수 담당','initial':'Q','color':'#efc38f','description':'초안의 논리·누락·표현 검토','instruction':'제공한 초안에서 논리적 문제, 근거 부족, 누락, 표현을 검토하고 수정안을 제시한다. 확인할 수 없는 사실은 불확실하다고 적는다.'},
]
STAFF=[
 {'id':'noa','name':'노아','department':'planning','role':'기획·대본 초안','node':'M1','manual':True},
 {'id':'lumi','name':'루미','department':'documents','role':'요약·번역·편집','node':'M1','manual':True},
 {'id':'leo','name':'레오','department':'research','role':'자료 분석·보고서 초안','node':'M1','manual':True},
 {'id':'ian','name':'이안','department':'research','role':'근거 수집물 정리','node':'M1','manual':True},
 {'id':'moa','name':'모아','department':'review','role':'초안 누락·표현 점검','node':'M1','manual':True},
 {'id':'sera','name':'세라','department':'review','role':'자동 보고서 검수·보강','node':'M6','manual':False},
]
def employee_for(department,employee=None):
 staff=next((e for e in STAFF if e['id']==employee and e['department']==department and e['manual']),None) if employee else next((e for e in STAFF if e['department']==department and e['manual']),None)
 if not staff:raise ValueError('이 업무를 맡길 직원을 선택해 줘.')
 return staff

STATES={'queued':'대기 중','running':'처리 중','completed':'완료','failed':'실패','interrupted':'중단됨','cancelled':'취소됨'}

def department_for(purpose):
 for token,dept in [('검수','review'),('fact_review','review'),('보고서','research'),('분석','research'),('자료','research'),('요약','documents'),('번역','documents'),('문서','documents')]:
  if token in purpose:return dept
 return 'planning'

def messages(department,prompt,node='M1',employee=None):
 d=next((d for d in DEPARTMENTS if d['id']==department),None)
 if not d:raise ValueError('알 수 없는 부서야.')
 person=employee_for(department,employee)
 return [{'role':'system','content':f'너는 User의 개인 비서 AIRI(아이리)의 {node} 작업실 {d["name"]}의 AI 직원 {person["name"]}다. 담당 업무는 {person["role"]}다. AIRI 본부는 새 Mac에서 대화·음성·카메라·무거운 렌더링을 맡고 M1은 백그라운드 텍스트 작업을 맡는다. 이는 실제 모델 작업 역할이며 사람이 아니다. 도구 실행이나 파일 저장을 하지 않았으면 했다고 말하지 않는다. 한국어는 자연스러운 반말로 답하고 다른 언어 요청은 따른다. '+d['instruction']},{'role':'user','content':prompt}]

class Store:
 def __init__(self,folder):
  self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.path=self.folder/'jobs.sqlite3'
  with self.db() as c:
   c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request_key TEXT UNIQUE, department TEXT, source TEXT, mode TEXT, title TEXT, request TEXT, state TEXT, created REAL, started REAL, finished REAL, pid INTEGER, result TEXT, error TEXT, node TEXT)')
   if 'employee' not in {r[1] for r in c.execute('PRAGMA table_info(jobs)')}:c.execute('ALTER TABLE jobs ADD COLUMN employee TEXT')
  self.path.chmod(0o600)
 @contextlib.contextmanager
 def db(self):
  c=sqlite3.connect(self.path,timeout=3);c.row_factory=sqlite3.Row
  try:
   with c:yield c
  finally:c.close()
 def submit(self,prompt,department,model,source='AIRI 본부',request_key=None,request=None,mode='queue',job_id=None,employee=None):
  if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=16000:raise ValueError('작업 내용을 1~16000자로 입력해 줘.')
  if department not in {d['id'] for d in DEPARTMENTS}:raise ValueError('부서를 골라줘.')
  if request_key is not None and (not isinstance(request_key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',request_key)):raise ValueError('잘못된 요청 번호야.')
  if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+~-]{0,255}',model):raise ValueError('잘못된 모델 이름이야.')
  person=employee_for(department,employee)
  identifier=job_id if isinstance(job_id,str) and re.fullmatch(r'[a-f0-9]{24,32}',job_id) else secrets.token_hex(12)
  req=request or {'version':1,'action':'complete','model':model,'messages':messages(department,prompt,employee=person['id']),'max_tokens':1800}
  with self.db() as c:
   old=c.execute('SELECT id FROM jobs WHERE request_key=? OR id=?',(request_key,identifier)).fetchone()
   if old:return self.get(old['id'])
   if c.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]>=20:raise ValueError('대기 중인 작업이 많아. 완료 후 다시 맡겨줘.')
   c.execute('INSERT INTO jobs(id,request_key,department,source,mode,title,request,state,created,started,finished,pid,result,error,node,employee) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,request_key,department,source,mode,prompt[:110],json.dumps(req,ensure_ascii=False),'queued',time.time(),None,None,os.getpid() if mode=='external' else None,'','','M1',person['id']))
  return self.get(identifier)
 def get(self,identifier,internal=False):
  with self.db() as c:row=c.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
  if not row:return None
  data=dict(row);req=json.loads(data.pop('request'));data['model']=req.get('model')
  data['brief']=next((m['content'] for m in reversed(req.get('messages',[])) if m.get('role')=='user'),'') if data['mode']=='queue' else data['title']
  if internal:data['request']=req
  data['seconds']=round((data['finished'] or time.time())-data['started'],2) if data['started'] else None
  return data
 def snapshot(self):
  with self.db() as c:
   ids=[r[0] for r in c.execute("SELECT id FROM jobs ORDER BY CASE WHEN state IN ('running','queued') THEN 0 ELSE 1 END, created DESC LIMIT 60")]
   counts={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM jobs GROUP BY state')}
  jobs=[]
  for identifier in ids:
   row=self.get(identifier)
   for field in ('result','final_text','brief'):row.pop(field,None)
   jobs.append(row)
  return {'jobs':jobs,'counts':counts}
 def next(self):
  with self.db() as c:r=c.execute("SELECT id FROM jobs WHERE state='queued' AND mode='queue' ORDER BY created LIMIT 1").fetchone()
  return r[0] if r else None
 def cancel(self,identifier):
  with self.db() as c:
   if c.execute("UPDATE jobs SET state='cancelled',finished=? WHERE id=? AND state='queued'",(time.time(),identifier)).rowcount!=1:raise ValueError('아직 시작하지 않은 작업만 취소할 수 있어.')
  return self.get(identifier)
 def recover(self):
  # A process death is not a successful result. Never replay an in-flight job.
  with self.db() as c:
   for row in c.execute("SELECT id,pid FROM jobs WHERE state='running' OR (state='queued' AND mode='external')").fetchall():
    try:os.kill(row['pid'],0)
    except ProcessLookupError:c.execute("UPDATE jobs SET state='interrupted',finished=?,error=? WHERE id=?",(time.time(),'실행 프로세스가 종료됐어. 결과를 확인한 뒤 다시 맡겨줘.',row['id']))
    except (PermissionError,TypeError):pass
 def run(self,identifier,executor,timeout=135):
  path=self.folder/'inference.lock'
  with path.open('a') as lock:
   path.chmod(0o600);deadline=time.monotonic()+timeout
   while True:
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
    except BlockingIOError:
     if time.monotonic()>=deadline:
      with self.db() as c:c.execute("UPDATE jobs SET state='failed',error=?,finished=? WHERE id=? AND state='queued'",('실행 순서 대기 시간 초과',time.time(),identifier))
      raise ValueError('M1 작업 대기 시간 초과')
     time.sleep(.1)
   job=self.get(identifier,internal=True)
   if not job:raise ValueError('작업을 찾지 못했어.')
   with self.db() as c:
    claimed=c.execute("UPDATE jobs SET state='running',started=?,pid=? WHERE id=? AND state='queued'",(time.time(),os.getpid(),identifier)).rowcount
   if not claimed:
    if job['state']=='completed':return {'version':1,'text':job['result'],'model':job['model'],'pid':job['pid'],'job_id':identifier}
    raise ValueError('이미 시작했거나 취소한 작업이야.')
   try:
    result=executor(job['request'])
    if not isinstance(result,dict) or not isinstance(result.get('text'),str) or not result['text'].strip() or len(result['text'])>64000 or result.get('model')!=job['model']:raise ValueError('유효한 작업 결과가 없어.')
    with self.db() as c:c.execute("UPDATE jobs SET state='completed',finished=?,result=? WHERE id=?",(time.time(),result['text'],identifier))
    return {**result,'pid':os.getpid(),'job_id':identifier}
   except Exception as e:
    with self.db() as c:c.execute("UPDATE jobs SET state='failed',finished=?,error=? WHERE id=?",(time.time(),'모델 실행 실패 또는 결과 검증 실패 · '+type(e).__name__,identifier))
    raise
