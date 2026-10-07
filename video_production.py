"""Durable local-only video requests shared with a user-session GPU worker."""
import datetime as dt,fcntl,hashlib,json,os,re,secrets,time
from pathlib import Path


def root(app):return app.DATA/'video-production'
def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+'.'+secrets.token_hex(4)+'.tmp')
 with temp.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)
 temp.chmod(0o600);os.replace(temp,path)
def read(path,default=None):
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return default

def jobs(app):
 return sorted((read(p) for p in (root(app)/'jobs').glob('*.json')),key=lambda j:(j or {}).get('created',''),reverse=True)
def status(app):
 heartbeat=read(root(app)/'heartbeat.json',{})
 return {'worker_online':time.time()-heartbeat.get('timestamp',0)<45,'worker':heartbeat,'learning':learning_status(app),
 'daily_schedule':{'enabled':False,'target_count':3,'target_ready_time':'09:00','timezone':'UTC','reason':'Awaiting a successful 30-second pilot and quality approval.'},
 'jobs':[{k:j.get(k) for k in ('id','state','title','brief','created','scene','error','result','duration_seconds','script_node')} for j in jobs(app) if j][:15]}

def submit(app,body):
 brief=body.get('brief','Create an original vivid visual short with a clear beginning, development and payoff. Use the requested subject and style.')
 if not isinstance(brief,str) or not 1<=len(brief.strip())<=3000:raise ValueError('영상 요청은 1~3000자로 입력해 주세요.')
 mode=body.get('mode') or ('autonomous' if re.search(r'알아서|자율|스스로|surprise me|your own idea|original vivid visual short',brief,re.I) else 'directed')
 if mode not in ('autonomous','directed'):raise ValueError('Invalid video mode')
 folder=root(app);folder.mkdir(parents=True,exist_ok=True)
 with (folder/'submit.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  request_key=body.get('request_key')
  if request_key is not None and (not isinstance(request_key,str) or len(request_key)>250):raise ValueError('Invalid request key')
  active=next((j for j in jobs(app) if j and ((request_key and j.get('request_key')==request_key) or (not request_key and j['state'] in ('queued','planning','rendering','assembling') and j['brief']==brief.strip()))),None)
  if active:return {**active,'existing':True}
  jid=secrets.token_hex(12)
  job={'id':jid,'state':'queued','created':dt.datetime.now().astimezone().isoformat(),'brief':brief.strip(),'brief_sha256':brief_hash(brief.strip()),'request_key':request_key,'title':'Original 30-second short','scene':0,'mode':mode,'quality_approved':False,'paid_api':False}
  atomic(folder/'jobs'/(jid+'.json'),job)
  return job

def brief_hash(brief):return hashlib.sha256(brief.encode()).hexdigest()

VIDEO=re.compile(r'영상|동영상|쇼츠|유튜브|\b(video|shorts|youtube|short film)\b',re.I)
ACTION=re.compile(r'만들어(?:\s*줘)?|만들어줄|만들자|제작\s*(?:해|하자|부탁|요청|의뢰)|생성\s*해|\b(make|create|generate|produce|render)\b',re.I)
NEGATIVE=re.compile(r'(?:만들|제작하|생성하)지\s*마|하지\s*마|하지\s*말|취소|\bcancel\b|\b(?:do not|don.t)\s+(?:create|make|generate|render|produce)\b',re.I)
FEEDBACK=re.compile(r'같[아어]|왜|못|별로|이상|개선|퀄리티|퀄러티|quality|wrong|feedback',re.I)
FOLLOWUP=re.compile(r'^(?:ㅇㅋ|ㅇ|응|그래|네|yes|ok(?:ay)?|go ahead)[.! ]*$|그걸로.*(?:해|만들)|그거.*(?:해줘|만들)|다시\s*해|니가\s*하라고|하기나\s*해|바로\s*(?:해|시작)',re.I)

def is_brief(text):
 return len(text)>80 and bool(re.search(r'장면|shot|scene|lighting|조명|주인공',text,re.I)) and bool(VIDEO.search(text) or re.search(r'\d+\s*(?:초|seconds?)',text,re.I))

def request_brief(query,history=()):
 if NEGATIVE.search(query):return None
 if re.search(r'어떻게|방법|how (?:do|can|to)',query,re.I):return None
 if re.search(r'대본만|스크립트만|프롬프트만|(?:script|prompt) only|only (?:a )?(?:script|prompt)',query,re.I):return None
 if (VIDEO.search(query) or is_brief(query)) and ACTION.search(query):
  # Criticism about how a prompt should improve is not a new render order.
  if FEEDBACK.search(query) and re.search(r'같[아어]|should|need to',query,re.I) and not re.search(r'지금|바로|create this|make this',query,re.I):return None
  return query
 if is_brief(query):return query
 if FOLLOWUP.search(query) or (ACTION.search(query) and re.search(r'이걸|그걸|이거|그거|this|that',query,re.I)):
  nearby=list(history)[-2:]
  if not any(VIDEO.search(m.get('content','')) or is_brief(m.get('content','')) for m in nearby):return None
  for m in reversed(list(history)):
   content=m.get('content','')
   if m.get('role')=='user' and (is_brief(content) or (VIDEO.search(content) and ACTION.search(content) and not FEEDBACK.search(content))):
    return content if len(query)<70 else content+'\nCurrent follow-up instruction: '+query
 return None

def capability(app):
 s=status(app)
 return {'available':True,'worker_online':s['worker_online'],'interface':'video_create /video <brief>; video_status /videos; /video_result',
 'pipeline':'M1 story planning, local LTX rendering, six shots totaling about 32 seconds, NAS review export. New topics create separate queued jobs.',
 'limits':'Exact spoken dialogue, lip sync and text are not guaranteed by the local generator. No automatic publishing. Daily schedule is disabled.',
 'recent_jobs':s['jobs'][:3]}

def chat_request(app,query,history=(),request_key=None):
 brief=request_brief(query,history)
 if brief:
  if re.search(r'매일|daily|every day',query,re.I):return {'text':'매일 오전 9시까지 3편은 품질 확인 전이라 아직 켜지 않았어요. 먼저 한 편을 제작하고 검토할 수 있어요.'}
  job=submit(app,{'brief':brief,'request_key':request_key});online=status(app)['worker_online']
  return {'id':job['id'],'text':('동일한 요청이 이미 등록돼 있어요. ' if job.get('existing') else '영상 제작 요청을 별도 작업으로 등록했어요. ')+('대기 순서대로 M1 기획 → 로컬 렌더링 → NAS 저장을 진행합니다.' if online else '영상 작업자가 오프라인이라 대기 중이며, 아직 렌더링이 시작된 것은 아닙니다.')+'\n요청: '+brief[:550]+'\n작업 ID: '+job['id']+'\n약 32초로 제작하며 정확한 대사·입 모양은 현재 로컬 생성기로 보장하지 못합니다.'}
 if VIDEO.search(query) and not NEGATIVE.search(query):
  if re.search(r'상태|진행|어디까지|status|progress|도구|기능|가능|할\s*수|못\s*해|can you|tools?|어떻게|방법|how',query,re.I):
   c=capability(app);recent=c['recent_jobs']
   return {'text':'로컬 영상 제작 도구가 연결돼 있어요. '+('작업자는 온라인입니다.' if c['worker_online'] else '현재 작업자는 오프라인입니다.')+(' 최근 작업: '+recent[0]['title']+' · '+recent[0]['state'] if recent else ' 등록된 작업은 없습니다.')+' 주제와 장면을 적어 제작을 요청하면 약 32초 영상 작업으로 등록합니다. 정확한 대사·입 모양은 보장하지 못합니다.'}
 return None

def review(app,body):
 jid=body.get('id');accepted=body.get('accepted');feedback=body.get('feedback')
 if not isinstance(jid,str) or not re.fullmatch('[a-f0-9]{24}',jid):raise ValueError('Invalid video job ID.')
 if type(accepted) is not bool or not isinstance(feedback,str) or not 5<=len(feedback.strip())<=2000:raise ValueError('승인 여부와 구체적인 피드백을 입력해 주세요.')
 path=root(app)/'jobs'/(jid+'.json');job=read(path)
 if not job or job.get('state') not in ('awaiting_review','accepted','rejected'):raise ValueError('검토 가능한 완성 영상이 없습니다.')
 plan=read(root(app)/'renders'/jid/'story.json',{})
 record={'job_id':jid,'accepted':accepted,'feedback':feedback.strip(),'title':plan.get('title',job.get('title')),'story_plan':plan,'reviewed_at':dt.datetime.now().astimezone().isoformat(),'source':'user_review','weights_trained':False}
 atomic(root(app)/'learning'/('review-'+jid+'.json'),record)
 job.update(state='accepted' if accepted else 'rejected',quality_approved=accepted,feedback=feedback.strip());atomic(path,job)
 return {'saved':True,'state':job['state'],'weights_trained':False,'message':'피드백을 다음 기획에 반영합니다. 모델 가중치 추가 학습은 아직 실행하지 않았습니다.'}

def learning_status(app):
 records=[read(p,{}) for p in (root(app)/'learning').glob('review-*.json')]
 return {'feedback_records':len(records),'accepted':sum(r.get('accepted') is True for r in records),'rejected':sum(r.get('accepted') is False for r in records),'method':'review_feedback_in_next_planning_prompt','weights_trained':False,'automatic_weight_training_enabled':False,'reason':'No validated training dataset or independent evaluation suite yet; inference feedback is not weight training.'}
