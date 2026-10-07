"""Evidence validation, conservative event merging, source independence and ranking."""
import datetime as dt,hashlib,json,re
from .config import WEIGHTS,INTERESTS
from .retrieval import UTC,topics

def normalized(text):return re.sub(r'\s+',' ',str(text)).strip().casefold()
def terms(text):return set(re.findall(r'[a-z가-힣]{3,}',normalized(text)))-{'the','and','that','with','from','after','says','said','this','will','about','into','news'}
def similarity(a,b):
 a,b=terms(a),terms(b);return len(a&b)/max(1,len(a|b))
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
def numbers(text):return set(re.findall(r'(?<![a-zA-Z])[-+]?\d+(?:[,.]\d+)*(?:%|bp|bps)?',str(text)))
def quote_exists(quote,body):return 12<=len(quote)<=700 and normalized(quote) in normalized(body)

def date_in_quote(value,quote,published):
 if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\d',value):return None
 try:d=dt.date.fromisoformat(value)
 except ValueError:return None
 formats=[value,d.strftime('%B %d, %Y'),d.strftime('%b %d, %Y'),d.strftime('%d %B %Y'),f'{d.year}년 {d.month}월 {d.day}일']
 quote=normalized(quote).replace(' 0',' ')
 explicit=any(normalized(x).replace(' 0',' ') in quote for x in formats)
 # Relative expressions may be anchored only to a dated article, never to now.
 relative=published and value==published[:10] and bool(re.search(r'\btoday\b|오늘',quote))
 return {'date':value,'basis':'explicit' if explicit else 'relative_to_publication'} if explicit or relative else None

def validate_extraction(value,doc,now):
 if not isinstance(value,dict):raise ValueError('Extraction must be an object')
 facts=[]
 for item in (value.get('facts') or [])[:8]:
  if not isinstance(item,dict):continue
  text=str(item.get('text',''))[:600];quote=str(item.get('quote',''));key=normalized(item.get('key',''))[:180]
  if key.count('|')!=2:
   key=normalized((value.get('entities') or [doc['title']])[0])+'|'+key+'|'+str(value.get('timestamp') or 'unknown')
  if not text or not key or not quote_exists(quote,doc['body']) or not numbers(text)<=numbers(quote):continue
  # Preserve limiting negation; dropping it can reverse the meaning of a claim.
  if re.search(r'\b(?:not|never|without|non-sensitive)\b',quote,re.I) and not re.search(r'않|아니|없|비민감|제외|금지|불가|\b(?:not|never|without|non-sensitive)\b',text,re.I):continue
  # Structured keys align subject/metric/period; opposing values remain separate.
  facts.append(dict(id=doc['id']+'v'+doc['body_hash'][:8]+'f'+str(len(facts)),text=text,quote=quote,key=key,value=normalized(item.get('value',''))[:160],source_ids=[doc['id']],kind='reported'))
 date_quote=str(value.get('timestamp_quote',''))
 event_date=date_in_quote(value.get('timestamp'),date_quote,doc.get('published')) if quote_exists(date_quote,doc['body']) else None
 timestamp=event_date['date'] if event_date else None
 if timestamp and dt.date.fromisoformat(timestamp)>now.date()+dt.timedelta(days=1):timestamp=None;event_date=None
 raw_entities=value.get('entities') or []
 entities=[str(e)[:100] for e in raw_entities[:12] if isinstance(e,str) and normalized(e) in normalized(doc['body']+' '+doc['title'])]
 kind=value.get('kind','unknown')
 if kind not in ('development','update','background','opinion','unknown'):kind='unknown'
 if re.search(r'\b(opinion|commentary|editorial)\b|사설|칼럼',doc['title'],re.I):kind='opinion'
 if timestamp and (now.date()-dt.date.fromisoformat(timestamp)).days>2 and kind!='opinion':kind='background'
 return dict(event=doc['title'][:250],focus=str(value.get('event') or doc['title'])[:250],timestamp=timestamp,timestamp_basis=event_date['basis'] if event_date else 'unknown',entities=entities,facts=facts,source_ids=[doc['id']],topics=topics(doc['title']+' '+' '.join(f['quote'] for f in facts)),kind=kind,uncertainties=[],confidence='LOW')

def related(a,b):
 # Timeline relation is broader than event identity: investigations and a later
 # resignation can share context without being merged into one occurrence.
 ea={normalized(x) for x in a['entities']};eb={normalized(x) for x in b['entities']}
 common=ea&eb
 if not common:return False
 generic={'federal reserve board','federal reserve','bank of canada','bank of korea','united states','canada','south korea'}
 return bool(common-generic) or same_event(a,b)

def same_event(a,b):
 ea={normalized(x) for x in a['entities']};eb={normalized(x) for x in b['entities']}
 if not ea&eb:return False
 if a.get('timestamp') and b.get('timestamp') and a['timestamp']!=b['timestamp']:return False
 if (a['kind'] in ('background','opinion') or b['kind'] in ('background','opinion')) and a['kind']!=b['kind']:return False
 shared_keys={f['key'] for f in a['facts']}&{f['key'] for f in b['facts']}
 generic_metrics={'action','date','issue date','announcement time','decision','event','statement'}
 informative_keys={k for k in shared_keys if len(k.split('|'))==3 and k.split('|')[1].strip() not in generic_metrics}
 # Remove issuer names before comparing event actions. Two Fed releases on the
 # same day are not corroborating reports about the same event.
 left=a.get('focus',a['event']);right=b.get('focus',b['event'])
 for entity in sorted(ea|eb,key=len,reverse=True):
  left=re.sub(re.escape(entity),' ',left,flags=re.I);right=re.sub(re.escape(entity),' ',right,flags=re.I)
 generic_words=r'\b(announces?|announced|issues?|issued|board|statement|requests?|proposal|new)\b'
 left=re.sub(generic_words,' ',left,flags=re.I);right=re.sub(generic_words,' ',right,flags=re.I)
 return bool(informative_keys) or (len(terms(left)&terms(right))>=3 and similarity(left,right)>=.5)


def cluster(extractions,documents,history,now,profile,interests=None):
 docs={d['id']:d for d in documents};groups=[]
 for e in extractions:
  if not e['facts']:continue
  group=next((g for g in groups if all(same_event(e,member) for member in g)),None)
  if group is None:groups.append([e])
  else:group.append(e)
 events=[]
 for group in groups:
  e=dict(group[0]);e['facts']=[];e['source_ids']=sorted({s for x in group for s in x['source_ids']});e['entities']=sorted({s for x in group for s in x['entities']});e['topics']=sorted({s for x in group for s in x['topics']})
  claims={};contradictions=[]
  for x in group:
   for fact in x['facts']:
    # A shared metric key with a different value is retained as a disagreement.
    claims.setdefault(fact['key'],[]).append(fact)
  for key,items in claims.items():
   variants={}
   for f in items:variants.setdefault(f['value'] or normalized(f['text']),[]).append(f)
   if len(variants)>1:
    contradictions.append(dict(key=key,accounts=[{'text':f['text'],'source_ids':f['source_ids']} for f in items],resolution='Primary evidence does not automatically resolve differing periods/definitions.'))
   for identical in variants.values():
    f=dict(identical[0]);f['source_ids']=sorted({s for item in identical for s in item['source_ids']});f['evidence']=[{'source_id':item['source_ids'][0],'quote':item['quote']} for item in identical]
    primary=any(docs[s]['quality']['primary'] for s in f['source_ids']);independent={docs[s]['quality']['family'] for s in f['source_ids'] if docs[s]['quality']['tier']<=3 or docs[s]['quality'].get('trusted_journalism')}
    f['confirmed']=len(variants)==1 and e['kind'] not in ('opinion','background') and (primary or len(independent)>=2)
    e['facts'].append(f)
  e['source_records']=[{k:v for k,v in docs[s].items() if k!='body'} for s in e['source_ids']];e['contradictions']=contradictions;e['confirmed_facts']=[f for f in e['facts'] if f['confirmed']];e['quantitative_data']=[f for f in e['facts'] if numbers(f['text'])]
  e['uncertainties']=list(dict.fromkeys([s for x in group for s in x['uncertainties']]+(['Event time unverified; publication time is not event time.'] if not e['timestamp'] else [])+(['Reporting differs on this point.'] if contradictions else [])))
  e['confidence']='LOW' if contradictions or not e['confirmed_facts'] else 'HIGH' if len(e['confirmed_facts'])>=2 and e['timestamp'] else 'MEDIUM'
  prior=[h for h in history if related(e,h)]
  old_facts={(f['key'],f['value']) for h in prior for f in h['facts']}
  e['new_fact_ids']=[f['id'] for f in e['facts'] if (f['key'],f['value']) not in old_facts]
  e['classification']=e['kind'] if e['kind'] in ('opinion','background') else 'repeated' if prior and not e['new_fact_ids'] else 'update' if prior else 'new' if e['timestamp'] else 'event_time_unknown'
  e['timeline']=[{'event':h['event'],'timestamp':h.get('timestamp'),'id':h['id'],'facts':h['confirmed_facts'][:3]} for h in prior[-5:]]
  e['id']='e'+fingerprint([sorted((f['key'],f['value']) for f in e['facts']),e.get('timestamp')])
  quality=max((6-docs[s]['quality']['tier'] for s in e['source_ids']),default=1)
  significance=len(set(e['topics'])&{'monetary_policy','markets','geopolitics','energy','regulation','labour','supply_chains'})
  interests=interests or INTERESTS;corpus=' '.join(e['entities']+[e['event']]+e['topics']).lower()
  relevant=any(i.lower() in corpus for i in interests) or bool(set(e['topics'])&set(profile['topics']))
  isolated=bool(re.search(r'former employee|individual.*(?:fine|enforcement)|local.*(?:rink|arena)',e['event'],re.I))
  e['scores']=dict(impact=1 if isolated else min(5,2+significance),relevance=4 if relevant else 2,novelty=4 if e['classification']=='new' else 3 if e['classification']=='update' else 1,credibility=quality if e['confidence']!='LOW' else min(quality,2),persistence=min(5,2+len(prior)),urgency=4 if e['timestamp']==now.date().isoformat() and significance else 1)
  e['priority']=round(sum(e['scores'][k]*v for k,v in WEIGHTS.items()),3);events.append(e)
 return sorted(events,key=lambda e:e['priority'],reverse=True)

def topic_graph(events):
 edges=[]
 channels={frozenset(pair):label for pair,label in [
  (('AI','energy'),'AI infrastructure electricity demand'),
  (('monetary_policy','markets'),'financing and discount rates'),
  (('geopolitics','supply_chains'),'trade restrictions and supply availability'),
  (('regulation','technology'),'compliance and technology adoption'),
  (('energy','macroeconomics'),'input costs and inflation'),
  (('companies','labour'),'capital allocation and hiring')
 ]}
 for i,a in enumerate(events):
  for b in events[i+1:]:
   overlap=sorted(set(a['topics'])&set(b['topics']))
   possible=sorted({label for pair,label in channels.items() if any(x in a['topics'] and y in b['topics'] and x!=y for x in pair for y in pair)})
   if overlap or possible:edges.append({'from':a['id'],'to':b['id'],'topics':overlap,'possible_transmission':possible,'kind':'candidate_relationship_not_proven_causation'})
 return edges

def trend_support(event_ids,events,history):
 all_events={e['id']:e for e in history+events};selected=[all_events[x] for x in set(event_ids) if x in all_events and all_events[x].get('confirmed_facts')]
 dates={e.get('timestamp') for e in selected if e.get('timestamp')}
 return len(selected)>=3 and len(dates)>=2
