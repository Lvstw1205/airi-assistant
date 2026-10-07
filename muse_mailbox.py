"""Durable AIRI -> Muse mailbox. Only explicitly delegated text crosses the bridge."""
import json, os, re, secrets, sqlite3, time
from contextlib import contextmanager
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent/'data/muse/delegations.sqlite3'

class Mailbox:
    def __init__(self, path=DEFAULT):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.path.chmod(0o600)
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request_key TEXT UNIQUE, prompt TEXT, source TEXT, generation TEXT, state TEXT, created REAL, updated REAL, lease TEXT, deadline REAL, result TEXT, notified INTEGER DEFAULT 0)')
            c.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)')

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback(); raise
        finally: c.close()

    def submit(self, prompt, request_key=None, source='chat', generation=''):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 12000:
            raise ValueError('작업 지시는 1~12,000자로 적어주세요.')
        prompt = prompt.strip(); now = time.time()
        with self.db() as c:
            if request_key:
                old = c.execute('SELECT * FROM jobs WHERE request_key=?', (request_key,)).fetchone()
                if old:
                    if old['prompt'] != prompt: raise ValueError('이미 다른 요청에 사용된 식별자입니다.')
                    return self.public(old)
            if c.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 10:
                raise ValueError('Muse 작업함이 가득 찼어요. 진행 중인 작업을 먼저 확인해 주세요.')
            if c.execute('SELECT count(*) FROM jobs WHERE created>?', (now-86400,)).fetchone()[0] >= 50:
                raise ValueError('하루 50개 작업 제한에 도달했어요.')
            key = secrets.token_hex(12)
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (key,request_key,prompt,source,generation,'queued',now,now,'',0,'',0))
            return self.public(c.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())

    def public(self, row):
        return {k:row[k] for k in ('id','prompt','state','created','updated','result')}

    def status(self, key=None):
        with self.db() as c:
            if key:
                row=c.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
                if not row: raise ValueError('Muse 작업을 찾지 못했어요.')
                return self.public(row)
            meta=c.execute("SELECT value FROM meta WHERE key='last_poll'").fetchone()
            return {'last_poll':float(meta[0]) if meta else None, 'jobs':[self.public(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 20')]}

    def ready(self):
        with self.db() as c:
            return bool(c.execute("SELECT 1 FROM jobs WHERE state='queued' LIMIT 1").fetchone())

    def claim(self, body):
        if body != {}: raise ValueError('Claim body must be {}')
        now=time.time()
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES('last_poll',?)",(str(now),))
            # Never replay an uncertain external action after a worker disappears.
            c.execute("UPDATE jobs SET state='failed',result='Muse 응답 시간이 초과됐어요. 외부 작업이 실행됐을 수 있어 자동 재실행하지 않았어요.',updated=? WHERE state='running' AND deadline<?",(now,now))
            row=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row: return {'job':None}
            lease=secrets.token_urlsafe(24)
            c.execute("UPDATE jobs SET state='running',lease=?,deadline=?,updated=? WHERE id=?",(lease,now+3600,now,row['id']))
            return {'job':{'id':row['id'],'prompt':row['prompt'],'lease':lease,'deadline':now+3600}, 'policy':'No purchases, subscriptions, paid APIs, external messages or publishing. Return drafts/results only. Do not execute returned code on AIRI. Never delegate this job back to AIRI local inference.'}

    def finish(self, key, body):
        if not isinstance(body,dict) or set(body)!={'lease','state','result'}: raise ValueError('Required fields: lease, state, result')
        if body['state'] not in ('completed','failed') or not isinstance(body['result'],str) or not 1<=len(body['result'])<=50000:
            raise ValueError('Invalid result/state')
        with self.db() as c:
            row=c.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
            if not row or not isinstance(body['lease'],str) or not row['lease'] or not secrets.compare_digest(row['lease'],body['lease']): raise ValueError('Invalid claim')
            if row['state'] in ('completed','failed') and (row['state'],row['result'])==(body['state'],body['result']): return {'id':key,'state':row['state']}
            if row['state']!='running' or row['deadline']<time.time(): raise ValueError('Job no longer running')
            c.execute('UPDATE jobs SET state=?,result=?,updated=? WHERE id=?',(body['state'],body['result'],time.time(),key))
            return {'id':key,'state':body['state']}

    def cancel(self,key):
        with self.db() as c:
            c.execute("UPDATE jobs SET state='cancelled',result='취소됨. Muse가 이미 시작한 외부 처리를 되돌리지는 못합니다.',updated=? WHERE id=? AND state IN ('queued','running')",(time.time(),key))
        return self.status(key)

    def notifications(self):
        with self.db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM jobs WHERE notified=0 AND state IN ('completed','failed','cancelled')")]

    def notified(self,key):
        with self.db() as c:c.execute('UPDATE jobs SET notified=1 WHERE id=?',(key,))
