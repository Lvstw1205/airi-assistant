"""Shared executive intelligence service for AIRI UI, chat and Telegram."""
import datetime as dt,hashlib,json,re,threading,time,uuid
from .config import PROFILES,DEFAULTS
from .store import Store
from .pipeline import build,normalize_options
from .retrieval import UTC
_LOCK=threading.RLock();_stores={};_threads={}

def settings(app):
 path=app.ROOT/'config/intelligence.json'
 try:value=json.loads(path.read_text())
 except (OSError,ValueError):value={}
 return normalize_options(value)

def store(app):
 key=str(app.DATA.resolve())
 with _LOCK:
  if key not in _stores:
   _stores[key]=Store(app.DATA/'news-intelligence');_stores[key].recover()
  return _stores[key]

def public_job(row):return {k:row.get(k) for k in ('id','profile','state','progress','created','updated','result_id','error')}

def publish(app,job,text):
 options=json.loads(job['options']);destination=options.get('_destination')
 if not destination:return
 # Local message and delivery receipt are one transaction. Telegram outbox keys
 # are durable too, so a crash/retry cannot double-send a report.
 with app.db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS intelligence_delivery(job_id TEXT PRIMARY KEY,created TEXT)')
  c.execute('BEGIN IMMEDIATE')
  existed=c.execute('SELECT 1 FROM intelligence_delivery WHERE job_id=?',(job['id'],)).fetchone()
  if not existed:
   c.execute('INSERT INTO messages(session,role,content,created) VALUES(?,?,?,?)',('main','assistant',text,app.now()))
   c.execute('INSERT INTO intelligence_delivery VALUES(?,?)',(job['id'],app.now()))
 if destination=='telegram':
  cfg=app.telegram_bridge.config(app)
  if cfg.get('enabled') and cfg.get('generation')==options.get('_generation'):
   import report_service
   artifact=report_service.find(app,job['id'])
   app.telegram_bridge.enqueue(app,cfg,'intelligence:'+job['id'],text,{'analysis_report_id':artifact['id']} if artifact else None)

def ensure_worker(app):
 key=str(app.DATA.resolve());s=store(app)
 import report_service
 if report_service.MOUNT.is_mount():
  with s.db() as c:c.execute("UPDATE jobs SET state='queued',progress='NAS 저장 재시도' WHERE state='waiting_storage'")
 with _LOCK:
  if key in _threads and _threads[key].is_alive():return
  def work():
   import report_service
   while True:
    with _LOCK:
     job=s.next_job()
     if not job:_threads.pop(key,None);return
    try:
     options=json.loads(job['options']);saved=s.report(job['result_id']) if job.get('result_id') else None
     if saved:report,text=json.loads(saved['payload']),saved['text']
     else:
      from .priority import background_model
      report,text=build(s,job['profile'],options,model=background_model(app,options,lambda value:s.update(job['id'],progress=value)),progress=lambda value:s.update(job['id'],progress=value))
     if report.get('professional_research') and not report.get('final'):
      import research_desk.service
      if report['status'] in ('awaiting_approval','awaiting_continue','needs_sources'):
       publish(app,job,research_desk.service.notice(report))
      s.update(job['id'],result_id=report['id'],state='completed',progress=report['status'])
      continue
     s.update(job['id'],result_id=report['id'],progress='NAS PDF 저장 중')
     import report_service
     artifact=report_service.publish(app,job,report,text,auto_read=options.get('_destination') in ('web','telegram') or job['profile']!='breaking')
     if report.get('professional_research'):
      from research_desk import core as desk_core
      record=desk_core.get(s,report['professional_research']['id']);record['payload']['artifact']=artifact
      desk_core.save(s,record)
     publish(app,job,report_service.notice(artifact))
     s.update(job['id'],state='completed',progress='Complete' if report['status']=='complete' else 'Complete with evidence limits')
     app.event('news','Intelligence brief ready · '+job['profile']+' · '+str(len(report['events']))+' events')
    except report_service.NASUnavailable as error:
     s.update(job['id'],state='waiting_storage',error=str(error),progress='NAS 연결 대기 · 분석 결과 보관됨')
    except Exception as error:
     if options.get('_research_id'):
      try:
       from research_desk import core as desk_core
       current=desk_core.get(s,options['_research_id'])
       if current['state']!='cancelled':
        current['payload']['error']=str(error)[:350];current['payload']['progress']='Research requires attention before publication';desk_core.save(s,current,state='failed')
      except Exception:pass
     s.update(job['id'],state='failed',error=type(error).__name__+': '+str(error)[:200],progress='Failed')
     try:publish(app,{**job,'id':job['id']+':failure'},'AIRI INTELLIGENCE BRIEF\n브리핑을 완성하지 못했어. '+str(error)[:180]+'\n확인되지 않은 최신 뉴스로 대체하지 않았어.')
     except Exception:pass
  thread=threading.Thread(target=work,name='airi-intelligence',daemon=True);_threads[key]=thread;thread.start()

def request(app,profile='morning',options=None,key=None,destination=None,generation=None,force=False):
 if profile not in PROFILES:raise ValueError('지원하는 브리핑 종류를 선택하세요.')
 import research_desk
 if research_desk.is_research(profile,options or {}):
  return research_desk.start(app,{**settings(app),**(options or {}),**({'request_id':key} if key else {})},destination,generation)
 opts=settings(app);opts.update(options or {});opts=normalize_options(opts)
 if profile=='company' and not opts.get('company'):raise ValueError('기업 브리핑에는 기업명이 필요합니다.')
 if destination:opts['_destination']=destination
 if generation:opts['_generation']=generation
 s=store(app)
 if not key:
  digest=hashlib.sha256(json.dumps([profile,opts],sort_keys=True).encode()).hexdigest()[:20]
  key='request:'+digest+':'+(uuid.uuid4().hex if force else str(int(time.time()/1800)))
 job=s.enqueue(profile,opts,key)
 import report_service
 missing_pdf=job['state']=='completed' and job.get('result_id') and not report_service.find(app,job['result_id'])
 if missing_pdf or (job['state']=='failed' and job.get('result_id')):
  s.update(job['id'],state='queued',error=None,progress='Retrying delivery');job=s.job(job['id'])
 ensure_worker(app);return public_job(job)

def status(app,id=None,profile=None):
 s=store(app);ensure_worker(app)
 if id:
  row=s.job(id)
  if not row:raise ValueError('브리핑 작업을 찾지 못했습니다.')
  result=public_job(row)
  if row['result_id']:
   report=s.report(row['result_id'])
   import report_service
   artifact=report_service.find(app,row['result_id']);result['artifact']=artifact
   result['text']=report_service.notice(artifact) if artifact else 'PDF 준비 중'
   result['report']=summary(json.loads(report['payload'])) if report else None
   if report and json.loads(report['payload']).get('professional_research') and not artifact:
    from research_desk.service import notice
    result['text']=notice(json.loads(report['payload']))
  return result
 report=s.report(profile=profile)
 import report_service
 artifact=report_service.find(app,report['id']) if report else None
 return {'profiles':{k:v['label'] for k,v in PROFILES.items()},'latest':{'text':report_service.notice(artifact) if artifact else 'PDF 형식으로 새 분석을 요청해 줘.','artifact':artifact,'report':summary(json.loads(report['payload']))} if report else None}

def summary(report):
 result={k:report.get(k) for k in ('id','profile','created','window_start','coverage','status','model','qc','limitations','delivery_style')}
 if report.get('professional_research'):
  r=report['professional_research'];result['research_desk']={'id':r['id'],'state':r['state'],'url':'/research-desk/?id='+r['id']}
 if report.get('research'):
  from .research_engine import ui_summary
  result['dashboard']=ui_summary(report['research'])
 return result

def intent(text):
 if re.search(r'하지\s*마|중지|취소|그만|\b(?:stop|cancel|do not|don.t)\b',text,re.I):return None
 if re.search(r'번역|예시|코드|설정|오류|고쳐|만드는 법|translate|example|debug|implement|configure',text,re.I):return None
 if re.search(r'매일|마다|daily|every morning|every evening',text,re.I):return None
 analysis=bool(re.search(r'분석|전망|리포트|보고서|영향|analy[sz]|outlook|research report',text,re.I) and re.search(r'뉴스|증시|주가|주식|시장|경제|금리|채권|환율|금융|투자|실적|재무|펀더멘털|반도체|\b(?:news|stock|market|equity|bond|econom|inflation|earnings|investment|rates)\b',text,re.I))
 import market_router
 analysis=analysis or bool(re.search(r'분석|전망|목표가|오를까|떨어질까|analy[sz]|outlook|forecast',text,re.I) and (market_router.intent(text)=='outlook' or any(name in text.casefold() for name in market_router.ALIASES)))
 if not analysis and not re.search(r'브리핑|뉴스.*(?:정리|분석|요약|알려|보여)|(?:오늘|최신|아침|저녁|주요).*뉴스|\b(?:news|intelligence|market|morning|evening) brief|/brief\b|/news\b',text,re.I):return None
 profile='market' if analysis else 'morning'
 for pattern,name in [(r'저녁|evening','evening'),(r'속보|breaking','breaking'),(r'경제|시장|증시|market','market'),(r'캐나다|canada','canada'),(r'한국|korea','korea'),(r'인공지능|기술|\bAI\b|technology','technology'),(r'기업|company','company')]:
  if re.search(pattern,text,re.I):profile=name
 company=None
 if analysis or re.search(r'실적|재무|펀더멘털|earnings|fundamental|financial statement',text,re.I):
  candidates=re.findall(r'(?<![A-Za-z])([A-Z]{1,5}(?:\.TO)?)(?![A-Za-z])',text)
  candidates=[x for x in candidates if x not in ('AIRI','PDF','EPS','FCF','EBITDA','ROE','ROIC','TSX','CAD','USD','CPI','GDP')]
  aliases={'애플':'AAPL','엔비디아':'NVDA','NVIDIA':'NVDA','마이크로소프트':'MSFT','테슬라':'TSLA','로열뱅크':'RY.TO','RBC':'RY.TO','쇼피파이':'SHOP.TO'}
  known=next((v for k,v in aliases.items() if k.casefold() in text.casefold()),None)
  if known or len(candidates)==1:company=known or candidates[0];profile='company'
 match=re.search(r'(?:company|기업)\s*[:：]\s*(.{2,100})',text,re.I)
 if match:company=match[1].strip()
 return profile,company

def chat_request(app,text,destination='web'):
 import research_desk
 command=research_desk.chat_request(app,text,destination)
 if command:return command
 if re.search(r'세계|글로벌|global|investment intelligence',text,re.I) and re.search(r'분석|시장|증시|보고서|브리핑|market|report|brief|analy',text,re.I) and not re.search(r'하지\s*마|취소|중지|설정|오류|예시|번역|매일|cancel|stop|example|translate',text,re.I):
  cfg=app.telegram_bridge.config(app) if destination=='telegram' else {}
  job=request(app,'market',{'delivery_style':'investment_v2','query':text[:1200]},destination=destination,generation=cfg.get('generation'))
  return {'text':job.get('notice','시장 자료를 조사하고 있어.')+'\n'+job.get('url','/research-desk/')}
 parsed=intent(text)
 if not parsed:return None
 profile,company=parsed
 if profile=='company' and not company:return {'text':'기업 브리핑은 기업명을 지정해 줘. 예: /brief company: NVIDIA'}
 options={'query':text[:1200]}
 if company:options['company']=company
 if not re.search('[가-힣]',text):options['language']='fr' if re.search(r'actualité|briefing.*français',text,re.I) else 'en'
 cfg=app.telegram_bridge.config(app) if destination=='telegram' else {}
 job=request(app,profile,options,destination=destination,generation=cfg.get('generation'))
 if job.get('workflow_id'):return {'text':job['notice']+'\n'+job['url']}
 if job['state']=='completed':return {'text':status(app,job['id'])['text']}
 if job['state']=='failed':return {'text':'직전 브리핑이 실패했어. 뉴스 화면에서 다시 만들 수 있어. '+str(job['error'])}
 return {'text':'요청한 주제로 출처를 확인해서 PDF 분석 보고서를 만들고 있어. NAS의 Investment/AIRI_Analysis에 저장하고, 아이리 화면이 열려 있고 음성이 켜져 있으면 읽어줄게. 다른 대화도 계속할 수 있어.'}
