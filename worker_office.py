"""Authenticated AIRI view of real M1 departments, queue and results."""
import threading,time,json,sqlite3
from contextlib import closing
import mac_cluster
from office_core import Store,DEPARTMENTS,STAFF,employee_for
_services={};_lock=threading.Lock()
def automations(app):
 path=app.DATA/'news-intelligence/intelligence.sqlite3'
 if not path.exists():return []
 try:
  with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)) as c:
   c.row_factory=sqlite3.Row
   return [dict(r) for r in c.execute("SELECT id,profile,state,progress,updated,result_id,error FROM jobs ORDER BY created DESC LIMIT 6")]
 except sqlite3.Error:return []

class Service:
 def __init__(self,app):
  self.app=app;self.store=Store(app.DATA/'worker-office');self.store.recover()
  self.thread=threading.Thread(target=self.work,daemon=True,name='airi-office-dispatch');self.thread.start()
  threading.Thread(target=self.sync,daemon=True,name='airi-office-hq-sync').start()
 def sync(self):
  while True:
   try:
    state=mac_cluster.status(self.app)
    if 'office_v1' in state.get('capabilities',[]):
     mac_cluster.mac_dispatch.exchange(mac_cluster.command(self.app),{'version':1,'action':'office_hq','state':{'updated_at':time.time(),'automations':automations(self.app),'workflow':'자동 보고서: M1 자료 정리·초안 → M6 검수·보강 → PDF 저장'}},10)
   except Exception:pass
   time.sleep(15)
 def execute(self,request):
  result=mac_cluster.try_offload(self.app,request['messages'],request['model'],request['max_tokens'],purpose=request.get('purpose','M1 작업실'),job_id=request.get('job_id'),timeout=135)
  if not result:raise ValueError(mac_cluster.REASONS.get(mac_cluster.last_reason(),'M1 처리 실패'))
  return result
 def work(self):
  while True:
   try:
    identifier=self.store.next()
    if identifier:
     def run(req):
      job=self.store.get(identifier);return self.execute({**req,'job_id':identifier,'purpose':employee_for(job['department'],job.get('employee'))['name']+' · '+next(d['name'] for d in DEPARTMENTS if d['id']==job['department'])})
     self.store.run(identifier,run)
    else:time.sleep(1)
   except Exception:time.sleep(1)
 def submit(self,body):
  s=mac_cluster.status(self.app)
  if s.get('stale') or not s.get('checked_at'):mac_cluster.refresh(self.app);s=mac_cluster.status(self.app)
  if not s.get('connected') or s.get('state')!='ready':raise ValueError('M1이 연결되지 않았어. 작업실에서 연결 상태를 먼저 확인해 줘.')
  if not s['routing']['enabled']:raise ValueError('M1 자동 배정이 꺼져 있어. 분산 설정에서 켜 줘.')
  if 'office_v1' in s.get('capabilities',[]):
   r=mac_cluster.mac_dispatch.exchange(mac_cluster.command(self.app),{'version':1,'action':'office_submit','prompt':body.get('prompt'),'department':body.get('department'),'request_key':body.get('request_key'),'employee':body.get('employee')},15)
   mac_cluster.refresh(self.app);return r
  return {'job':self.store.submit(body.get('prompt'),body.get('department'),s['routing']['model'],request_key=body.get('request_key'),employee=body.get('employee'))}
 def result(self,identifier):
  job=self.store.get(identifier)
  if job:return {'job':job}
  return mac_cluster.mac_dispatch.exchange(mac_cluster.command(self.app),{'version':1,'action':'office_result','id':identifier},15)
 def cancel(self,identifier):
  if self.store.get(identifier):return {'job':self.store.cancel(identifier)}
  return mac_cluster.mac_dispatch.exchange(mac_cluster.command(self.app),{'version':1,'action':'office_cancel','id':identifier},15)
 def snapshot(self):
  cluster=mac_cluster.status(self.app);local=self.store.snapshot();remote=cluster.get('office') or {}
  jobs={j['id']:j for j in local['jobs']}
  for job in remote.get('jobs',[]):jobs[job['id']]=job
  data=sorted(jobs.values(),key=lambda j:(j['state'] not in ('running','queued'),-j['created']))[:60]
  return {'node':'M1','view':'hq','installed':'office_v1' in cluster.get('capabilities',[]),'model':remote.get('model',cluster['routing']['model']),
   'staff':STAFF,'departments':[{k:v for k,v in d.items() if k!='instruction'} for d in DEPARTMENTS],
   'jobs':data,'counts':{state:sum(1 for j in data if j['state']==state) for state in ('queued','running','completed','failed','interrupted')},
   'automations':automations(self.app),'hq_updated_at':time.time(),'connection':cluster,'sensor_installed':'hardware_metrics' in cluster.get('capabilities',[])}

def service(app):
 key=str(app.DATA)
 with _lock:
  if key not in _services:_services[key]=Service(app)
  return _services[key]

def snapshot(app):return service(app).snapshot()
def action(app,body):
 s=service(app)
 if body.get('action')=='submit':return s.submit(body)
 if body.get('action')=='cancel':return s.cancel(str(body.get('id','')))
 if body.get('action')=='refresh':mac_cluster.refresh(app);return s.snapshot()
 raise ValueError('알 수 없는 작업실 명령이야.')
