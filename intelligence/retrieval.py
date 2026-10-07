"""Article bodies and provenance. RSS is discovery, never sufficient evidence."""
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from .config import FEEDS,TIERS,TOPICS
UTC=dt.timezone.utc

def timestamp(value):
 if not isinstance(value,str) or not value:return None
 try:d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
 except ValueError:
  try:d=parsedate_to_datetime(value)
  except (ValueError,TypeError,OverflowError):return None
 # A missing timezone is not silently converted to UTC.
 if d.tzinfo is None:return None
 return d.astimezone(UTC).isoformat()

def canonical_url(url):
 p=urlsplit(url)
 if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('Public HTTPS article required')
 query=[(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_','fbclid','gclid','mc_'))]
 return urlunsplit(('https',p.netloc.lower(),p.path or '/',urlencode(query),''))

def quality(url):
 host=(urlsplit(url).hostname or '').removeprefix('www.')
 for tier,domains in TIERS.items():
  for domain in domains:
   if host==domain or host.endswith('.'+domain):return {'tier':tier,'family':domain,'primary':tier==1,'reviewed':True,'trusted_journalism':domain in __import__(__package__+'.config',fromlist=['TRUSTED_JOURNALISM']).TRUSTED_JOURNALISM,'source_policy':'source-hierarchy/2'}
 return {'tier':4,'family':host,'primary':False,'reviewed':False}

def topics(text):return [name for name,pattern in TOPICS.items() if re.search(pattern,text,re.I)]

def parse_feed(raw,source,tags):
 root=ET.fromstring(raw);items=[]
 for row in list(root.findall('.//item'))+list(root.findall('.//{http://www.w3.org/2005/Atom}entry')):
  def find(name):
   return row.findtext(name) or row.findtext('{http://www.w3.org/2005/Atom}'+name) or ''
  link=find('link')
  if not link:
   links=row.findall('{http://www.w3.org/2005/Atom}link');link=next((x.get('href','') for x in links if x.get('rel','alternate')=='alternate'),'')
  try:url=canonical_url(link.strip())
  except (ValueError,TypeError):continue
  title=html.unescape(re.sub('<[^>]+>',' ',find('title'))).strip()
  published=timestamp(find('pubDate') or find('published') or find('updated'))
  if title:items.append(dict(url=url,title=title,published=published,source=source,topics=tags,description=html.unescape(re.sub('<[^>]+>',' ',find('description') or find('summary')))[:1000]))
 return items

class ArticleParser(HTMLParser):
 def __init__(self):
  super().__init__();self.stack=[];self.body=[];self.article=[];self.title=[];self.meta={};self.jsonld=[];self.script=[];self.in_json=False;self.skip=0;self.byline=''
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='meta':self.meta[a.get('property') or a.get('name') or '']=a.get('content','')
  if tag=='script' and a.get('type')=='application/ld+json':self.in_json=True;self.script=[]
  if tag in ('script','style','nav','footer','header','noscript','svg'):self.skip+=1
  if tag not in ('meta','link','img','br','input','hr','source','wbr'):self.stack.append(tag)
  if tag in ('p','h1','h2','h3','li','tr','br'):self.body.append('\n');self.article.append('\n')
 def handle_endtag(self,tag):
  if tag=='script' and self.in_json:
   try:self.jsonld.append(json.loads(''.join(self.script)))
   except ValueError:pass
   self.in_json=False
  if tag in ('script','style','nav','footer','header','noscript','svg') and self.skip:self.skip-=1
  if tag in self.stack:self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
 def handle_data(self,data):
  if self.in_json:self.script.append(data)
  if self.stack and self.stack[-1]=='title':self.title.append(data)
  if not self.skip:
   self.body.append(data)
   if 'article' in self.stack or 'main' in self.stack:self.article.append(data)
 def records(self):
  def walk(value):
   if isinstance(value,dict):
    yield value
    for v in value.values():yield from walk(v)
   elif isinstance(value,list):
    for v in value:yield from walk(v)
  return list(walk(self.jsonld))
 def result(self):
  rows=self.records();article=next((r for r in rows if r.get('articleBody')), {})
  metadata=next((r for r in rows if r.get('datePublished')),article)
  value=article.get('articleBody') or '\n'.join(self.article)
  if len(re.sub(r'\s','',value))<250:value='\n'.join(self.body)
  value=html.unescape(re.sub(r'[ \t]+',' ',value));value=re.sub(r'\n\s*\n+','\n',value).strip()
  title=article.get('headline') or self.meta.get('og:title') or ''.join(self.title)
  author=metadata.get('author') or self.meta.get('author','')
  return dict(body=value,title=title,published=timestamp(metadata.get('datePublished') or self.meta.get('article:published_time','')),modified=timestamp(metadata.get('dateModified') or self.meta.get('article:modified_time','')),author=str(author)[:500],paywall=metadata.get('isAccessibleForFree') in (False,'false'))

def extract(row,fetch,now,limit=14000):
 raw,resolved,truncated=fetch(row['url']);parser=ArticleParser();parser.feed(raw);data=parser.result();url=canonical_url(resolved)
 if not data['published'] and urlsplit(url).path in ('/','/news','/news/') and re.search(r'news|stock market|tsx today',data['title'],re.I):raise ValueError('Listing page is not a dated article')
 body=data['body'];blocked=re.search(r'access denied|enable javascript and cookies to continue|verify you are human|just a moment\.\.\.',data['title'],re.I)
 if blocked or data['paywall'] or len(body)<350:raise ValueError('Body unavailable, incomplete, or paywalled')
 published=data['published'] or row.get('published')
 q=quality(url)
 # Wire byline/republication is not an independent corroborating source.
 attribution=(data['author']+' '+body[:800]).lower()
 if re.search(r'by reuters|©.{0,20}reuters|copyright.{0,20}reuters|the associated press|by associated press',attribution):q['family']='reuters.com' if 'reuters' in attribution else 'apnews.com';q['syndicated']=True
 digest=hashlib.sha256(re.sub(r'\s+',' ',body).encode()).hexdigest()
 return dict(id='s'+hashlib.sha256((url+'#'+digest).encode()).hexdigest()[:14],url=url,title=data['title'] or row['title'],source=row.get('source') or q['family'],published=published,modified=data['modified'],retrieved=now.isoformat(),body=body[:limit],partial=truncated or len(body)>limit,body_hash=digest,quality=q,topics=sorted(set(row.get('topics',[])+topics(body))),evidence_type='article_body',author=data['author'])

def collect(profile,options,now,fetch,search,progress=lambda x:None,seeds=None):
 warnings=[];rows=list(seeds or [])
 selected=[f for f in FEEDS if not profile['topics'] or set(f[2])&set(profile['topics']) or f[0]=='BBC World']
 if seeds is None:
  def feed(entry):name,url,tags=entry;raw,_,_=fetch(url);return parse_feed(raw,name,tags)
  with cf.ThreadPoolExecutor(max_workers=4) as pool:
   futures={pool.submit(feed,f):f[0] for f in selected}
   for f in cf.as_completed(futures):
    try:rows.extend(f.result())
    except Exception:warnings.append('Feed unavailable: '+futures[f])
  # A company brief searches only the explicit public company/topic name.
  if options.get('company'):
   try:rows.extend(dict(r,source=quality(r['url'])['family'],published=None,topics=['companies']) for r in search(options['company'][:120]+' investor relations latest release',limit=4)['results'])
   except Exception:warnings.append('Company search unavailable')
 if seeds is None and options.get('search_terms'):
  # Explicit topics replace broad feed candidates; unrelated headlines cannot hijack a report.
  rows=[]
  try:
   rows=[dict(r,source=quality(r['url'])['family'],published=None,topics=profile['topics']) for r in search(options['search_terms']+' latest official news',limit=12)['results']]
  except Exception:warnings.append('Requested topic search unavailable')
 cutoff=now-dt.timedelta(hours=profile['hours']);unique={}
 for row in rows:
  try:u=canonical_url(row['url'])
  except (ValueError,KeyError):continue
  published=timestamp(row.get('published'))
  if published and not cutoff<=dt.datetime.fromisoformat(published)<=now+dt.timedelta(minutes=5):continue
  row=dict(row,url=u,published=published);unique.setdefault(u,row)
 # Balance sources so one prolific feed cannot monopolize coverage.
 if options.get('company'):
  company=options['company'].casefold();unique={u:r for u,r in unique.items() if company in (r.get('title','')+' '+r.get('description','')+' '+u).casefold()}
 def rank(row):
  subject=row.get('title','')+' '+row.get('description','');tags=topics(subject)
  relevance=len(set(tags)&{'macroeconomics','monetary_policy','markets','AI','technology','energy','geopolitics','regulation','labour','supply_chains'})
  canada_focus=bool(re.search(r'캐나다|Canada|Canadian|TSX',options.get('query',''),re.I))
  local_priority=1.5 if canada_focus and 'Canada' in row.get('topics',[]) else 0
  return (quality(row['url'])['tier']-.5*min(3,relevance)-local_priority,-dt.datetime.fromisoformat(row['published']).timestamp() if row.get('published') else 0)
 ledger={u:dict(url=u,title=r.get('title',''),discovered=True,fetched=False,reviewed=False,included=False,exclusion_reason='Not selected within retrieval budget') for u,r in unique.items()}
 ranked=sorted(unique.values(),key=rank)
 candidates=[];families={}
 for row in ranked:
  family=quality(row['url'])['family']
  if families.get(family,0)>=3:continue
  families[family]=families.get(family,0)+1;candidates.append(row)
 articles=[];attempted=0;failures={}
 # Backfill unreadable/paywalled discoveries from other sources. Stop retrying
 # a blocked publisher during this run instead of exhausting the whole window.
 remaining=candidates[:options['max_articles']*3]
 while remaining and len(articles)<options['max_articles'] and attempted<options['max_articles']*2:
  batch=[]
  while remaining and len(batch)<min(4,options['max_articles']-len(articles)):
   row=remaining.pop(0)
   if failures.get(quality(row['url'])['family'],0)<2:batch.append(row)
  if not batch:break
  attempted+=len(batch)
  with cf.ThreadPoolExecutor(max_workers=4) as pool:
   futures={pool.submit(extract,r,fetch,now,options['article_chars']):r for r in batch}
   for f in cf.as_completed(futures):
    try:
     doc=f.result();record=ledger[futures[f]['url']];record.update(fetched=True,source_id=doc['id'],exclusion_reason=None);pub=timestamp(doc['published'])
     if pub and not cutoff<=dt.datetime.fromisoformat(pub)<=now+dt.timedelta(minutes=5):
      record['exclusion_reason']='Publication outside coverage window';continue
     articles.append(doc)
    except Exception:
     row=futures[f];family=quality(row['url'])['family'];failures[family]=failures.get(family,0)+1
     ledger[row['url']].update(failure='Article body unavailable, blocked or paywalled',exclusion_reason='Fetch failed')
     warnings.append('Article body not reviewed: '+row['url'])
 seen={};dedup=[]
 for doc in sorted(articles,key=lambda d:(d['quality']['tier'],d['url'])):
  if doc['body_hash'] in seen:
   seen[doc['body_hash']].setdefault('duplicate_urls',[]).append(doc['url'])
   for row in ledger.values():
    if row.get('source_id')==doc['id']:row.update(reviewed=True,exclusion_reason='Identical article body / syndication')
  else:seen[doc['body_hash']]=doc;dedup.append(doc)
 # Near-verbatim syndication cannot manufacture source independence. Keep each
 # document for differences but assign copied reports to one evidence family.
 shingles=[]
 for doc in dedup:
  tokens=re.findall(r'\w+',doc['body'].casefold())[:3000]
  grams={' '.join(tokens[i:i+5]) for i in range(len(tokens)-4)}
  for prior,other in shingles:
   if min(len(grams),len(other))>=80 and len(grams&other)/min(len(grams),len(other))>=.88:
    doc['quality']['family']=prior['quality']['family'];doc['quality']['syndicated']=True;break
  shingles.append((doc,grams))
 progress('Collected '+str(len(dedup))+' article bodies')
 return dedup,warnings,{'discovered':len(unique),'attempted':attempted,'reviewed':len(dedup),'duplicate_bodies':len(articles)-len(dedup),'article_ledger':list(ledger.values())}
