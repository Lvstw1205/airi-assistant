"""Durable NAS PDF publication and one-reader, interruptible narration leases."""
import contextlib, fcntl, hashlib, json, os, re, secrets, sqlite3, threading, time
from pathlib import Path
NAS=Path(__import__('os').environ.get('AIRI_REPORTS_ROOT',str(Path(__file__).resolve().parent/'data/reports')))
MOUNT=Path(os.environ['AIRI_REPORTS_MOUNT']) if os.environ.get('AIRI_REPORTS_MOUNT') else None
LOCK=threading.RLock()
VERSION='pdf-reports-1'
_reading_until=0
class NASUnavailable(OSError):pass

def connect(app):
 root=app.DATA/'analysis-reports';root.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(root/'reports.sqlite3',timeout=15);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,job TEXT UNIQUE,number INTEGER,path TEXT,title TEXT,created REAL,sha256 TEXT,chunks TEXT,state TEXT,position INTEGER DEFAULT 0,owner TEXT,until REAL DEFAULT 0)')
 return c

@contextlib.contextmanager
def db(app):
 c=connect(app)
 try:
  with c:yield c
 finally:c.close()

def public(row):
 if not row:return None
 item={k:row[k] for k in ('id','number','path','title','created','state','position')}
 item.update(filename=Path(row['path']).name,total=len(json.loads(row['chunks'])),url='/api/reports/pdf?id='+row['id'])
 return item

def find(app,id):
 with db(app) as c:r=c.execute('SELECT * FROM reports WHERE id=? OR job=?',(id,id)).fetchone()
 return public(r)

def notice(item):
 return 'AIRI PDF 보고서 저장 완료\n'+item['filename']+' · '+item['title']+'\n설정한 보고서 폴더에 저장했어. 아이리의 보고서 카드에서 PDF를 열거나 읽기를 계속할 수 있어.'

def publish(app,job,report,text,auto_read=True):
 from intelligence.report_pdf import render_pdf
 id=report['id']
 if not re.fullmatch('[a-f0-9]{32}',id):raise ValueError('Invalid report identifier')
 with LOCK:
  existing=find(app,id)
  if existing:
   pdf_path(app,id)  # Never claim a missing NAS artifact was delivered.
   return existing
  if MOUNT is not None and not MOUNT.is_mount():
   raise NASUnavailable('NAS 연결이 없어 PDF 저장을 보류했어. NAS가 다시 연결되면 저장을 이어갈게. 분석 결과는 보관했어.')
  NAS.mkdir(parents=True,exist_ok=True)
  # Shared lock and atomic rename also serialize writers on two Macs using SMB.
  with (NAS/'.airi-report.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   # Recover a crash after NAS commit but before local receipt commit.
   receipt=NAS/('.airi-'+id+'.json')
   temporary=receipt.with_suffix('.pending.json')
   if not receipt.exists() and temporary.exists():
    recovery=json.loads(temporary.read_text());candidate=NAS/recovery['filename']
    if re.fullmatch(r'AIRI_Report_\d+\.pdf',candidate.name) and candidate.parent==NAS and candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest()==recovery['sha256']:os.replace(temporary,receipt)
   if receipt.exists():
    saved=json.loads(receipt.read_text());target=NAS/saved['filename']
    if target.parent!=NAS or not re.fullmatch(r'AIRI_Report_\d+\.pdf',target.name):raise ValueError('Invalid NAS receipt')
    if hashlib.sha256(target.read_bytes()).hexdigest()!=saved['sha256']:raise ValueError('NAS PDF verification failed')
    number=saved['number'];meta=saved
   else:
    numbers=[int(m[1]) for p in NAS.iterdir() if (m:=re.fullmatch(r'AIRI_Report_(\d+)\.pdf',p.name))]
    number=max(numbers,default=0)+1;target=NAS/f'AIRI_Report_{number}.pdf'
    pending=NAS/('.airi-'+id+'.pending.pdf')
    try:
     meta=render_pdf(pending,report,text,number)
     with pending.open('rb') as f:
      if f.read(5)!=b'%PDF-':raise ValueError('PDF rendering failed')
      os.fsync(f.fileno())
     if target.exists():raise FileExistsError('NAS sequence collision')
     meta.update(number=number,filename=target.name,sha256=hashlib.sha256(pending.read_bytes()).hexdigest())
     # Receipt is recoverable; an incomplete pair is never shown as saved.
     temporary=receipt.with_suffix('.pending.json');temporary.write_text(json.dumps(meta,ensure_ascii=False))
     os.replace(pending,target);os.replace(temporary,receipt)
    finally:pending.unlink(missing_ok=True)
   with db(app) as c:
    c.execute('INSERT OR IGNORE INTO reports(id,job,number,path,title,created,sha256,chunks,state) VALUES(?,?,?,?,?,?,?,?,?)',(id,job['id'],number,str(target),meta['title'],time.time(),meta['sha256'],json.dumps(meta['chunks'],ensure_ascii=False),'pending' if auto_read else 'paused'))
   return find(app,id)

def pdf_path(app,id):
 if not re.fullmatch('[a-f0-9]{32}',str(id)):raise ValueError('보고서를 찾지 못했어.')
 with db(app) as c:row=c.execute('SELECT * FROM reports WHERE id=?',(id,)).fetchone()
 if not row:raise ValueError('보고서를 찾지 못했어.')
 path=Path(row['path'])
 if path.parent.resolve()!=NAS.resolve() or not re.fullmatch(r'AIRI_Report_\d+\.pdf',path.name) or path.is_symlink():raise ValueError('Invalid PDF path')
 if (MOUNT is not None and not MOUNT.is_mount()) or not path.is_file():raise ValueError('NAS를 다시 연결해 줘. 보고서 파일을 열 수 없어.')
 return path

def status(app):
 import intelligence
 intelligence.ensure_worker(app)
 with db(app) as c:
  # A closed tab pauses its report. It must not restart on another tab unexpectedly.
  c.execute("UPDATE reports SET state='paused',owner=NULL,until=0 WHERE state='reading' AND until<?",(time.time(),))
  rows=c.execute('SELECT * FROM reports ORDER BY created DESC LIMIT 20').fetchall()
 latest=intelligence.store(app).report()
 dashboard=None
 if latest:
  payload=json.loads(latest['payload'])
  if payload.get('research'):
   from intelligence.research_engine import ui_summary
   dashboard=ui_summary(payload['research'])
 return {'version':VERSION,'research_schema':'airi-financial-research/3','dashboard':dashboard,'reports':[public(r) for r in rows],'folder':str(NAS)}

def action(app,body):
 global _reading_until
 action=body.get('action');owner=body.get('owner','')
 if not isinstance(owner,str) or not re.fullmatch('[a-zA-Z0-9-]{8,80}',owner):raise ValueError('Invalid reader')
 with db(app) as c:
  c.execute('BEGIN IMMEDIATE');now=time.time()
  if action=='claim':
   if c.execute("SELECT 1 FROM reports WHERE state='reading' AND until>?",(now,)).fetchone():return {'report':None}
   id=body.get('id')
   if id:
    row=c.execute("SELECT * FROM reports WHERE id=? AND state IN ('pending','paused','done')",(id,)).fetchone()
   else:row=c.execute("SELECT * FROM reports WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
   if not row:return {'report':None}
   position=0 if row['state']=='done' else row['position'];lease=secrets.token_hex(24)
   c.execute("UPDATE reports SET state='reading',owner=?,until=?,position=? WHERE id=?",(owner+':'+lease,now+180,position,row['id']))
   value=public(row);value.update(position=position,state='reading')
   _reading_until=time.monotonic()+185
   return {'report':value,'lease':lease}
  row=c.execute('SELECT * FROM reports WHERE id=?',(body.get('id'),)).fetchone()
  if not row or row['owner']!=owner+':'+str(body.get('lease','')) or row['state']!='reading' or row['until']<now:raise ValueError('보고서 읽기 권한이 만료됐어. 이어 읽기를 눌러 줘.')
  if action in ('chunk','heartbeat'):
   _reading_until=time.monotonic()+185
   c.execute('UPDATE reports SET until=? WHERE id=?',(now+180,row['id']))
   chunks=json.loads(row['chunks'])
   return {'text':chunks[row['position']] if row['position']<len(chunks) else '', 'position':row['position'],'total':len(chunks)}
  if action=='advance':
   if body.get('position')!=row['position']:raise ValueError('낭독 순서가 바뀌었어.')
   position=row['position']+1;done=position>=len(json.loads(row['chunks']))
   c.execute('UPDATE reports SET position=?,state=?,until=?,owner=? WHERE id=?',(position,'done' if done else 'reading',0 if done else now+180,None if done else row['owner'],row['id']))
   if done:_reading_until=0
   return {'done':done,'position':position}
  if action=='pause':
   _reading_until=0
   c.execute("UPDATE reports SET state='paused',owner=NULL,until=0 WHERE id=?",(row['id'],));return {'ok':True}
  raise ValueError('지원하지 않는 보고서 동작이야.')
