"""Free official rates and dated calendars. Failures are data, not invented dates."""
import datetime as dt,re,urllib.request,xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from .research_schema import source,finite
from .research_market import cached,describe
UTC=dt.timezone.utc
TREASURY='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
BOC='https://www.bankofcanada.ca/press/upcoming-events/'
BLS='https://www.bls.gov/schedule/news_release/bls.ics'
FED='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'

def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'AIRI personal research contact local user','Accept':'text/html,application/xml,text/calendar,*/*'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as r:return r.read(4000000).decode('utf-8','replace')

def treasury_rows(raw):
 out={k:[] for k in ('us2y','us10y','us3m','us_real10y')}
 fields={'BC_2YEAR':'us2y','BC_10YEAR':'us10y','BC_3MONTH':'us3m','TC_10YEAR':'us_real10y'}
 for entry in ET.fromstring(raw).iter():
  if entry.tag.rsplit('}',1)[-1]!='properties':continue
  d={x.tag.rsplit('}',1)[-1]:x.text for x in entry};date=(d.get('NEW_DATE') or '')[:10]
  try:dt.date.fromisoformat(date)
  except ValueError:continue
  for field,key in fields.items():
   try:value=float(d[field])
   except (KeyError,TypeError,ValueError):continue
   if finite(value):out[key].append({'date':date,'value':value,'volume':None})
 return out

def enrich_rates(market,root,now,get=fetch):
 """Primary nominal rates replace the secondary 10Y quote only on success."""
 ledger=market.setdefault('data_ledger',[])
 for kind in ('daily_treasury_yield_curve','daily_treasury_real_yield_curve'):
  rows={};origins=[]
  for year in (now.year-1,now.year):
   url=TREASURY+'?data='+kind+'&field_tdr_date_value='+str(year)
   entry={'url':url,'kind':'official_rates','status':'failed'};ledger.append(entry)
   try:
    value=cached(root,kind+str(year),3600,lambda:{'raw':get(url),'collected_at':dt.datetime.now(UTC).isoformat()})
    parsed=treasury_rows(value['raw']);src=source(url,'US Treasury · '+kind+' '+str(year),1,value['collected_at'])
    origins.append(src)
    for k,v in parsed.items():rows.setdefault(k,[]).extend(v)
    entry.update(status='included',source_id=src['id'])
   except Exception as error:entry['reason']=type(error).__name__+(' '+str(error.code) if getattr(error,'code',None) else '')
  for key,history in rows.items():
   if not history:continue
   origin=origins[-1];label={'us2y':'US 2Y','us10y':'US 10Y','us3m':'US 3M','us_real10y':'US 10Y real yield'}[key]
   item=describe(key,label,'percent',history,origin,now,'yield');item.update(source_ids=[s['id'] for s in origins],instrument_type='Treasury par real yield' if 'real' in key else 'Treasury par yield',source_tier=1)
   if item.get('available'):market['assets'][key]=item
  market['sources'].extend(origins)
 for key in ('us2y','us3m','us_real10y'):
  market['assets'].setdefault(key,{'key':key,'label':key,'available':False,'missing_reason':'Official Treasury feed unavailable'})
 return market

def calendar_item(name,date,origin,country,time=None):
 rates=bool(re.search(r'rate|FOMC|policy',name,re.I))
 return {'id':origin['id']+':'+str(date)+':'+name,'event':name,'date':date,'time':time,'timezone':('America/Toronto' if country=='CA' else 'America/New_York') if time else None,'country':country,'date_status':'Verified official schedule' if date else 'Date Not Verified','source_id':origin['id'],'evidence_ids':[], 'consensus':None,'previous':None,'why_it_matters':'금리 경로와 할인율·통화의 다음 관측치다. 발표 결과나 가격 반응은 아직 관측되지 않았다.' if rates else '물가·고용·성장 판단을 갱신할 관측치다. 발표 전 방향이나 서프라이즈를 가정하지 않는다.','assets':['CAD','Canadian yields','TSX'] if country=='CA' else ['US yields','USD','US equities','CAD'],'collected_at':origin['collected_at']}

def parse_bls(raw,origin):
 raw=re.sub(r'\r?\n[ \t]','',raw);items=[]
 for block in raw.split('BEGIN:VEVENT')[1:]:
  lines=block.split('END:VEVENT')[0].splitlines();fields={line.split(':',1)[0]:line.split(':',1)[1] for line in lines if ':' in line}
  title=fields.get('SUMMARY','').replace('\\,',',');start=next(((k,v) for k,v in fields.items() if k.startswith('DTSTART')),None)
  if not start or not re.search('Consumer Price|Employment Situation|Producer Price|Employment Cost',title,re.I):continue
  k,v=start
  try:
   if len(v)==8:date=dt.datetime.strptime(v,'%Y%m%d').date().isoformat();time=None
   else:
    parsed=dt.datetime.strptime(v.rstrip('Z'),'%Y%m%dT%H%M%S')
    if v.endswith('Z'):parsed=parsed.replace(tzinfo=UTC).astimezone(ZoneInfo('America/New_York'))
    elif 'TZID=America/New_York' not in k and 'TZID=US/Eastern' not in k:continue
    date=parsed.date().isoformat();time=parsed.strftime('%H:%M')
   items.append(calendar_item(title,date,origin,'US',time))
  except ValueError:continue
 return items

def parse_boc(raw,origin):
 soup=BeautifulSoup(raw,'html.parser');items=[]
 for heading in soup.find_all(['h2','h3']):
  name=heading.get_text(' ',strip=True)
  if not re.search('Interest Rate Announcement|Business Outlook|Consumer Expectations|Market Participants',name,re.I):continue
  # Locate the enclosing event card; never borrow a date from a neighbouring event.
  card=heading.parent
  for _ in range(4):
   text=card.get_text(' ',strip=True)
   dates=re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})',text)
   if len(dates)==1:break
   if len(dates)>1 or card.parent is None:dates=[];break
   card=card.parent
  if not dates:continue
  month,day,year=dates[0];date=dt.datetime.strptime(f'{month} {day} {year}','%B %d %Y').date().isoformat()
  clock=re.search(r'\b(\d{2}:\d{2})\s*\(ET\)',text)
  event_time=clock[1] if clock else None
  if year=='2026' and 'Interest Rate Announcement' in name:event_time='09:45'
  items.append(calendar_item(name,date,origin,'CA',event_time))
 return items

def parse_fed(raw,origin):
 soup=BeautifulSoup(raw,'html.parser');items=[]
 for panel in soup.select('div.panel'):
  h=panel.select_one('.panel-heading');match=re.search(r'(20\d{2})\s+FOMC',h.get_text(' ',strip=True) if h else '')
  if not match:continue
  for meeting in panel.select('.fomc-meeting'):
   month=meeting.select_one('.fomc-meeting__month');day=meeting.select_one('.fomc-meeting__date')
   if month is None or day is None:continue
   months=month.get_text(' ',strip=True).split('/');days=re.findall(r'\d+',day.get_text(' ',strip=True))
   if not days:continue
   try:date=dt.datetime.strptime(f'{months[-1]} {days[-1]} {match[1]}','%B %d %Y').date().isoformat()
   except ValueError:continue
   items.append(calendar_item('FOMC meeting conclusion (decision time not verified)',date,origin,'US'))
 return items

def catalysts(root,now,get=fetch):
 result={'items':[],'sources':[],'ledger':[]}
 for url,name,parser in [(BOC,'Bank of Canada calendar',parse_boc),(BLS,'BLS release calendar',parse_bls),(FED,'Federal Reserve FOMC calendar',parse_fed)]:
  row={'url':url,'kind':'calendar','status':'failed'};result['ledger'].append(row)
  try:
   value=cached(root,'calendar:'+url,21600,lambda:{'raw':get(url),'collected_at':dt.datetime.now(UTC).isoformat()});origin=source(url,name,1,value['collected_at'],kind='calendar')
   entries=parser(value['raw'],origin)
   if not entries:raise ValueError('No verified dated entries parsed')
   result['sources'].append(origin);row.update(status='included',source_id=origin['id'])
   result['items'] += [e for e in entries if now.date()<=dt.date.fromisoformat(e['date'])<=now.date()+dt.timedelta(days=100)]
  except Exception as error:row['reason']=type(error).__name__+(' '+str(error.code) if getattr(error,'code',None) else '')
 result['items']=sorted({(x['event'],x['date']):x for x in result['items']}.values(),key=lambda x:x['date'])[:16]
 result['missing']=['Canadian CPI/GDP and company earnings: Date Not Verified unless present in independently verified event evidence.','Calendar consensus and previous values are not supplied by these official schedule feeds.']
 return result
