"""M1 local durable receipts; never a copy of the primary ledger or memories."""
import json
from pathlib import Path
import sqlite3
import time

class Outbox:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,created REAL NOT NULL,payload TEXT NOT NULL)')
        self.path.chmod(0o600)
    def put(self,identifier,payload):
        data=json.dumps(payload,ensure_ascii=False,allow_nan=False)
        with sqlite3.connect(self.path,timeout=5) as c:
            c.execute('INSERT OR IGNORE INTO outbox VALUES(?,?,?)',(identifier,time.time(),data))
    def pending(self,limit=20):
        with sqlite3.connect(self.path,timeout=5) as c:
            return [{'id':r[0],'payload':json.loads(r[1])} for r in c.execute('SELECT id,payload FROM outbox ORDER BY created,rowid LIMIT ?',(limit,))]
    def ack(self,identifiers):
        with sqlite3.connect(self.path,timeout=5) as c:
            c.executemany('DELETE FROM outbox WHERE id=?',[(i,) for i in identifiers])
