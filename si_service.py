"""Local UI controls for SI foundations. Background growth stays stopped."""
import contextlib,json,os,sqlite3,threading,time
from pathlib import Path
from airi_core.si.recall import index
from airi_core.si.si_index import metrics

class SI:
    def __init__(self,app):
        self.app=app;self.cfg=json.loads((app.ROOT/'config/si.yaml').read_text())
        folder=app.DATA/'si';folder.mkdir(mode=0o700,parents=True,exist_ok=True);folder.chmod(0o700)
        self.path=folder/'si.sqlite3';fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd);self.path.chmod(0o600)
        with self.db() as c:
            c.executescript('CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,payload TEXT);')
            index.init(c)
    @contextlib.contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=2);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
    def stopped(self):
        with self.db() as c:r=c.execute("SELECT value FROM config WHERE key='stopped'").fetchone()
        return not self.cfg['enabled'] if not r else json.loads(r[0])
    def stop(self):
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO config VALUES('stopped','true')")
            c.execute('INSERT INTO versions(ts,kind,payload) VALUES(?,?,?)',(time.time(),'kill_switch','{"stopped":true}'))
        return self.status()
    def status(self):
        with self.db() as c:count=c.execute('SELECT count(*) FROM recall').fetchone()[0]
        return {'stopped':self.stopped(),'automatic_growth':False,'tier2_validated':False,'recall':{'indexed_messages':count,'method':'BM25','vector_enabled':False,'mail_connected':False,'folders':[]},'metrics':metrics([],[],[]),'stages':{'recall':'chat index available on request','deep_think':'resource validation required','sleep_compute':'not enabled','skill_forge':'proposal skeleton','evolution':'proposal skeleton'},'quality_validated':False}
    def build_index(self):
        with self.db() as c:
            known=c.execute("SELECT max(cast(substr(source_id,6) AS INTEGER)) FROM recall").fetchone()[0] or 0
            rows=self.app.rows("SELECT id,created,content FROM messages WHERE session='main' AND id>? ORDER BY id LIMIT ?",(known,self.cfg['index_batch_limit']))
            count=index.update(c,rows)
        return {'added':count,'more_possible':len(rows)==self.cfg['index_batch_limit'],**self.status()}
    def search(self,query):
        if not isinstance(query,str) or len(query)>200:raise ValueError('검색어는 200자 이내로 입력해줘.')
        with self.db() as c:return {'results':index.search(c,query,self.cfg['recall_result_limit']),'method':'BM25','partial':True,'source':'owner local chat','local_only':True}
    def clear_index(self):
        with self.db() as c:c.execute('DELETE FROM recall')

_instances={};_lock=threading.Lock()
def service(app):
    with _lock:
        key=str(app.DATA)
        if key not in _instances:_instances[key]=SI(app)
        return _instances[key]

def command(app,query):
    s=query.strip().rstrip('.!').lower()
    if s in ('si 중지','si 멈춰','si 꺼','/si stop'):
        service(app).stop();return 'SI 확장 작업을 멈췄어. 기본 대화와 안전 응답은 계속 동작해.'
    if s in ('si 상태','/si status'):
        value=service(app).status();return 'SI 자동 작업은 정지 상태야. 대화 검색 색인은 '+str(value['recall']['indexed_messages'])+'개이고, 성장 점수는 아직 검증되지 않았어.'
    return None
