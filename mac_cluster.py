"""Authenticated Mac worker status and routing of pure scheduled text jobs."""
import contextlib
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
import threading
import time
import urllib.request
import mac_dispatch

_lock=threading.RLock()
_refreshing=threading.Lock()
_cache={}
_last={}
_dispatch_lock=threading.Lock()
_active={}
_waiting={}
_attempt=threading.local()

ROLES={'M1':['예약 글쓰기','문서 요약·번역·정리','같은 모델이 있는 보고서 분석','작업실 기획·초안·검수'],
       'primary':['실시간 대화','음성 인식·합성','카메라·방문자 응대','이미지·영상 생성·렌더링']}


def directory(app):return app.DATA/'mac-worker'

def config(app):
    try:
        c=json.loads((directory(app)/'routing.json').read_text())
        return {'enabled':c.get('enabled') is True,'model':str(c.get('model','qwen3:4b'))}
    except (OSError,ValueError):return {'enabled':False,'model':'qwen3:4b'}

def pairing(app):
    try:return json.loads((directory(app)/'pairing.json').read_text())
    except (OSError,ValueError):return {}

def command(app):
    p=pairing(app)
    if not p.get('paired'):raise ValueError('M1 pairing is not configured.')
    return mac_dispatch.ssh_command(p['host'],p['username'],directory(app)/'id_ed25519',directory(app)/'known_hosts')

def local_models():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:11434/api/tags',timeout=3) as r:return json.load(r).get('models',[])
    except Exception:return []

def transport(host):
    try:
        p=subprocess.run(['/sbin/route','-n','get',host],capture_output=True,text=True,timeout=2,check=True)
        found=re.search(r'interface:\s*(\S+)',p.stdout)
        interface=found.group(1) if found else ''
        return {'host':host,'interface':interface,'label':'Thunderbolt Bridge' if interface=='bridge0' else '로컬 네트워크','verified_at':time.time()}
    except (OSError,subprocess.SubprocessError):return {'host':host,'label':'네트워크 경로 미확인'}

def refresh(app):
    p=pairing(app)
    state={'id':'mac2','role':'background_worker','connected':False,'state':'unconfigured' if not p.get('paired') else 'offline',
           'capabilities':[],'matching_models':[],'checked_at':time.time(),'hardware':p.get('worker',{}).get('hardware','M1')}
    if p.get('paired'):
        try:
            remote=mac_dispatch.exchange(command(app),{'version':1,'action':'status'},20)
            local=local_models()
            state.update(connected=True,state='ready' if remote.get('ollama') else 'ollama_offline',
                         capabilities=remote.get('capabilities',[]),hardware=remote.get('hardware','M1'),
                         worker_pid=remote.get('pid'),transport=transport(p['host']),office=remote.get('office'),
                         matching_models=[m['name'] for m in local if mac_dispatch.can_offload(m['name'],local,remote.get('models',[]),True)])
        except Exception:state['error']='M1 worker unavailable. Check power, Remote Login and the Thunderbolt connection.'
    with _lock:_cache[str(app.DATA)]=state
    return state

def status(app):
    key=str(app.DATA)
    with _lock:state=dict(_cache.get(key,{'id':'mac2','connected':False,'state':'checking' if pairing(app).get('paired') else 'unconfigured','capabilities':[],'matching_models':[]}))
    if time.time()-state.get('checked_at',0)>15 and _refreshing.acquire(False):
        def check():
            try:refresh(app)
            finally:_refreshing.release()
        threading.Thread(target=check,daemon=True).start()
    saved=history(app)
    return {**state,'stale':time.time()-state.get('checked_at',0)>30,'routing':config(app),'last_job':dict(_last.get(key) or saved.get('last_job',{})),
            'active_job':dict(_active.get(key,{})),'waiting_jobs':list(_waiting.get(key,{}).values()),'roles':ROLES,'recent_jobs':saved.get('recent_jobs',[])}

def history(app):
    try:
        value=json.loads((directory(app)/'workload.json').read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def record_job(app,node,model,purpose,seconds,fallback=False,state='completed',job_id=None,reason=None,proof=None):
    record={'node':node,'model':model,'purpose':purpose,'fallback':fallback,'state':state,
            'seconds':round(seconds,2),'finished_at':time.time(),'job_id':job_id or secrets.token_hex(12)}
    if reason:record['reason']=reason
    if proof:record['proof']=proof
    with _lock:
        _last[str(app.DATA)]=record
        # Optional status history must never discard a completed inference.
        tmp=None
        try:
            folder=directory(app);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            recent=history(app).get('recent_jobs',[])
            value={'last_job':record,'recent_jobs':([record]+[r for r in recent if r.get('job_id')!=record['job_id']])[:100]}
            tmp=folder/('workload-'+secrets.token_hex(8))
            with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(value,f)
            os.replace(tmp,folder/'workload.json')
        except OSError:
            if tmp:
                with contextlib.suppress(OSError):tmp.unlink()
    return record

REASONS={'routing_disabled':'M1 자동 배정 꺼짐','external_model':'외부 API 모델은 M1에서 실행하지 않음','offline':'M1 연결 응답 없음','ollama_offline':'M1 모델 서비스 응답 없음','model_mismatch':'양쪽 Mac에 동일한 모델 가중치가 없음','queue_timeout':'M1 실행 순서 대기 시간 초과','worker_error':'M1 실행 실패 또는 응답 불완전','invalid_output':'M1 결과 검증 실패'}

def last_reason():return getattr(_attempt,'reason',None)

def try_offload(app,messages,model,max_tokens=1600,purpose='background',timeout=135,validator=None,job_id=None,on_start=None):
    """Pure buffered text only; same weights, no foreground lock or external tools."""
    _attempt.reason=None
    identifier=job_id or secrets.token_hex(12)
    def failed(reason,seconds=0):
        _attempt.reason=reason
        record_job(app,'M1',model,purpose,seconds,state='invalid_output' if reason=='invalid_output' else 'unavailable' if reason=='worker_error' else 'skipped',job_id=identifier,reason=reason)
        return None
    if not config(app)['enabled']:return failed('routing_disabled')
    if model.startswith(('openai:','freellmapi:')):return failed('external_model')
    key=str(app.DATA);start=time.monotonic();deadline=start+min(135,max(1,timeout))
    with _lock:current=dict(_cache.get(key,{}))
    if time.time()-current.get('checked_at',0)>30:current=refresh(app)
    if not current.get('connected'):return failed('offline')
    if current.get('state')=='ollama_offline':return failed('ollama_offline')
    if model not in current.get('matching_models',[]):return failed('model_mismatch')
    remaining=deadline-time.monotonic()
    with _lock:_waiting.setdefault(key,{})[identifier]={'job_id':identifier,'node':'M1','model':model,'purpose':purpose,'state':'queued'}
    acquired=remaining>0 and _dispatch_lock.acquire(timeout=max(0,remaining))
    with _lock:_waiting.get(key,{}).pop(identifier,None)
    if not acquired:return failed('queue_timeout',time.monotonic()-start)
    try:
        remaining=deadline-time.monotonic()
        if remaining<1:return failed('queue_timeout',time.monotonic()-start)
        with _lock:_active[key]={'job_id':identifier,'node':'M1','model':model,'purpose':purpose,'state':'running','started_at':time.time()}
        if on_start:on_start()
        answer=mac_dispatch.exchange(command(app),{'version':1,'action':'complete','model':model,
                'messages':messages,'max_tokens':max_tokens,'job_id':identifier,'purpose':purpose},timeout=remaining)
        if answer.get('model')!=model or not isinstance(answer.get('text'),str) or not answer['text'].strip():raise ValueError('Incomplete worker result')
        if validator:
            try:validator(answer['text'])
            except (ValueError,TypeError):return failed('invalid_output',time.monotonic()-start)
        record=record_job(app,'M1',model,purpose,time.monotonic()-start,job_id=identifier,proof={'transport':'authenticated_ssh','host':pairing(app).get('host'),'worker_pid':answer.get('pid'),'status_pid':current.get('worker_pid')})
        return {'text':answer['text'],**record}
    except (ValueError,OSError):
        return failed('worker_error',time.monotonic()-start)
    finally:
        with _lock:_active.pop(key,None)
        _dispatch_lock.release()

def save(app,body):
    old=config(app);enabled=body.get('enabled',old['enabled']);model=body.get('model',old['model'])
    if type(enabled) is not bool or not isinstance(model,str):raise ValueError('Invalid routing settings.')
    if enabled:
        current=refresh(app)
        if model not in current['matching_models']:raise ValueError('Choose a model with matching weights installed on both Macs. M1 must be online to enable routing.')
    folder=directory(app);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/'routing.json';tmp=folder/('routing-'+secrets.token_hex(8))
    with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump({'enabled':enabled,'model':model},f)
    os.replace(tmp,path)
    return status(app)

def complete(app,messages,selected_model,max_tokens=1536,primary_locked=False):
    c=config(app);start=time.monotonic();model=selected_model;node='primary';fallback=False
    if c['enabled']:
        # Dedicated background model is explicit in the settings panel. Keep
        # interactive chat's selected provider and personality untouched.
        model=c['model'];answer=try_offload(app,messages,model,max_tokens,purpose='예약 글쓰기')
        if answer:text=answer['text'];node='M1'
        else:fallback=True
    if node=='primary':
        # Local fallback waits for foreground chat to finish; SSH inference
        # never holds this lock, so the other Mac can keep responding.
        with contextlib.nullcontext() if primary_locked else app.CHAT_LOCK:
            text=app.llm_client.complete(messages,model,max_tokens)
    if node=='primary':record_job(app,node,model,'예약 글쓰기',time.monotonic()-start,fallback,reason=last_reason() if fallback else None)
    app.event('cluster','Background inference: '+node+' · '+model+(' · worker unavailable, completed locally' if fallback else ''))
    return text

def test(app):
    c=config(app);state=refresh(app)
    if c['model'] not in state['matching_models']:raise ValueError('M1 is unavailable or model weights do not match.')
    nonce='AIRI-'+secrets.token_hex(4)
    def exact(text):
        if text.strip()!=nonce:raise ValueError('Verification text mismatch')
    result=try_offload(app,[{'role':'system','content':'Copy the user text exactly. No additional words.'},{'role':'user','content':nonce}],c['model'],256,purpose='M1 왕복 검증',validator=exact)
    if not result:raise ValueError('M1 검증 실패: '+REASONS.get(last_reason(),'응답을 확인하지 못함'))
    return {**result,'ok':True,'hardware':state['hardware'],'message':'M1에서 새 확인 문구를 생성해 일치하는 결과를 받았어.'}
