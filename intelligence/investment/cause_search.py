"""Dated article-body attribution with independent newsroom corroboration."""
import datetime as dt,re,hashlib
from zoneinfo import ZoneInfo
from ..retrieval import extract,quality
NAMES={'^GSPC':'S&P 500','^IXIC':'Nasdaq','^GSPTSE':'TSX','^KS11':'KOSPI','^N225':'Nikkei','^HSI':'Hang Seng','^GDAXI':'DAX','^FTSE':'FTSE','CL=F':'WTI crude oil','BZ=F':'Brent crude oil','GC=F':'gold','HG=F':'copper','us10y':'US Treasury 10 year yield','us2y':'US Treasury 2 year yield','ca10y':'Canada 10 year bond yield','ca2y':'Canada 2 year bond yield','BTC-USD':'Bitcoin','ETH-USD':'Ethereum'}
# Only explicit causal clauses qualify. Mere co-occurrence or snippets never count.
CAUSES=[('inflation',r'\b(?:inflation|CPI|consumer prices)\b','물가 발표 또는 물가 기대'),('rates',r'\b(?:rate cut|rate hike|interest rate decision|monetary policy)\b','통화정책 결정 또는 금리 기대'),('earnings',r'\b(?:earnings|profit forecast|profit outlook)\b','기업 실적 또는 이익 전망'),('tariffs',r'\b(?:tariff|trade restriction)\b','관세 또는 무역 제한'),('supply',r'\b(?:supply disruption|production cut|OPEC)\b','원유 공급 변화'),('jobs',r'\b(?:payroll|jobs report|employment report)\b','고용 발표'),('geopolitics',r'\b(?:war|ceasefire|military attack)\b','지정학 사건')]
MARKER=re.compile(r'\b(?:because|driven by|due to|on concerns|on fears|after|as investors|as traders|weighed on|boosted by|fuelled by|fueled by)\b',re.I)
def investigate(row,stats,search,fetch,now):
 name=NAMES.get(row['symbol'],row['symbol']);date=stats['date'];query=f'{name} {date} market move reason Reuters AP Bloomberg';result={'instrument_id':row['instrument_id'],'query':query,'date':date,'attempted':True,'status':'searched_no_match','sources':[],'evidence_ids':[],'fetch_ledger':[]}
 try:
  found=search(query,limit=6);result['search_provider']=found.get('provider');links=found.get('results',[])
 except Exception as error:
  result.update(status='search_failed',error=type(error).__name__,text=row['name']+'의 원인 검색이 실패해 원인 판정을 중단한다.');return result
 groups={};seen_hash=set()
 for hit in links[:6]:
  url=hit.get('url','');q=quality(url);entry={'url':url,'status':'excluded'};result['fetch_ledger'].append(entry)
  if not (q.get('trusted_journalism') or q.get('primary')):entry['reason']='untrusted outlet';continue
  try:doc=extract({**hit,'source':q['family'],'published':None},fetch,now)
  except Exception as error:entry['reason']=type(error).__name__;continue
  if not doc['published']:entry['reason']='publication date absent';continue
  published=dt.datetime.fromisoformat(doc['published']).astimezone(ZoneInfo(row['timezone'])).date().isoformat()
  if published!=date:entry['reason']='not same market date';continue
  if doc['body_hash'] in seen_hash:entry['reason']='duplicate article body';continue
  seen_hash.add(doc['body_hash']);family=doc['quality']['family']
  # Exact dated asset identity must occur in the clause, not somewhere else on the page.
  asset=re.compile(re.escape(name),re.I)
  match=None
  for sentence in re.split(r'(?<=[.!?])\s+|\n',doc['body']):
   if not MARKER.search(sentence) or not asset.search(sentence):continue
   for key,pattern,label in CAUSES:
    if re.search(pattern,sentence,re.I):match=(key,label,sentence[:1200]);break
   if match:break
  if not match:entry['reason']='no explicit attributable clause';continue
  key,label,excerpt=match;sid='news'+hashlib.sha256(doc['url'].encode()).hexdigest()[:18]
  ev={'id':sid,'kind':'announcement','provider':doc['source'],'source_url':doc['url'],'retrieved_at':doc['retrieved'],'published_at':doc['published'],'author':doc.get('author'),'description':doc['title'],'quality_status':'delayed','body_hash':doc['body_hash'],'family':family,'supporting_clause':excerpt,'cause_key':key,'instrument_id':row['instrument_id']}
  result['sources'].append(ev);groups.setdefault(key,{}).setdefault(family,(sid,label));entry.update(status='included',family=family,source_id=sid)
 if groups:
  key,families=max(groups.items(),key=lambda item:len(item[1]));selected=list(families.values());result['evidence_ids']=[x[0] for x in selected];label=selected[0][1]
  if len(selected)>=2:result.update(status='confirmed',text=f'{date}의 독립 보도 {len(selected)}건은 {row["name"]} 움직임의 공통 배경으로 {label}를 제시한다.')
  else:result.update(status='candidate',text=f'원인 후보: {date} 보도 1건이 {row["name"]} 움직임을 {label}와 연결하며 신뢰도는 low다.')
 else:result['text']=f'{row["name"]}는 {date} 뉴스 검색과 본문 확인 뒤에도 같은 날의 적합한 원인 보도를 확보하지 못해 원인 미확인으로 남긴다.'
 return result
