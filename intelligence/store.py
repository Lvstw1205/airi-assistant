"""Private durable event timeline, extraction cache, reports and job receipts."""
import contextlib,datetime as dt,json,sqlite3,uuid
from pathlib import Path
from .retrieval import UTC
class Store:
 def __init__(self,folder):
  self.folder=Path(folder);self.folder.mkdir(mode=0o700,parents=True,exist_ok=True);self.path=self.folder/'intelligence.sqlite3'
  with self.db() as c:
   c.executescript('''
    CREATE TABLE IF NOT EXISTS documents(id TEXT,body_hash TEXT,payload TEXT,extraction TEXT,created TEXT,PRIMARY KEY(id,body_hash));
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,event_time TEXT,observed TEXT,payload TEXT);
    CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,profile TEXT,created TEXT,payload TEXT,text TEXT);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,request_key TEXT UNIQUE,profile TEXT,options TEXT,state TEXT,progress TEXT,created TEXT,updated TEXT,result_id TEXT,error TEXT);
   ''')
  self.path.chmod(0o600)
 @contextlib.contextmanager
 def db(self):
  c=sqlite3.connect(str(self.path),timeout=15);c.row_factory=sqlite3.Row
  try:
   c.execute('PRAGMA journal_mode=WAL');yield c;c.commit()
  except Exception:c.rollback();raise
  finally:c.close()
 def extraction(self,doc):
  with self.db() as c:r=c.execute('SELECT extraction FROM documents WHERE id=? AND body_hash=?',(doc['id'],doc['body_hash'])).fetchone()
  return json.loads(r[0]) if r else None
 def save_extraction(self,doc,value):
  with self.db() as c:c.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)',(doc['id'],doc['body_hash'],json.dumps(doc,ensure_ascii=False),json.dumps(value,ensure_ascii=False),doc['retrieved']))
 def history(self,now,days=30):
  with self.db() as c:rows=c.execute('SELECT payload FROM events WHERE observed>=? ORDER BY observed',( (now-dt.timedelta(days=days)).isoformat(),)).fetchall()
  return [json.loads(r[0]) for r in rows]
 def save_report(self,report,text):
  with self.db() as c:
   for e in report['events']+report.get('context_events',[]):
    c.execute('INSERT OR REPLACE INTO events VALUES(?,?,?,?)',(e['id'],e.get('timestamp'),report['created'],json.dumps(e,ensure_ascii=False)))
   c.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?,?)',(report['id'],report['profile'],report['created'],json.dumps(report,ensure_ascii=False),text))
   cutoff=(dt.datetime.fromisoformat(report['created'])-dt.timedelta(days=30)).isoformat()
   c.execute('DELETE FROM documents WHERE created<?',(cutoff,));c.execute('DELETE FROM events WHERE observed<?',(cutoff,));c.execute('DELETE FROM reports WHERE created<?',(cutoff,));c.execute("DELETE FROM jobs WHERE created<? AND state IN ('completed','failed')",(cutoff,))
 def report(self,report_id=None,profile=None):
  with self.db() as c:
   if report_id:r=c.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
   elif profile:r=c.execute('SELECT * FROM reports WHERE profile=? ORDER BY created DESC LIMIT 1',(profile,)).fetchone()
   else:r=c.execute('SELECT * FROM reports ORDER BY created DESC LIMIT 1').fetchone()
  return dict(r) if r else None
 def enqueue(self,profile,options,key):
  now=dt.datetime.now(UTC).isoformat()
  with self.db() as c:
   c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,key,profile,json.dumps(options),'queued','Queued',now,now,None,None))
   return dict(c.execute('SELECT * FROM jobs WHERE request_key=?',(key,)).fetchone())
 def job(self,key):
  with self.db() as c:r=c.execute('SELECT * FROM jobs WHERE id=? OR request_key=?',(key,key)).fetchone()
  return dict(r) if r else None
 def update(self,id,**values):
  allowed={'state','progress','result_id','error'};assert set(values)<=allowed;values['updated']=dt.datetime.now(UTC).isoformat()
  with self.db() as c:c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[id])
 def recover(self):
  with self.db() as c:c.execute("UPDATE jobs SET state='queued',progress='Resuming after restart' WHERE state='running'")
 def next_job(self):
  with self.db() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
   if r:c.execute("UPDATE jobs SET state='running' WHERE id=?",(r['id'],))
  return dict(r) if r else None
