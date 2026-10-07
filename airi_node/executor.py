"""Common queue gateway. Stage-A workers run only explicit read-only tools."""
import hashlib
import json
import os
import shutil
import threading
import time
import urllib.request
import urllib.error
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .auth import header
from .bus import Bus, Circuit
from .ledger import Ledger, encoded
from .outbox import Outbox


class TaskRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key: str = Field(min_length=8,max_length=160)
    tool_id: Literal['system.health','system.storage']
    node_target: Literal['prime','works'] = 'prime'
    objective: str = Field(default='상태 확인',max_length=2000)
    input: dict = Field(default_factory=dict)
    priority: int = Field(default=50,ge=0,le=100)
    timeout_seconds: int = Field(default=30,ge=1,le=300)


class Runtime:
    def __init__(self,node):
        self.node=node;self.config=node.config
        self.primary=self.config.node_id=='AIRI_PRIME'
        self.owner=('prime' if self.primary else 'works')+':'+uuid.uuid4().hex
        self.ledger=Ledger(self.config.ledger_path) if self.primary else None
        self.bus=Bus('127.0.0.1',self.config.redis_port,self.config.redis_secret_file.read_text().strip()) if self.primary else None
        self.outbox=Outbox(self.config.state_dir/'outbox.sqlite3') if not self.primary else None
        self.circuit=Circuit();self.redis_ok=False;self.error=None
        self.running={};self.running_lock=threading.Lock()
        self.threads=[];self.publish_lock=threading.Lock()

    def status(self):
        value={'enabled':True,'owner':'common execution ledger','redis':'ONLINE' if self.redis_ok else 'LEDGER_ONLY' if self.primary else 'PRIMARY_MANAGED',
               'active_task':self.active,'active_tasks':self.active_tasks,'error':self.error,'circuit_breakers':self.circuit.snapshot()}
        if self.primary:
            with self.ledger.db() as c:
                value['counts']={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM airi_exec_tasks GROUP BY state')}
        else:value['pending_receipts']=len(self.outbox.pending(100))
        return value

    @property
    def active_tasks(self):
        with self.running_lock:return list(self.running)

    @property
    def active(self):return next(iter(self.active_tasks),None)

    def submit(self,body):
        if not self.primary:raise ValueError('Submit to the primary node')
        request=TaskRequest.model_validate(body).model_dump()
        if request['input']:raise ValueError('This read-only tool accepts no arguments')
        request.update(agent_id='system_health',safe_retry=True,max_retries=2)
        return self.ledger.submit(request)

    def flush(self):
        with self.publish_lock:
            try:
                self.redis_ok=self.bus.ping()
                with self.ledger.db() as c:
                    rows=c.execute('SELECT sequence,type,payload FROM airi_exec_events WHERE published=0 ORDER BY sequence LIMIT 100').fetchall()
                for r in rows:
                    value=json.loads(r['payload'])
                    self.bus.publish('airi:events',value)
                    if r['type'] in ('TASK_CREATED','TASK_RETRY'):
                        task=self.ledger.get(value['task_id'])
                        self.bus.publish('airi:tasks:'+task['node_target'],{'task_id':task['task_id'],'event_id':value['event_id']})
                    with self.ledger.db(True) as c:
                        c.execute('UPDATE airi_exec_events SET published=1 WHERE sequence=?',(r['sequence'],))
            except (OSError,RuntimeError):self.redis_ok=False

    def next(self,target,owner):
        stream='airi:tasks:'+target;group='executor-v1'
        try:
            self.bus.ping();self.redis_ok=True
            messages=self.bus.next(stream,group,owner,self.config.reclaim_idle_ms)
        except (OSError,RuntimeError):
            self.redis_ok=False;messages=[]
        if not self.redis_ok and target!='prime':return None
        for identifier,payload in messages:
            task=self.ledger.claim(target,owner,payload['task_id'])
            # The durable claim or preexisting state is committed before acknowledgement.
            try:self.bus.ack(stream,group,identifier)
            except (OSError,RuntimeError):self.redis_ok=False
            if task:return task
        # Reconciliation also covers interrupted publication or messages read before retry time.
        return self.ledger.claim(target,owner)

    def execute(self,task):
        tool=task['tool_id']
        with self.running_lock:self.running[task['task_id']]=tool
        try:
            if tool=='agent.run' and self.primary:
                raw=encoded({'task_id':task['task_id'],'owner':task['lease_owner'],'fence':task['fence']}).encode()
                token=self.config.ledger_path.parent/'session-token'
                req=urllib.request.Request('http://127.0.0.1:8766/api/execution/run',data=raw,
                  headers={'X-AIRI-Token':token.read_text().strip(),'Content-Type':'application/json'})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=task['timeout_seconds']+10) as r:value=json.load(r)
            elif json.loads(task['input_json']):raise ValueError('Unexpected tool arguments')
            elif tool=='system.health':
                value={'node_id':self.config.node_id,'observed_at':time.time(),'pid':os.getpid(),
                       'peer':self.node.peer.snapshot(),'loaded_models':self.node.models.get('loaded',[])}
            elif tool=='system.storage':
                disk=shutil.disk_usage(self.config.state_dir)
                value={'node_id':self.config.node_id,'observed_at':time.time(),'free_bytes':disk.free,'total_bytes':disk.total}
            else:raise ValueError('Tool is not implemented')
            return {'task_id':task['task_id'],'owner':task['lease_owner'],'fence':task['fence'],'output':value,'error':None}
        except Exception as error:
            retry=False;reason=type(error).__name__
            if isinstance(error,urllib.error.HTTPError):
                try:
                    detail=json.loads(error.read(4096));reason=str(detail.get('error',reason))[:180]
                    retry=error.code==503 and detail.get('retryable') is True
                except (ValueError,TypeError):pass
            return {'task_id':task['task_id'],'owner':task['lease_owner'],'fence':task['fence'],'output':None,'error':reason,'retryable':retry}
        finally:
            with self.running_lock:self.running.pop(task['task_id'],None)

    def receive(self,body):
        if not self.primary:raise ValueError('Primary only')
        owner=body.get('owner','')
        if not isinstance(owner,str) or not owner.startswith('works:') or len(owner)>80:raise ValueError('Invalid worker identity')
        receipts=body.get('receipts',[])
        if not isinstance(receipts,list) or len(receipts)>20:raise ValueError('Too many receipts')
        ack=[]
        for receipt in receipts:
            identifier=receipt['id'];p=receipt['payload']
            if not isinstance(identifier,str) or len(identifier)>160:raise ValueError('Invalid receipt')
            digest=hashlib.sha256(encoded(p).encode()).hexdigest()
            row=self.ledger.get(p['task_id'])
            if not row or row['node_target']!='works' or not str(p['owner']).startswith('works:'):raise ValueError('Invalid result target')
            with self.ledger.db() as c:
                old=c.execute('SELECT payload_hash FROM airi_exec_receipts WHERE receipt_id=?',(identifier,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Receipt content changed')
                ack.append(identifier);continue
            accepted=self.ledger.finish(p['task_id'],p['owner'],p['fence'],p.get('output'),p.get('error'),False)
            with self.ledger.db(True) as c:
                c.execute('INSERT OR IGNORE INTO airi_exec_receipts VALUES(?,?,?)',(identifier,digest,time.time()))
                if not accepted:self.ledger.event(c,'STALE_RESULT_REJECTED',row,{'receipt_id':identifier})
            ack.append(identifier)
        active=body.get('active')
        if active:self.ledger.renew(active['task_id'],owner,active['fence'])
        task=None if active else self.next('works',owner)
        return {'ack':ack,'task':task,'mode':'NORMAL' if self.redis_ok else 'LEDGER_ONLY'}

    def primary_loop(self):
        while not self.node.peer.stop.is_set():
            try:
                task=self.next('prime',self.owner)
                if task:
                    done=threading.Event()
                    def renew():
                        while not done.wait(15):
                            if not self.ledger.renew(task['task_id'],task['lease_owner'],task['fence']):break
                    renewer=threading.Thread(target=renew,daemon=True);renewer.start()
                    try:
                        result=self.execute(task)
                        self.ledger.finish(result['task_id'],result['owner'],result['fence'],result['output'],result['error'],result.get('retryable',False))
                    finally:done.set();renewer.join(timeout=1)
                self.error=None
            except Exception as error:self.error=type(error).__name__
            self.node.peer.stop.wait(self.config.queue_poll_seconds)

    def maintain(self):
        while not self.node.peer.stop.is_set():
            try:self.ledger.reap();self.flush()
            except Exception as error:self.error=type(error).__name__
            self.node.peer.stop.wait(self.config.queue_poll_seconds)

    def works_loop(self):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not self.node.peer.stop.is_set():
            try:
                address='127.0.0.1' if self.config.peer_loopback_port else self.node.peer.address
                port=self.config.peer_loopback_port or self.config.port
                if not address:raise ConnectionError('Primary unavailable')
                data=encoded({'owner':self.owner,'receipts':self.outbox.pending()}).encode()
                path='/worker/tick'
                req=urllib.request.Request(f'http://{address}:{port}'+path,data=data,
                    headers={'Authorization':header(self.node.secret,self.config.node_id,'POST',path,data),'Content-Type':'application/json'})
                with opener.open(req,timeout=5) as r:value=json.load(r)
                self.outbox.ack(value.get('ack',[]))
                if value.get('task'):
                    task=value['task'];result=self.execute(task)
                    self.outbox.put(task['task_id']+':'+str(task['fence']),result)
                self.error=None
            except Exception as error:self.error=type(error).__name__
            self.node.peer.stop.wait(self.config.worker_tick_seconds)

    def start(self):
        if self.primary:
            maintenance=threading.Thread(target=self.maintain,daemon=True);self.threads.append(maintenance);maintenance.start()
        for _ in range(self.config.prime_concurrency if self.primary else 1):
            thread=threading.Thread(target=self.primary_loop if self.primary else self.works_loop,daemon=True)
            self.threads.append(thread);thread.start()
