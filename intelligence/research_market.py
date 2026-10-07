"""Timestamped free market observations and deterministic significance checks."""
import concurrent.futures as cf,datetime as dt,json,math,statistics,time,urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from .research_schema import finite,ident,source
ASSETS={
 'tsx':('^GSPTSE','S&P/TSX','index points','Canada'), 'sp500':('^GSPC','S&P 500','index points','US'),
 'nasdaq':('^IXIC','NASDAQ Composite','index points','US'),'dow':('^DJI','Dow','index points','US'),
 'wti':('CL=F','WTI futures','USD/barrel','global'),'brent':('BZ=F','Brent futures','USD/barrel','global'),
 'gold':('GC=F','Gold futures','USD/oz','global'),'natural_gas':('NG=F','Natural gas futures','USD/MMBtu','global'),
 'copper':('HG=F','Copper futures','USD/lb','global'),'vix':('^VIX','VIX','index points','US'),
 'us10y':('^TNX','US 10Y Treasury yield','percent','US'),'dxy':('DX-Y.NYB','US Dollar Index','index points','US')}
SECTORS={'Financials':'XFN.TO','Energy':'XEG.TO','Materials':'XMA.TO','Industrials':'XGI.TO','Technology':'XIT.TO','Utilities':'XUT.TO','Consumer staples':'XST.TO','Real Estate':'XRE.TO'}

def json_get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'AIRI local personal research/2.0','Accept':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=12) as r:return json.load(r)

def cached(root,key,ttl,load):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);p=root/(ident('',key)+'.json')
 try:
  data=json.loads(p.read_text())
  if time.time()-data['cached_at']<ttl:return data['value']
 except (OSError,ValueError,KeyError):pass
 value=load();tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'cached_at':time.time(),'value':value},allow_nan=False));tmp.replace(p);return value

def yf_series(symbol):
 import yfinance as yf
 frame=yf.Ticker(symbol).history(period='1y',interval='1d',auto_adjust=False,actions=False,timeout=12,raise_errors=True)
 rows=[]
 for stamp,row in frame.iterrows():
  if finite(float(row['Close'])):rows.append({'date':stamp.date().isoformat(),'value':float(row['Close']),'volume':float(row['Volume']) if finite(float(row.get('Volume',0))) and float(row.get('Volume',0))>0 else None})
 if not rows:raise ValueError('No timestamped daily observations')
 return rows

def describe(key,label,unit,rows,origin,now,kind='price',region=None):
 rows=sorted({r['date']:r for r in rows if r.get('date') and r['date']<=now.date().isoformat() and finite(r.get('value'))}.values(),key=lambda r:r['date'])
 if not rows:return {'key':key,'label':label,'available':False,'missing_reason':'No valid dated observations'}
 last=rows[-1];returns=[(100*(b['value']-a['value']) if kind=='yield' else 100*(b['value']/a['value']-1)) for a,b in zip(rows,rows[1:]) if kind=='yield' or a['value']>0]
 def change(n):
  if len(rows)<=n or (kind!='yield' and rows[-n-1]['value']==0):return None
  return (last['value']-rows[-n-1]['value'])*100 if kind=='yield' else 100*(last['value']/rows[-n-1]['value']-1)
 prior_year=[r for r in rows if r['date'][:4]<last['date'][:4]]
 vols=[r['volume'] for r in rows[-21:-1] if finite(r.get('volume')) and r['volume']>0]
 age=(now.date()-dt.date.fromisoformat(last['date'])).days
 market_now=now.astimezone(ZoneInfo('America/New_York'));partial=last['date']==market_now.date().isoformat() and market_now.hour<16 and region in ('US','Canada')
 daily=change(1);baseline=returns[-21:-1]
 item=dict(key=key,label=label,unit=unit,region=region,kind=kind,available=True,current=last['value'],previous=rows[-2]['value'] if len(rows)>1 else None,daily_change=daily,change_5d=change(5),change_20d=change(20),change_unit='bps' if kind=='yield' else '%',ytd_change=(((last['value']-prior_year[-1]['value'])*100 if kind=='yield' else 100*(last['value']/prior_year[-1]['value']-1)) if prior_year and prior_year[-1]['value'] else None),observed_at=last['date'],collected_at=origin['collected_at'],source_id=origin['id'],stale=age>4,partial_session=partial,volume=last.get('volume'),average_volume_20d=statistics.mean(vols) if len(vols)==20 else None,average_absolute_move_20d=statistics.mean(map(abs,baseline)) if len(baseline)==20 else None,realized_daily_volatility_20d=statistics.stdev(baseline) if len(baseline)==20 else None,history=rows[-260:])
 item['volume_ratio']=item['volume']/item['average_volume_20d'] if item.get('volume') and item.get('average_volume_20d') else None
 return item

def significance(item):
 missing=[]
 for k in ('daily_change','change_5d','change_20d','average_absolute_move_20d','realized_daily_volatility_20d','volume_ratio'):
  if item.get(k) is None:missing.append(k)
 if item.get('stale'):missing.append('fresh observations')
 if item.get('partial_session'):missing.append('complete-session volume')
 result={'classification':'Insufficient Evidence','missing':missing,'method':'Daily absolute move vs prior 20-session mean absolute move and sample standard deviation; completed-session volume / preceding 20-session average. Descriptive heuristic, not a statistical p-value.'}
 if missing:return result
 move=abs(item['daily_change']);avg=item['average_absolute_move_20d'];vol=item['realized_daily_volatility_20d']
 if move<=avg and move<=vol and item['volume_ratio']<=1.25:result['classification']='Normal Noise'
 elif move>=2*max(avg,vol) and item['volume_ratio']>=1.25:result['classification']='Unusual move; cause unverified'
 else:result['classification']='Mixed'
 return result

def collect(root,now=None,loader=None,get_json=None,official_fetch=None):
 now=now or dt.datetime.now(dt.timezone.utc);loader=loader or yf_series;get_json=get_json or json_get
 assets={};sources=[];failures=[];root=Path(root)
 jobs={k:(s,l,u,region,False) for k,(s,l,u,region) in ASSETS.items()}
 jobs.update({'sector_'+k:(s,k+' ETF proxy','CAD/share','Canada',True) for k,s in SECTORS.items()})
 def job(key,value):
  symbol,label,unit,region,proxy=value
  def retrieve():return {'rows':loader(symbol),'collected_at':dt.datetime.now(dt.timezone.utc).isoformat()}
  result=cached(root,'daily:'+symbol,900,retrieve)
  origin=source('https://finance.yahoo.com/quote/'+symbol+'/history/','Yahoo Finance · '+symbol,3,result['collected_at'],symbol=symbol)
  item=describe(key,label,unit,result['rows'],origin,now,'yield' if key=='us10y' else 'price',region);item['proxy']=proxy;item['symbol']=symbol
  if proxy:item['proxy_note']='Sector ETF price-return proxy; not official TSX sector return or index contribution. Distributions may affect price returns.'
  if symbol.endswith('=F'):item['instrument_note']='Front-month futures; rolling contracts can affect historical comparisons.'
  return key,item,origin
 with cf.ThreadPoolExecutor(max_workers=3) as pool:
  future={pool.submit(job,k,v):k for k,v in jobs.items()}
  for f in cf.as_completed(future):
   key=future[f]
   try:k,item,origin=f.result();assets[k]=item;sources.append(origin)
   except Exception as error:assets[key]={'key':key,'label':jobs[key][1],'available':False,'missing_reason':type(error).__name__};failures.append(key)
 # BoC yields and daily reference FX: primary observations, independently dated.
 for key,series,label,unit,invert in [('cadusd','FXUSDCAD','CAD/USD','USD per CAD',True),('ca10y','BD.CDN.10YR.DQ.YLD','Canada 10Y','percent',False),('ca2y','BD.CDN.2YR.DQ.YLD','Canada 2Y','percent',False),('ca3m','TB.CDN.90D.MID','Canada 3M bill yield','percent',False)]:
  url='https://www.bankofcanada.ca/valet/observations/'+series+'/json?start_date='+(now.date()-dt.timedelta(days=400)).isoformat()
  try:
   def retrieve():return {'raw':get_json(url),'collected_at':dt.datetime.now(dt.timezone.utc).isoformat()}
   raw=cached(root,'boc:'+series,1800,retrieve);rows=[]
   for r in raw['raw'].get('observations',[]):
    try:v=float(r[series]['v'])
    except (ValueError,KeyError,TypeError):continue
    if invert and v<=0:continue
    rows.append({'date':r['d'],'value':1/v if invert else v,'volume':None})
   origin=source(url,'Bank of Canada · '+series,1,raw['collected_at'],series=series)
   assets[key]=describe(key,label,unit,rows,origin,now,'fx' if invert else 'yield');sources.append(origin)
  except Exception as error:assets[key]={'key':key,'label':label,'available':False,'missing_reason':type(error).__name__};failures.append(key)
 assessment=significance(assets.get('tsx',{}));sector_rows=[a for k,a in assets.items() if k.startswith('sector_') and a.get('available') and a.get('daily_change') is not None and not a.get('stale')]
 aligned=[a for a in sector_rows if a.get('observed_at')==assets.get('tsx',{}).get('observed_at')]
 missing={'breadth':'No verified TSX constituent breadth feed connected.','advancers_decliners':'No verified TSX advancer/decliner counts connected.','index_contributors':'Constituent weights and matched-session returns not available.','official_sector_returns':'Only labeled ETF proxies are available.','macro_cause':'A dated announcement alone does not prove it caused the market move.'}
 result={'as_of':now.isoformat(),'assets':assets,'sources':sources,'significance':assessment,'market_character':'Normal Noise' if assessment['classification']=='Normal Noise' else 'Insufficient Evidence','market_character_reason':'Daily movement and broader market regime are evaluated separately in synthesis.','sector_proxies':{'top':max(aligned,key=lambda a:a['daily_change'])['key'] if aligned else None,'weakest':min(aligned,key=lambda a:a['daily_change'])['key'] if aligned else None},'missing':missing,'failures':failures,'macro_catalysts':[],'data_ledger':[{'series':k,'status':'included' if a.get('available') else 'failed','source_id':a.get('source_id'),'reason':a.get('missing_reason')} for k,a in assets.items()]}
 from .research_feeds import enrich_rates,catalysts,fetch
 enrich_rates(result,root,now,official_fetch or fetch);result['calendar']=catalysts(root,now,official_fetch or fetch)
 result['data_ledger']+=result['calendar']['ledger']
 return result

def evidence(market):
 result={}
 for key,a in market['assets'].items():
  if not a.get('available'):continue
  fields=['current','previous','daily_change','change_5d','change_20d','ytd_change','volume','volume_ratio','average_absolute_move_20d','realized_daily_volatility_20d']
  for field in fields:
   if a.get(field) is None:continue
   id=ident('m',key,field,a['observed_at']);text=f"{a['label']} {field}: {a[field]:.6g}; observation {a['observed_at']}; unit {a['unit'] if field in ('current','previous') else a['change_unit'] if 'change' in field or field in ('average_absolute_move_20d','realized_daily_volatility_20d') else 'count' if field=='volume' else 'ratio'}"
   result[id]={'id':id,'text':text,'quote':text,'source_ids':a.get('source_ids',[a['source_id']]),'tag':'FACT','confirmed':False,'basis':'dated_provider_observation','observation_time':a['observed_at'],'value':a[field],'metric':field,'asset':key,'stale':a['stale'],'partial_session':a['partial_session']}
 return result
