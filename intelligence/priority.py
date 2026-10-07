from .research_formats import format_for
"""Cooperative background inference: yield to speech/chat without taking CHAT_LOCK."""
import json,re,time,urllib.request
import mac_cluster
from .pipeline import LocalModel

def foreground_busy(app):
 for name in ('CHAT_LOCK','STT_LOCK','TTS_LOCK'):
  lock=getattr(app,name,None)
  if lock and lock.locked():return True
 if time.monotonic()<getattr(app,'LISTEN_UNTIL',0):return True
 speech=getattr(app,'SPEECH',None)
 if speech and speech.poll() is None:return True
 service=getattr(app,'VOICE_SERVICE',None)
 if service and getattr(service,'active',False):return True
 # The reader periodically renews this priority across gaps between sentences.
 import report_service
 return time.monotonic()<getattr(report_service,'_reading_until',0)

M1_DRAFT_STAGES={'topic','extraction','investment_relevance','article_commentary','financial_research','desk_topic','desk_extract','desk_notes'}

class BackgroundModel(LocalModel):
 def __init__(self,app,options,progress):
  super().__init__(options['model'],time.monotonic()+options['deadline_seconds'])
  self.app=app;self.progress=progress;self.wall_deadline=time.monotonic()+7200
  self.remote_failures={}
 def __call__(self,stage,prompt,data,max_tokens=1600):
  # The worker preserves this report's selected model/digest. Only the pure
  # reasoning pass travels over the paired SSH channel; collection and PDF/DB
  # writes remain on the primary Mac. Local validation still gates publication.
  remaining=self.deadline-time.monotonic()
  if remaining<5:raise TimeoutError('Intelligence run time budget exhausted')
  schema=format_for(stage)
  if stage.startswith('desk_'):
   from research_desk.schemas import for_stage
   schema=for_stage(stage,data)
  contract='\nReturn only one JSON object, without Markdown. '
  if isinstance(schema,dict):contract+='Required JSON schema: '+json.dumps(schema,separators=(',',':'))
  employee='노아' if stage in ('desk_topic','desk_extract','desk_notes') else '세라' if stage.startswith('desk_') else '이안' if stage in ('topic','extraction','investment_relevance') else '레오' if stage in M1_DRAFT_STAGES else '세라'
  prompt='너는 AIRI 투자 분석팀의 AI 직원 '+employee+'다. 아래 작업과 근거·출력 형식 지침을 정확하게 따른다.\n'+prompt
  messages=[{'role':'system','content':prompt+contract},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]
  self.progress('자료 분석 담당 확인 · '+stage)
  start=time.monotonic();call_started=start;remote_seconds=0
  remote=None;fallback_reason=None
  draft_stage=stage in M1_DRAFT_STAGES
  if draft_stage and self.remote_failures.get(stage,0)<2:
   remote_model=mac_cluster.config(self.app)['model'] if stage in ('desk_topic','desk_extract','desk_notes') else self.model
   remote_limit=60 if stage in ('desk_topic','desk_notes') else 125
   remote=mac_cluster.try_offload(self.app,messages,remote_model,max_tokens,purpose=employee+' · 보고서 초안 · '+stage,timeout=min(remote_limit,remaining),validator=lambda text:validated_json(text,schema),on_start=lambda:self.progress('M1 '+employee+' · 자료 정리·초안 · '+stage))
   fallback_reason=mac_cluster.last_reason()
   remote_seconds=time.monotonic()-start
   if fallback_reason in ('invalid_output','worker_error'):self.remote_failures[stage]=self.remote_failures.get(stage,0)+1
  elif draft_stage:fallback_reason='report_stage_retry_limit'
  if remote:
   self.remote_failures[stage]=0
   result=validated_json(remote['text'],schema)
   self.calls.append({'stage':stage,'seconds':round(time.monotonic()-start,2),'wall_seconds':round(time.monotonic()-call_started,2),'tokens':None,'actual_model':remote_model,'node':'M1','role':'draft'})
   return result
  if fallback_reason:self.progress(mac_cluster.REASONS.get(fallback_reason,'M1 처리 확인 필요')+' · M6에서 초안 대체 처리')
  while True:
   wait=time.monotonic()
   announced=False
   while foreground_busy(self.app):
    if not announced:self.progress('대화·음성 우선 처리 중 · 분석 대기');announced=True
    if time.monotonic()>self.wall_deadline:raise TimeoutError('대화 우선 대기 시간이 길어 분석을 중단했어. 다시 요청해 줘.')
    time.sleep(.25)
   self.deadline+=time.monotonic()-wait
   remaining=self.deadline-time.monotonic()
   if remaining<5:raise TimeoutError('Intelligence run time budget exhausted')
   self.progress(('M6 세라 · 초안 대체 처리 · ' if draft_stage else 'M6 세라 · 검수·보강 · ')+stage)
   self.app.local_learning.touch()
   body={'model':self.model,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(data,ensure_ascii=False)}], 'stream':True,'format':schema,'think':False,'keep_alive':'60s','options':{'temperature':.1,'presence_penalty':0,'num_predict':max_tokens,'num_ctx':16384}}
   request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
   start=time.monotonic();content='';cancelled=False;last={}
   # A 3,000–5,500-token research answer cannot reliably finish in the same
   # window as a short extraction on the installed local model. Keep the
   # total job deadline authoritative while allowing the requested output.
   stage_limit=min(900,max(150,60+max_tokens/8)) if stage.startswith('desk_') else 150
   with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=min(stage_limit,remaining)) as response:
    for line in response:
     # Research uses a dedicated model and holds no foreground lock. Once it
     # has started, do not throw away minutes of work for every short utterance.
     # New calls still wait for foreground activity before starting above.
     if not stage.startswith('desk_') and foreground_busy(self.app):cancelled=True;break
     if time.monotonic()-start>min(stage_limit,remaining):raise TimeoutError('Background inference deadline')
     if not line.strip():continue
     part=json.loads(line)
     if part.get('error'):raise ValueError(str(part['error'])[:180])
     content+=part.get('message',{}).get('content','');last=part
     if part.get('done'):break
   if cancelled:
    self.deadline+=time.monotonic()-start
    continue
   if not last.get('done') or last.get('done_reason')=='length':raise ValueError('Incomplete local JSON response')
   result=validated_json(content,schema)
   if not isinstance(result,dict):raise ValueError('Expected JSON object')
   elapsed=time.monotonic()-start
   self.calls.append({'stage':stage,'seconds':round(elapsed,2),'wall_seconds':round(time.monotonic()-call_started,2),'remote_attempt_seconds':round(remote_seconds,2),'load_seconds':round(last.get('load_duration',0)/1e9,2),'prompt_seconds':round(last.get('prompt_eval_duration',0)/1e9,2),'generation_seconds':round(last.get('eval_duration',0)/1e9,2),'tokens':last.get('eval_count'),'actual_model':last.get('model'),'node':'primary','role':'draft_fallback' if draft_stage else 'review'})
   mac_cluster.record_job(self.app,'primary',self.model,('보고서 초안 대체 · ' if draft_stage else '보고서 검수·보강 · ')+stage,elapsed,fallback=bool(draft_stage and mac_cluster.config(self.app)['enabled']),reason=fallback_reason);return result

def validated_json(text,schema):
 def reject_constant(value):raise ValueError('Non-finite JSON number')
 value=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip()),parse_constant=reject_constant)
 if not isinstance(value,dict):raise ValueError('Expected JSON object')
 def check(v,s):
  if not isinstance(s,dict):return
  if 'anyOf' in s:
   for option in s['anyOf']:
    try:check(v,option);break
    except ValueError:pass
   else:raise ValueError('JSON alternative type mismatch')
  kinds=s.get('type');kinds=kinds if isinstance(kinds,list) else [kinds] if kinds else []
  matches={'object':isinstance(v,dict),'array':isinstance(v,list),'string':isinstance(v,str),'null':v is None,'boolean':type(v) is bool,'number':type(v) in (int,float),'integer':type(v) is int}
  if kinds and not any(matches.get(k,False) for k in kinds):raise ValueError('JSON field type mismatch')
  if 'enum' in s and v not in s['enum']:raise ValueError('JSON enum mismatch')
  if type(v) in (int,float) and (v<s.get('minimum',v) or v>s.get('maximum',v)):raise ValueError('JSON number outside bounds')
  if isinstance(v,dict):
   props=s.get('properties',{})
   if not set(s.get('required',[]))<=set(v) or (s.get('additionalProperties') is False and set(v)-set(props)):raise ValueError('JSON fields mismatch')
   for k,item in v.items():check(item,props.get(k,{}))
  if isinstance(v,list):
   if len(v)<s.get('minItems',0):raise ValueError('JSON array too short')
   if len(v)>s.get('maxItems',len(v)):raise ValueError('JSON array too long')
   for item in v:check(item,s.get('items',{}))
 check(value,schema);return value

def background_model(app,options,progress):return BackgroundModel(app,options,progress)
