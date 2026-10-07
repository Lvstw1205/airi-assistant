"""Authenticated host integration; reuse AIRI's single durable intelligence queue."""
import datetime as dt,json,time,threading
from urllib.parse import urlsplit,parse_qs
from zoneinfo import ZoneInfo
from .registry import search,resolve,UNSUPPORTED
from .contract import validate
_last_tick=0
_tick_lock=threading.Lock()

def options(app):
 path=app.ROOT/'config/investment-v2.json'
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return {'enabled':True,'daily_brief':'06:00','timezone':'UTC','quote_polling':False}

def latest(app,id=None):
 import intelligence,report_service
 s=intelligence.store(app)
 with s.db() as c:
  if id:
   row=c.execute('SELECT payload FROM reports WHERE id=?',(id,)).fetchone()
   rows=[row] if row else []
  else:rows=c.execute("SELECT payload FROM reports WHERE payload LIKE '%\"investment_v2\"%' ORDER BY created DESC LIMIT 20").fetchall()
 reports=[json.loads(row[0]) for row in rows];reports=[r for r in reports if r.get('investment_v2')]
 value=reports[0] if reports else None
 overview=next((r for r in reports if len(r['investment_v2']['market_rows'])>1),None)
 with s.db() as c:jobs=c.execute("SELECT * FROM jobs WHERE options LIKE '%investment_v2%' ORDER BY created DESC LIMIT 6").fetchall()
 for r in reports:validate(r['investment_v2'])
 return {'report':value['investment_v2'] if value else None,'artifact':report_service.find(app,value['id']) if value else None,'overview':overview['investment_v2'] if overview else None,'jobs':[intelligence.public_job(dict(j)) for j in jobs],'instruments':search(),'unsupported':UNSUPPORTED,'schedule':options(app),'readonly':True,'stale_report': bool(value and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(value['created'])).total_seconds()>86400),'watchlist':watchlist(app),'health':{'collector':'primary Mac','worker':'M1 preferred for matched local model; primary fallback yields to voice/chat','m1':'Pure report analysis; collection, validation, DB and PDF remain on primary'}}

def watchlist(app):
 with app.db() as c:r=c.execute("SELECT value FROM settings WHERE key='investment_watchlist'").fetchone()
 try:return json.loads(r[0]) if r else []
 except ValueError:return []

def action(app,body):
 import intelligence
 kind=body.get('action','report')
 if kind=='watch':
  ids=body.get('ids',[])
  if not isinstance(ids,list) or len(ids)>30:raise ValueError('관심 목록은 최대 30개야.')
  for id in ids:resolve(id)
  with app.db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('investment_watchlist',json.dumps(list(dict.fromkeys(ids)))))
  return {'watchlist':ids}
 if kind!='report':raise ValueError('읽기 전용 분석 요청만 지원해.')
 mode=body.get('mode','live');id=body.get('instrument_id')
 if mode not in ('live','fixture'):raise ValueError('모드를 확인해 줘.')
 if id:resolve(id)
 return intelligence.request(app,'market',{'delivery_style':'investment_v2','investment_mode':mode,'instrument_id':id,'query':'세계 시장 분석' if not id else resolve(id)['name']+' 분석'},destination='web')

def handle_get(app,handler):
 path=urlsplit(handler.path).path
 if path!='/api/investment':return False
 try:
  query=parse_qs(urlsplit(handler.path).query);handler.send_json(latest(app,query.get('id',[None])[0]))
 except (ValueError,KeyError):handler.send_json({'error':'분석 자료를 검증하지 못했어. 이전 PDF는 보고서 목록에서 열 수 있어.'},400)
 return True

def tick(app,now=None):
 global _last_tick
 if now is None and time.monotonic()-_last_tick<60:return
 if not _tick_lock.acquire(blocking=False):return
 try:
  _last_tick=time.monotonic();cfg=options(app)
  if not cfg.get('enabled',True):return
  zone=ZoneInfo(cfg.get('timezone','UTC'));now=now or dt.datetime.now(zone);local=now.astimezone(zone)
  if local.date().isoformat()<cfg.get('start_date','0000-01-01'):return
  hour,minute=map(int,cfg.get('daily_brief','06:00').split(':'));due=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
  with app.db() as c:
   c.execute('CREATE TABLE IF NOT EXISTS investment_schedule(day TEXT PRIMARY KEY,job_id TEXT)')
   # Never backfill multiple days after downtime; one durable key for today's brief.
   if local<due:return
   if c.execute('SELECT 1 FROM investment_schedule WHERE day=?',(local.date().isoformat(),)).fetchone():return
  import intelligence
  job=intelligence.request(app,'market',{'delivery_style':'investment_v2','investment_mode':'live'},key='investment-daily:'+local.date().isoformat())
  with app.db() as c:c.execute('INSERT OR IGNORE INTO investment_schedule VALUES(?,?)',(local.date().isoformat(),job['id']))
 finally:_tick_lock.release()
