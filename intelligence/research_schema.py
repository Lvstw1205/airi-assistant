"""Research provenance and publication gates. A missing value is never zero."""
import hashlib,json,math
SCHEMA='airi-financial-research/3'
TAGS={'FACT','ANALYSIS','HYPOTHESIS','UNCERTAINTY'}
SIGNALS={'Positive Evidence','Negative Evidence','Mixed','Neutral','Insufficient Evidence'}
TIERS={1:'Primary / Official',2:'Exchange / Institutional Infrastructure',3:'Financial Data / Professional Secondary',4:'News / Aggregators'}

def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def ident(prefix,*parts):return prefix+hashlib.sha256(json.dumps(parts,sort_keys=True,default=str).encode()).hexdigest()[:16]
def source(url,name,tier,collected,kind='dataset',**extra):
 return dict(id=ident('ds',url),url=url,name=name,tier=tier,kind=kind,collected_at=collected,**extra)
def claim(text,refs,tag='ANALYSIS',**extra):
 return dict(id=ident('c',text,refs),tag=tag,text=text,evidence_ids=list(dict.fromkeys(refs)),**extra)
def confidence(facts,sources,contradictions=False):
 if contradictions or not facts:return 'Low'
 origins={s['id']:s for s in sources};primary=any(origins.get(s,{}).get('quality',{}).get('primary') for f in facts for s in f.get('source_ids',[]))
 families={origins[s]['quality']['family'] for f in facts for s in f.get('source_ids',[]) if s in origins and (origins[s]['quality']['tier']<=3 or origins[s]['quality'].get('trusted_journalism'))}
 confirmed=sum(bool(f.get('confirmed')) for f in facts)
 if not primary and len(families)<2:return 'Low'
 return 'High' if confirmed>=2 and (primary or len(families)>=2) else 'Medium'

def counts(ledger,included_ids):
 """Every successfully reviewed document is either included or excluded."""
 for row in ledger:
  if row.get('reviewed'):
   row['included']=row.get('source_id') in included_ids
   if row['included']:row['exclusion_reason']=None
   elif not row.get('exclusion_reason'):row['exclusion_reason']='No approved investment-relevant claim used in this report.'
 stats={'discovered_articles':len(ledger),'fetched_articles':sum(bool(x.get('fetched')) for x in ledger),'reviewed_articles':sum(bool(x.get('reviewed')) for x in ledger),'included_articles':sum(bool(x.get('reviewed') and x.get('included')) for x in ledger),'excluded_articles':sum(bool(x.get('reviewed') and not x.get('included')) for x in ledger),'failed_articles':sum(bool(x.get('failure')) for x in ledger),'source_count':len(included_ids)}
 return stats

def validate(report):
 r=report['research'];errors=[];pool=r['evidence'];sources={s['id'] for s in r['sources']};stats=r['article_counts'];ledger=r['article_ledger']
 if stats!=counts([dict(x) for x in ledger],set(r['included_source_ids'])):errors.append('Article accounting changed after editorial selection')
 if stats['reviewed_articles']!=stats['included_articles']+stats['excluded_articles']:errors.append('reviewed != included + excluded')
 if any(x.get('reviewed') and not x.get('included') and not x.get('exclusion_reason') for x in ledger):errors.append('Missing exclusion reason')
 if not set(r['included_source_ids'])<=sources:errors.append('Missing article citation')
 for key,fact in pool.items():
  if not fact.get('source_ids') or not set(fact['source_ids'])<=sources:errors.append('Dangling factual source: '+key)
 def walk(value):
  if isinstance(value,dict):
   if 'tag' in value and 'text' in value:
    if value['tag'] not in TAGS:errors.append('Unknown claim tag')
    refs=value.get('evidence_ids',[])
    if value['tag']=='FACT' and value.get('id') in pool and value.get('source_ids'):refs=[value['id']]
    if value['tag']!='UNCERTAINTY' and not refs:errors.append('Uncited substantive claim')
    if not set(refs)<=set(pool):errors.append('Dangling evidence reference')
   for v in value.values():walk(v)
  elif isinstance(value,list):
   for v in value:walk(v)
 walk(r['events']);walk(r['executive']);walk(r['company'])
 if r.get('synthesis'):
  syn=r['synthesis'];walk(syn)
  if syn.get('version')!='market-synthesis/1':errors.append('Unknown synthesis methodology')
  if len(syn.get('top_developments',[]))>3:errors.append('Too many top developments')
  for c in syn.get('cross_asset_read',[]):
   if c.get('status') not in ('CONFIRMED','CONSISTENT WITH','POSSIBLE','CONTRADICTED','UNVERIFIED'):errors.append('Unknown mechanism support status')
   if c.get('status')=='CONFIRMED' and not any(pool.get(f,{}).get('direct_causal_evidence') and pool[f].get('confirmed') for f in c.get('causal_evidence',[])):errors.append('Causality inferred from price co-movement')
   if not c.get('invalidation'):errors.append('Cross-asset view lacks invalidation')
   for w in c.get('windows',{}).values():
    if w.get('available') and (not w.get('start') or not w.get('end') or len(w.get('changes',[]))!=2 or not all(finite(v) for v in w['changes'])):errors.append('Invalid common-date comparison')
  for top in syn.get('top_developments',[]):
   if not top.get('invalidation') or not top.get('evidence_ids'):errors.append('Unsupported priority development')
  for item in syn.get('next_catalysts',[]):
   if item.get('date') and (item.get('date_status')!='Verified official schedule' or not item.get('evidence_ids')):errors.append('Unverified calendar date')
  for e in r['events']:
   if e.get('verification',{}).get('status')=='Confirmed' and not e['verification'].get('timing_verified'):errors.append('Publication time substituted for event time')
   for case in e.get('transmission_scenarios',[]):
    if not all(case.get(k) for k in ('trigger','transmission','assets','evidence_ids','invalidation')) or 'probability' in case:errors.append('Unsupported transmission scenario')
 company=r['company']
 if company.get('available'):
  for row in company['records']+company['derived']:
   if row.get('kind')!='Historical Actual' or not finite(row.get('value')):errors.append('Invalid actual financial value')
   if row.get('currency')!=company['currency']:errors.append('Mixed financial currencies')
   if not set(row.get('evidence_ids',[]))<=set(pool):errors.append('Dangling financial formula input')
  for row in company.get('expectations',[]):
   if row.get('kind') not in ('Company Guidance','Analyst Consensus'):errors.append('Expectation mislabeled as actual')
  for case in company.get('forecast',{}).get('cases',[]):
   if case.get('kind')!='Illustrative Scenario':errors.append('Forecast mislabeled')
   if abs(case['fcf']-(case['ocf']-case['capex']))>max(1,abs(case['fcf'])*1e-8):errors.append('Scenario cash-flow bridge does not reconcile')
 for card in r['events']:
  if card['relevance']=='F':errors.append('Irrelevant event reached publication')
  if card.get('analysis') and not card.get('invalidation'):errors.append('Unfalsifiable thesis')
  if card.get('signal') not in SIGNALS:errors.append('Unknown research signal')
 r['validation']={'ok':not errors,'errors':errors}
 if errors:raise ValueError('Research publication blocked: '+'; '.join(errors[:6]))
 return r['validation']
