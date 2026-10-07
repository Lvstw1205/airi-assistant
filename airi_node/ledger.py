"""Additive, transactional execution ledger in AIRI's existing local database."""
from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import time
import uuid

TERMINAL={'COMPLETE','FAILED','CANCELLED'}

def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class Ledger:
    def __init__(self,path,clock=time.time):
        self.path=Path(path);self.clock=clock
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS airi_exec_migrations(version INTEGER PRIMARY KEY, applied REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS airi_exec_tasks(
              task_id TEXT PRIMARY KEY, parent_task_id TEXT, root_task_id TEXT NOT NULL,
              correlation_id TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, signature TEXT NOT NULL,
              agent_id TEXT, tool_id TEXT NOT NULL, node_target TEXT NOT NULL, node_actual TEXT,
              objective TEXT NOT NULL, input_json TEXT NOT NULL, constraints_json TEXT NOT NULL DEFAULT '{}',
              priority INTEGER NOT NULL, state TEXT NOT NULL, depends_on_json TEXT NOT NULL DEFAULT '[]',
              optional INTEGER NOT NULL DEFAULT 0, safe_retry INTEGER NOT NULL,
              retry_count INTEGER NOT NULL DEFAULT 0, max_retries INTEGER NOT NULL,
              timeout_seconds INTEGER NOT NULL, lease_owner TEXT, lease_expires REAL,
              fence INTEGER NOT NULL DEFAULT 0, model_used TEXT, confidence REAL,
              output_json TEXT, sources_json TEXT, error TEXT, created REAL NOT NULL,
              started REAL, completed REAL, not_before REAL NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS airi_exec_task_state ON airi_exec_tasks(state,node_target,priority);
            CREATE TABLE IF NOT EXISTS airi_exec_events(
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,
              task_id TEXT, type TEXT NOT NULL, payload TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS airi_exec_locks(
              name TEXT PRIMARY KEY,owner TEXT NOT NULL,fencing_token INTEGER NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS airi_exec_receipts(
              receipt_id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,received REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS airi_exec_approvals(
              approval_id TEXT PRIMARY KEY,task_id TEXT,tool_id TEXT,tier TEXT,summary TEXT,
              args_redacted_json TEXT,state TEXT,requested REAL,expires REAL,decided REAL,via TEXT);
            CREATE TABLE IF NOT EXISTS airi_exec_audit(
              id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,task_id TEXT,actor TEXT,action TEXT,tier TEXT,result TEXT,detail_json TEXT);
            INSERT OR IGNORE INTO airi_exec_migrations VALUES(1,strftime('%s','now'));
            ''')

    @contextmanager
    def db(self,write=False):
        c=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA busy_timeout=5000');c.execute('PRAGMA foreign_keys=ON')
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            if c.in_transaction:c.commit()
        except BaseException:
            if c.in_transaction:c.rollback()
            raise
        finally:c.close()

    def event(self,c,kind,task=None,data=None):
        event={'event_id':str(uuid.uuid4()),'type':kind,'ts':self.clock(),'node_id':'AIRI_PRIME',
               'task_id':task['task_id'] if task else None,'correlation_id':task['correlation_id'] if task else None,'data':data or {}}
        c.execute('INSERT INTO airi_exec_events(event_id,task_id,type,payload) VALUES(?,?,?,?)',
                  (event['event_id'],event['task_id'],kind,encoded(event)))

    def submit(self,value,_connection=None):
        values=dict(value);now=self.clock()
        key=values['idempotency_key'];signature=hashlib.sha256(encoded(values).encode()).hexdigest()
        with nullcontext(_connection) if _connection is not None else self.db(True) as c:
            prior=c.execute('SELECT * FROM airi_exec_tasks WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                if prior['signature']!=signature:raise ValueError('Idempotency key reused with different request')
                return dict(prior)
            identifier=values.get('task_id') or str(uuid.uuid4())
            deps=values.get('depends_on',[])
            for dep in deps:
                if not c.execute('SELECT 1 FROM airi_exec_tasks WHERE task_id=?',(dep,)).fetchone():raise ValueError('Unknown dependency')
            fields={'task_id':identifier,'root_task_id':values.get('root_task_id') or identifier,
                    'parent_task_id':values.get('parent_task_id'),'correlation_id':values.get('correlation_id') or identifier,
                    'idempotency_key':key,'signature':signature,'agent_id':values.get('agent_id'),
                    'tool_id':values['tool_id'],'node_target':values.get('node_target','prime'),
                    'objective':values.get('objective',values['tool_id']),'input_json':encoded(values.get('input',{})),
                    'constraints_json':encoded(values.get('constraints',{})),
                    'priority':values.get('priority',50),'state':'WAITING' if deps else 'QUEUED',
                    'depends_on_json':encoded(deps),'optional':bool(values.get('optional')),
                    'safe_retry':bool(values.get('safe_retry',False)),'max_retries':values.get('max_retries',2),
                    'timeout_seconds':values.get('timeout_seconds',120),'created':now}
            c.execute('INSERT INTO airi_exec_tasks('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(fields.values()))
            self.event(c,'TASK_CREATED',fields,{'node_target':fields['node_target']})
            return dict(c.execute('SELECT * FROM airi_exec_tasks WHERE task_id=?',(identifier,)).fetchone())

    def submit_batch(self,values):
        with self.db(True) as c:
            return [self.submit(v,_connection=c) for v in values]

    def tasks(self,state=None,limit=50):
        with self.db() as c:
            q='SELECT * FROM airi_exec_tasks'+(' WHERE state=?' if state else '')+' ORDER BY created DESC LIMIT ?'
            return [dict(r) for r in c.execute(q,([state] if state else [])+[min(100,max(1,limit))])]

    def get(self,identifier):
        with self.db() as c:
            r=c.execute('SELECT * FROM airi_exec_tasks WHERE task_id=?',(identifier,)).fetchone()
            return dict(r) if r else None

    def reap(self):
        now=self.clock()
        with self.db(True) as c:
            for row in c.execute("SELECT * FROM airi_exec_tasks WHERE state IN ('RUNNING','REVIEW') AND lease_expires<?",(now,)).fetchall():
                retry=bool(row['safe_retry']) and row['retry_count']<row['max_retries']
                state='QUEUED' if retry else 'FAILED'
                c.execute('UPDATE airi_exec_tasks SET state=?,retry_count=retry_count+1,lease_owner=NULL,lease_expires=NULL,error=?,completed=?,not_before=? WHERE task_id=?',
                          (state,'Lease expired',None if retry else now,now+min(30,2*2**row['retry_count'])+random.random(),row['task_id']))
                self.event(c,'TASK_RETRY' if retry else 'TASK_FAILED',row,{'reason':'lease_expired'})
            for row in c.execute("SELECT * FROM airi_exec_tasks WHERE state='WAITING'").fetchall():
                deps=[c.execute('SELECT state,task_id FROM airi_exec_tasks WHERE task_id=?',(d,)).fetchone() for d in json.loads(row['depends_on_json'])]
                failed=[d['task_id'] for d in deps if d and d['state'] in ('FAILED','CANCELLED')]
                if failed and not row['optional']:
                    c.execute("UPDATE airi_exec_tasks SET state='CANCELLED',completed=?,error='Dependency failed' WHERE task_id=?",(now,row['task_id']))
                    self.event(c,'TASK_CANCELLED',row,{'dependency_failed':failed})
                elif all(d and d['state'] in TERMINAL for d in deps):
                    constraints=json.loads(row['constraints_json'])
                    constraints['missing_inputs']=failed
                    c.execute("UPDATE airi_exec_tasks SET state='QUEUED',constraints_json=? WHERE task_id=?",(encoded(constraints),row['task_id']))
                    self.event(c,'TASK_READY',row,{'missing_inputs':failed})

    def claim(self,node,owner,identifier=None):
        now=self.clock()
        with self.db(True) as c:
            sql="SELECT * FROM airi_exec_tasks WHERE state='QUEUED' AND node_target=? AND not_before<=?"
            args=[node,now]
            if identifier:sql+=' AND task_id=?';args.append(identifier)
            row=c.execute(sql+' ORDER BY priority DESC,created LIMIT 1',args).fetchone()
            if not row:return None
            c.execute("UPDATE airi_exec_tasks SET state='RUNNING',node_actual=?,lease_owner=?,lease_expires=?,fence=fence+1,started=? WHERE task_id=?",
                      (node,owner,now+row['timeout_seconds']+30,now,row['task_id']))
            self.event(c,'TASK_STARTED',row,{'node_actual':node,'lease_owner':owner})
            return dict(c.execute('SELECT * FROM airi_exec_tasks WHERE task_id=?',(row['task_id'],)).fetchone())

    def renew(self,identifier,owner,fence):
        with self.db(True) as c:
            n=c.execute("UPDATE airi_exec_tasks SET lease_expires=?+timeout_seconds+30 WHERE task_id=? AND lease_owner=? AND fence=? AND state IN ('RUNNING','REVIEW') AND lease_expires>?",(self.clock(),identifier,owner,fence,self.clock())).rowcount
            return n==1

    def finish(self,identifier,owner,fence,output=None,error=None,retryable=False):
        now=self.clock()
        with self.db(True) as c:
            row=c.execute('SELECT * FROM airi_exec_tasks WHERE task_id=?',(identifier,)).fetchone()
            if not row or row['state'] not in ('RUNNING','REVIEW') or row['lease_owner']!=owner or row['fence']!=fence or row['lease_expires']<=now:
                return False
            if not error:
                c.execute("UPDATE airi_exec_tasks SET state='REVIEW' WHERE task_id=?",(identifier,))
                state='COMPLETE'
            else:state='QUEUED' if retryable and row['safe_retry'] and row['retry_count']<row['max_retries'] else 'FAILED'
            c.execute('UPDATE airi_exec_tasks SET state=?,output_json=?,error=?,completed=?,lease_owner=NULL,lease_expires=NULL,retry_count=retry_count+?,not_before=? WHERE task_id=?',
                      (state,encoded(output) if output is not None else None,error,None if state=='QUEUED' else now,int(state=='QUEUED'),now+min(30,2*2**row['retry_count'])+random.random(),identifier))
            self.event(c,'TASK_COMPLETED' if state=='COMPLETE' else 'TASK_RETRY' if state=='QUEUED' else 'TASK_FAILED',row,{'state':state})
            return True

    def cancel(self,identifier):
        with self.db(True) as c:
            row=c.execute('SELECT * FROM airi_exec_tasks WHERE task_id=?',(identifier,)).fetchone()
            if not row:raise ValueError('Unknown task')
            if row['state'] not in TERMINAL:
                c.execute("UPDATE airi_exec_tasks SET state='CANCELLED',completed=?,lease_owner=NULL,lease_expires=NULL WHERE task_id=?",(self.clock(),identifier))
                self.event(c,'TASK_CANCELLED',row)
        return self.get(identifier)

    def cancel_root(self,root):
        with self.db(True) as c:
            rows=c.execute("SELECT * FROM airi_exec_tasks WHERE root_task_id=? AND state NOT IN ('COMPLETE','FAILED','CANCELLED')",(root,)).fetchall()
            for row in rows:
                c.execute("UPDATE airi_exec_tasks SET state='CANCELLED',completed=?,lease_owner=NULL,lease_expires=NULL WHERE task_id=?",(self.clock(),row['task_id']))
                self.event(c,'TASK_CANCELLED',row)
        return {'cancelled':len(rows),'root_task_id':root}

    def acquire(self,name,owner,ttl,bus=None,node='prime'):
        """Redis speeds exclusion; fencing in this transaction is authoritative."""
        acquired=False
        if bus:
            try:
                acquired=bus.command('SET','airi:lock:'+name,owner,'NX','PX',int(ttl*1000))=='OK'
                if not acquired:return None
            except (OSError,RuntimeError):
                if node!='prime':return None
        elif node!='prime':return None
        with self.db(True) as c:
            r=c.execute('SELECT * FROM airi_exec_locks WHERE name=?',(name,)).fetchone()
            if r and r['expires']>self.clock():
                token=None
            else:
                token=(r['fencing_token']+1) if r else 1
                c.execute('INSERT OR REPLACE INTO airi_exec_locks VALUES(?,?,?,?)',(name,owner,token,self.clock()+ttl))
        if token is None and acquired:self.release_redis(bus,name,owner)
        return token

    def valid_lock(self,c,name,owner,fence):
        return c.execute('SELECT 1 FROM airi_exec_locks WHERE name=? AND owner=? AND fencing_token=? AND expires>?',(name,owner,fence,self.clock())).fetchone() is not None

    def release(self,name,owner,fence,bus=None):
        with self.db(True) as c:
            c.execute('UPDATE airi_exec_locks SET expires=0 WHERE name=? AND owner=? AND fencing_token=?',(name,owner,fence))
        if bus:self.release_redis(bus,name,owner)

    @staticmethod
    def release_redis(bus,name,owner):
        try:bus.command('EVAL',"if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) end return 0",1,'airi:lock:'+name,owner)
        except (OSError,RuntimeError):return False
        return True
