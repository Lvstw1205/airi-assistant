"""Public dashboard feeds. Source timestamps are kept; no synthetic prices/news."""
import concurrent.futures,urllib.request,xml.etree.ElementTree as ET,json,re,datetime as dt,threading,time
from email.utils import parsedate_to_datetime
import mcp_bridge

def markets(app):
 def one(symbol):
  try:return mcp_bridge.request(app,'market','call','market_snapshot',{'symbol':symbol})
  except Exception:return {'label':symbol,'error':'시세를 확인하지 못했습니다.'}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:items=list(pool.map(one,watchlist(app)))
 return {'items':items}

NEWS_FEEDS={
 'canada':('캐나다','CBC Canada','https://www.cbc.ca/webfeed/rss/rss-canada'),
 'us':('미국','NPR National','https://feeds.npr.org/1003/rss.xml'),
 'business':('경제','CBC Business','https://www.cbc.ca/webfeed/rss/rss-business'),
 'technology':('기술·과학','CBC Technology','https://www.cbc.ca/webfeed/rss/rss-technology'),
}
NEWS_CACHE={}
NEWS_LOCK=threading.Lock()
NEWS_SUPPLEMENTS={
 'canada':[('Global News Canada','https://globalnews.ca/canada/feed/')],
 'us':[('Global News US','https://globalnews.ca/us-news/feed/')],
 'business':[('CNBC Business','https://www.cnbc.com/id/100003114/device/rss/rss.html')],
 'technology':[('CNBC Technology','https://www.cnbc.com/id/19854910/device/rss/rss.html')],
}

def news_priority(title):
 for pattern,reason in [
  (r'\b(evacuation order|state of emergency|tsunami warning|emergency alert)\b','안전에 영향을 줄 수 있는 긴급 소식'),
  (r'\b(bank of canada|federal reserve|fed)\b.*\b(cuts?|raises?|hikes?|holds?)\b.*\brates?\b','캐나다·미국 금리 결정'),
  (r'\b(trading halt|circuit breaker|market crash|major outage|data breach)\b','시장 또는 서비스 이용에 영향을 줄 수 있는 소식'),
 ]:
  if re.search(pattern,title,re.I):return reason
 return ''

def parse_news(raw,source):
 root=ET.fromstring(raw);items=[];seen=set()
 for item in root.findall('.//item'):
  link=item.findtext('link','').strip();title=item.findtext('title','').strip()
  if not title or not link.startswith('https://') or link in seen:continue
  seen.add(link)
  try:
   published=parsedate_to_datetime(item.findtext('pubDate',''))
   if published.tzinfo is None:published=published.replace(tzinfo=dt.timezone.utc)
   published=published.astimezone(dt.timezone.utc).isoformat()
  except (TypeError,ValueError,OverflowError):published=''
  items.append({'title':title,'url':link,'published':published,'source':source,'importance':news_priority(title)})
 return sorted(items,key=lambda i:i['published'],reverse=True)[:8]

def fetch_news_feed(source,url):
 req=urllib.request.Request(url,headers={'User-Agent':'AIRI personal reader/1.0','Cache-Control':'no-cache'})
 with urllib.request.urlopen(req,timeout=10) as r:items=parse_news(r.read(1000000),source)
 if not items:raise ValueError('뉴스 피드가 비어 있습니다.')
 return items

def news(category='business',force=False):
 if category not in NEWS_FEEDS:raise ValueError('지원하지 않는 뉴스 분류입니다.')
 label,source,url=NEWS_FEEDS[category]
 with NEWS_LOCK:
  cached=NEWS_CACHE.get(category)
  if not force and cached and time.monotonic()-cached[0]<20:return dict(cached[1],cached=True)
 items=[];sources=[];failed=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  pending=[(name,pool.submit(fetch_news_feed,name,feed)) for name,feed in [(source,url)]+NEWS_SUPPLEMENTS[category]]
  for name,future in pending:
   try:items.extend(future.result());sources.append(name)
   except Exception:failed.append(name)
 if not items:
  if cached:return dict(cached[1],stale=True,error='연결 실패 · 이전 기사를 표시합니다.')
  raise ValueError('뉴스 제공처에 연결하지 못했습니다.')
 current=dt.datetime.now(dt.timezone.utc)
 unique={}
 for item in sorted(items,key=lambda i:i['published'],reverse=True):
  if not item['published']:continue
  age=(current-dt.datetime.fromisoformat(item['published'])).total_seconds()
  if not 0<=age<=86400:continue
  key=item['url'].split('?',1)[0]
  if key not in unique:unique[key]=item
 result={'category':category,'label':label,'source':' + '.join(sources),'source_url':url,'items':list(unique.values())[:10],'checked_at':current.isoformat(),'stale':False,'failed_sources':failed,'window_hours':24}
 with NEWS_LOCK:NEWS_CACHE[category]=(time.monotonic(),result)
 return result

def claim_news_briefing(app,current=None):
 """Existing alert UI now waits for a verified event assessment, asynchronously."""
 import hashlib,intelligence
 current=current or dt.datetime.now(dt.timezone.utc)
 candidates=[]
 with NEWS_LOCK:
  for loaded,data in NEWS_CACHE.values():
   if time.monotonic()-loaded>900:continue
   for item in data['items']:
    if item.get('importance') and item.get('published') and 0<=(current-dt.datetime.fromisoformat(item['published'])).total_seconds()<21600:candidates.append(item)
 if not candidates:return None
 with app.db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS news_briefings(url TEXT PRIMARY KEY,delivered TEXT NOT NULL)')
  recent=c.execute('SELECT MAX(delivered) FROM news_briefings').fetchone()[0]
  if recent and (current-dt.datetime.fromisoformat(recent)).total_seconds()<1800:return None
 key='breaking:'+str(int(current.timestamp()/1800))
 job=intelligence.request(app,'breaking',key=key)
 if job['state']!='completed':return None
 s=intelligence.store(app);saved=s.report(job['result_id'])
 if not saved:return None
 report=json.loads(saved['payload'])
 if (current-dt.datetime.fromisoformat(report['created'])).total_seconds()>21600:return None
 events=[e for e in report['events'] if e['confirmed_facts'] and e['classification'] in ('new','update')]
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE');c.execute('CREATE TABLE IF NOT EXISTS news_briefings(url TEXT PRIMARY KEY,delivered TEXT NOT NULL)')
  recent=c.execute('SELECT MAX(delivered) FROM news_briefings').fetchone()[0]
  if recent and (current-dt.datetime.fromisoformat(recent)).total_seconds()<1800:return None
  for event in events:
   identifier='intelligence:'+event['id']
   if c.execute('SELECT 1 FROM news_briefings WHERE url=?',(identifier,)).fetchone():continue
   source=next(s for s in report['sources'] if s['id']==event['source_ids'][0])
   c.execute('INSERT INTO news_briefings VALUES(?,?)',(identifier,current.isoformat()))
   text=event['confirmed_facts'][0]['text']
   return dict(title=event['event'],url=source['url'],source=source['source'],published=source['published'],importance='검증된 사건 · 신뢰도 '+event['confidence'],text=text,report=None)
 return None


def watchlist(app):
 return app.settings().get('watchlist',['^GSPTSE','^GSPC','O'])

def update_watchlist(app,body):
 symbol=body.get('symbol','')
 if not isinstance(symbol,str):raise ValueError('티커를 입력하세요.')
 symbol=symbol.strip().upper()
 if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=\-]{0,19}',symbol):raise ValueError('AAPL, O, RY.TO처럼 티커를 입력하세요.')
 action=body.get('action')
 if action not in ('add','remove'):raise ValueError('지원하지 않는 작업입니다.')
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute("SELECT value FROM settings WHERE key='watchlist'").fetchone()
  symbols=json.loads(row['value']) if row else ['^GSPTSE','^GSPC','O']
  if action=='add' and symbol not in symbols:
   if len(symbols)>=8:raise ValueError('관심 종목은 최대 8개까지 등록할 수 있습니다.')
   symbols.append(symbol)
  if action=='remove':symbols=[s for s in symbols if s!=symbol]
  c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('watchlist',json.dumps(symbols)))
 return {'symbols':symbols}
