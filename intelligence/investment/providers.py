"""Bounded read-only public-data adapters. No broker, credentials, or order imports."""
import datetime as dt,hashlib,json,math,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo
from .registry import resolve
UTC=dt.timezone.utc
CALENDARS={}
def utcnow():return dt.datetime.now(UTC)
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def get_json(url,attempts=2):
 for attempt in range(attempts):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'AIRI personal research/2'})
   with urllib.request.urlopen(req,timeout=12) as f:
    raw=f.read(4000001)
    if len(raw)>4000000:raise ValueError('Response too large')
    return json.loads(raw)
  except urllib.error.HTTPError as e:
   if e.code not in (429,500,502,503,504) or attempt+1==attempts:raise
  except (OSError,ValueError):
   if attempt+1==attempts:raise
  time.sleep(.5*(attempt+1))

def calendar_state(inst,now):
 if inst['asset_class']=='crypto':return {'state':'24/7','last_session':(now.date()-dt.timedelta(days=1)).isoformat(),'calendar':'UTC daily buckets'}
 if not inst.get('calendar'):return {'state':'calendar_unverified','last_session':None,'calendar':None}
 try:
  import exchange_calendars as xc
  name=inst['calendar']
  if name not in CALENDARS:CALENDARS[name]=xc.get_calendar(name)
  cal=CALENDARS[name];day=now.astimezone(ZoneInfo(inst['timezone'])).date().isoformat();session=cal.date_to_session(day,direction='previous');close=cal.session_close(session).to_pydatetime()
  if close>now:session=cal.previous_session(session)
  current=cal.date_to_session(day,direction='previous');opened=cal.session_open(current).to_pydatetime()<=now<cal.session_close(current).to_pydatetime()
  return {'state':'open' if opened else 'closed','last_session':session.date().isoformat(),'calendar':name}
 except Exception:return {'state':'calendar_unverified','last_session':None,'calendar':inst.get('calendar')}

class Provider:
 def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
 def capabilities(self):return {'quotes':'completed daily observation only','history':'supported registry IDs','fundamentals':'existing company research module','events':'official BoC/Fed/BLS adapters','orders':'unsupported'}
 def fundamentals(self,id):return {'status':'unsupported','reason':'Use existing company filing research; price history is not financial statements.'}
 def events(self,now):
  from ..research_feeds import catalysts
  return catalysts(self.root,now)
 def quotes(self,ids,now=None):return [self.history(i,now=now) for i in ids]
 def history(self,id,period='1y',now=None):
  inst=resolve(id);now=now or utcnow();key=hashlib.sha256(id.encode()).hexdigest();file=self.root/(key+'.json');old=None
  try:
   old=json.loads(file.read_text());age=(now-dt.datetime.fromisoformat(old['retrieved_at'])).total_seconds()
   if 0<=age<3600:return self.quality(old,now)
  except (OSError,ValueError,KeyError):pass
  try:
   value=self.fetch(inst,now);value.update(inst,retrieved_at=utcnow().isoformat(),mode='live',error=None)
   if not value.get('history'):raise ValueError('No completed observations')
   # Hash and preserve the exact normalized provider payload used downstream.
   value['raw_hash']=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
   file.write_text(json.dumps(value));return self.quality(value,now)
  except Exception as e:
   reason=type(e).__name__+(' '+str(e.code) if isinstance(e,urllib.error.HTTPError) else '')
   if old:
    out=self.quality(old,now);out.update(quality_status='stale',error='Latest fetch failed: '+reason);return out
   return {**inst,'mode':'live','value':None,'history':[],'observed_at':None,'retrieved_at':utcnow().isoformat(),'adjustment':'unknown','quality_status':'missing','source_url':None,'error':reason,'market_session':calendar_state(inst,now)}
 def quality(self,row,now):
  row=dict(row);row['market_session']=calendar_state(row,now);last=row['history'][-1];row['value']=last['value'];row['observed_at']=last['observed_at'];row['observation_date']=last['date']
  expected=row['market_session']['last_session'];old=expected and last['date']<expected
  age=(now-dt.datetime.fromisoformat(last['observed_at'])).total_seconds()
  row['quality_status']='stale' if old or age>7*86400 else 'delayed'
  if row.get('conflict'):row['quality_status']='conflicting'
  return row
 def fetch(self,i,now):
  provider=i['provider'];symbol=i['symbol'];rows=[]
  if provider=='yahoo':
   import yfinance as yf
   t=yf.Ticker(symbol);f=t.history(period='1y',interval='1d',auto_adjust=True,actions=True,timeout=15);meta=t.history_metadata
   if i['asset_class']!='index' and meta.get('currency')!=i['currency']:raise ValueError('Currency mismatch')
   if meta.get('symbol')!=symbol:raise ValueError('Provider symbol identity mismatch')
   if not meta.get('exchangeName') or not meta.get('instrumentType'):raise ValueError('Identity metadata missing')
   expected_type={'equity':'EQUITY','index':'INDEX','commodity':'FUTURE'}[i['asset_class']]
   if str(meta['instrumentType']).upper()!=expected_type:raise ValueError('Instrument type mismatch')
   local_day=now.astimezone(ZoneInfo(i['timezone'])).date();state=calendar_state(i,now)
   for stamp,r in f.iterrows():
    day=stamp.date();v=float(r['Close'])
    if not finite(v) or v<=0 or day>local_day:continue
    if state['last_session'] and day.isoformat()>state['last_session']:continue
    if not state['last_session'] and day>=local_day:continue
    # Daily labels are not exact trade timestamps; disclose the period boundary.
    observed=dt.datetime.combine(day,dt.time(),ZoneInfo(i['timezone'])).astimezone(UTC).isoformat()
    rows.append({'date':day.isoformat(),'observed_at':observed,'value':v,'split':float(r.get('Stock Splits',0)),'dividend':float(r.get('Dividends',0))})
   return {'history':rows,'source_url':'https://finance.yahoo.com/quote/'+urllib.parse.quote(symbol,safe='')+'/history/','adjustment':'Provider auto_adjust=True (split/dividend adjusted); not an executable quote','provider_exchange':meta['exchangeName'],'timestamp_basis':'daily period start, not exact last trade','contract':None,'roll_status':'unverified' if i['asset_class']=='commodity' else None}
  if provider=='coinbase':
   url='https://api.exchange.coinbase.com/products/'+symbol+'/candles?granularity=86400';raw=get_json(url)
   if not isinstance(raw,list):raise ValueError('Invalid candles')
   for row in raw:
    start=dt.datetime.fromtimestamp(row[0],UTC)
    if start+dt.timedelta(days=1)>now:continue
    value=float(row[4])
    if not finite(value) or value<=0:raise ValueError('Invalid crypto price')
    rows.append({'date':start.date().isoformat(),'observed_at':start.isoformat(),'value':value})
   rows=sorted(rows,key=lambda x:x['date'])
   return {'history':rows,'source_url':url,'adjustment':'none; Coinbase USD market; completed UTC daily buckets, not rolling 24h','timestamp_basis':'UTC bucket start'}
  if provider=='treasury':
   from ..research_feeds import enrich_rates
   m={'assets':{},'sources':[]};enrich_rates(m,self.root,now);a=m['assets'].get(symbol,{})
   if not a.get('available'):raise ValueError('Treasury unavailable')
   rows=[{'date':r['date'],'observed_at':r['date']+'T00:00:00-04:00','value':r['value']} for r in a['history']]
   for r in rows:r['observed_at']=dt.datetime.combine(dt.date.fromisoformat(r['date']),dt.time(),ZoneInfo('America/New_York')).astimezone(UTC).isoformat()
   return {'history':rows,'source_url':next(s['url'] for s in m['sources'] if s['id']==a['source_id']),'adjustment':'none; par yield','timestamp_basis':'daily reference period, not trade time'}
  if provider=='boc':
   ids={'ca2y':['BD.CDN.2YR.DQ.YLD'],'ca10y':['BD.CDN.10YR.DQ.YLD'],'USD/CAD':['FXUSDCAD'],'USD/KRW':['FXUSDCAD','FXKRWCAD'],'EUR/USD':['FXEURCAD','FXUSDCAD'],'USD/JPY':['FXUSDCAD','FXJPYCAD']}[symbol]
   url='https://www.bankofcanada.ca/valet/observations/'+','.join(ids)+'/json?start_date='+(now.date()-dt.timedelta(days=400)).isoformat();raw=get_json(url)
   for r in raw.get('observations',[]):
    try:values=[float(r[k]['v']) for k in ids]
    except (KeyError,ValueError,TypeError):continue
    if not all(finite(v) for v in values) or len(values)>1 and values[1]<=0:continue
    date=dt.date.fromisoformat(r['d'])
    if date>now.date():continue
    rows.append({'date':r['d'],'observed_at':dt.datetime.combine(date,dt.time(),ZoneInfo('America/Toronto')).astimezone(UTC).isoformat(),'value':values[0]/values[1] if len(values)>1 else values[0],'inputs':dict(zip(ids,values))})
   return {'history':rows,'source_url':url,'adjustment':'none; indicative daily reference, not conversion quote','timestamp_basis':'daily reference period','formula':' / '.join(ids),'cross_rate':len(ids)>1}
  raise ValueError('Unsupported provider')

def fixture(id,now=None):
 """Explicit offline data, never called by live error handling."""
 i=resolve(id);now=now or utcnow();rows=[]
 for n in range(90):
  day=now.date()-dt.timedelta(days=100-n)
  if i['asset_class']!='crypto' and day.weekday()>4:continue
  value=(4+n*.001 if i['asset_class']=='rates' else 100+n*.2+math.sin(n))
  rows.append({'date':day.isoformat(),'observed_at':day.isoformat()+'T00:00:00+00:00','value':value})
 return {**i,'history':rows,'value':rows[-1]['value'],'observed_at':rows[-1]['observed_at'],'observation_date':rows[-1]['date'],'retrieved_at':now.isoformat(),'mode':'fixture','source_url':None,'quality_status':'delayed','adjustment':'SYNTHETIC FIXTURE — not market data','market_session':{'state':'fixture','last_session':rows[-1]['date']},'timestamp_basis':'synthetic','error':None}
