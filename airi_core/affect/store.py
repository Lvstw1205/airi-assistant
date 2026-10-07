"""Separate owner-only SQLite ledger, never synchronized with NAS or providers."""
import contextlib,json,os,sqlite3,time
from pathlib import Path

TABLES=('affect_obs','affect_daily','user_baseline','airi_state','user_mind','turns','check_ins','episodes','thoughts','jokes','proposals','metrics')

class Store:
    def __init__(self,folder,config):
        self.folder=Path(folder); self.cfg=config
        self.folder.mkdir(mode=0o700,parents=True,exist_ok=True); self.folder.chmod(0o700)
        self.path=self.folder/'humanlike.sqlite3'
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd);self.path.chmod(0o600)
        with self.db() as c:
            c.execute('PRAGMA journal_mode=DELETE')
            c.executescript(Path(__file__).with_name('schema.sql').read_text())
            c.execute("INSERT OR IGNORE INTO meta VALUES('created',?)",(str(time.time()),))

    @contextlib.contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=2);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA secure_delete=ON')
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def rows(self,sql,args=()):
        with self.db() as c:return [dict(x) for x in c.execute(sql,args)]

    def get(self,key,default=None):
        rows=self.rows('SELECT value FROM meta WHERE key=?',(key,))
        return json.loads(rows[0]['value']) if rows else default

    def set(self,key,value):
        with self.db() as c:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))

    def purge(self):
        # No backup of emotional records is made. Reset all derived state as well.
        with self.db() as c:
            for name in reversed(TABLES):c.execute('DELETE FROM '+name)
            c.execute("DELETE FROM meta WHERE key NOT IN ('guest')")
            c.execute("INSERT OR REPLACE INTO meta VALUES('created',?)",(str(time.time()),))
        with self.db() as c:c.execute('VACUUM')

    def retention(self,now=None):
        now=now or time.time();cutoff=now-self.cfg['retention_days']*86400
        with self.db() as c:
            c.execute("INSERT INTO affect_daily SELECT date(ts,'unixepoch'),count(*),avg(valence),avg(arousal) FROM affect_obs WHERE ts<? GROUP BY date(ts,'unixepoch') ON CONFLICT(day) DO UPDATE SET valence=(affect_daily.valence*affect_daily.n+excluded.valence*excluded.n)/(affect_daily.n+excluded.n),arousal=(affect_daily.arousal*affect_daily.n+excluded.arousal*excluded.n)/(affect_daily.n+excluded.n),n=affect_daily.n+excluded.n",(cutoff,))
            c.execute('DELETE FROM affect_obs WHERE ts<?',(cutoff,))
            for name in ('turns','episodes','thoughts','proposals','metrics'):
                c.execute('DELETE FROM '+name+' WHERE ts<?',(cutoff,))
            c.execute("DELETE FROM check_ins WHERE day<date(?,'unixepoch')",(cutoff,))
            c.execute("DELETE FROM affect_daily WHERE day<date(?,'unixepoch')",(now-self.cfg['aggregate_retention_days']*86400,))
            c.execute('DELETE FROM turns WHERE id NOT IN (SELECT id FROM turns ORDER BY id DESC LIMIT ?)',(self.cfg['recent_turn_limit'],))

    def record_turn(self,result,query,seconds):
        now=time.time()
        with self.db() as c:
            c.execute('INSERT INTO turns(ts,strategy,check_in,topic,text,humor) VALUES(?,?,?,?,?,?)',(now,result['strategy'],int(result['check_in']),result.get('topic','conversation'),result['text'][:self.cfg['reply_chars']],result['humor']))
            c.execute('INSERT OR REPLACE INTO user_mind VALUES(?,?,?)',('want',result.get('want','unknown'),now))
            c.execute('INSERT INTO metrics(ts,inference_seconds,outcome) VALUES(?,?,?)',(now,seconds,'completed'))
        self.retention(now)
