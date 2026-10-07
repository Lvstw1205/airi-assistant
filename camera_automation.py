"""Local camera companion and explicitly armed homecam. No saved camera-1 images."""
import collections, hashlib, json, re, threading, time
from pathlib import Path
import camera_bridge, camera_sources, camera_presence, camera_preview, product_search, usb_camera_preview
import homecam_dialogue

DEFAULTS={'camera1_auto':True,'camera1_speak':True,'home_armed':False,'home_generation':''}

def distance(a,b):
    if len(a)!=256 or len(b)!=256:return 0
    return sum(abs(x-y) for x,y in zip(a,b))/256

def retail_code(evidence):
    for code in evidence.get('barcodes',[]):
        b=code.get('bbox',[])
        if ('EAN' in code.get('symbology','').upper() or 'UPC' in code.get('symbology','').upper()) and product_search.valid_gtin(code.get('value')):
            if len(b)==4 and .15<(b[0]+b[2])/2<.85 and .1<(b[1]+b[3])/2<.9:return code['value']
    return None

class ChangeGate:
    """Wait for a stable held/placed item; suppress static rooms and repeated barcodes."""
    def __init__(self):
        self.previous=[];self.baseline=[];self.stable=0;self.code=None;self.code_hits=0;self.last_code=None;self.last=0
    def update(self,evidence,now):
        code=retail_code(evidence)
        self.code_hits=self.code_hits+1 if code and code==self.code else 1 if code else 0;self.code=code
        f=evidence.get('fingerprint',[])
        valid=isinstance(f,list) and len(f)==256 and all(type(n) is int and 0<=n<=255 for n in f)
        changed=distance(f,self.baseline) if valid else 0
        self.stable=self.stable+1 if valid and self.previous and distance(f,self.previous)<5 else 0
        if valid:
            self.previous=f
            if not self.baseline:self.baseline=f
        barcode_new=bool(code and code!=self.last_code and self.code_hits>=2)
        moved=changed>8 and self.stable>=2
        if now-self.last<12 or not (barcode_new or moved):return False
        self.last=now;self.baseline=f if valid else self.baseline
        if code:self.last_code=code
        return True

def short_identity(wanted):
    name=' '.join(dict.fromkeys(str(wanted.get(k) or '').strip() for k in ('brand','name','model'))).strip()
    if name:return name[:180]+'로 라벨이 읽혀. 판매 정보도 확인할게.'
    category=wanted.get('candidate_query','')
    if category:return category[:80]+'로 보여. 정확한 제품명을 알려면 라벨을 조금 더 가까이 보여 줘.'
    return ''

class Service:
    def __init__(self,app):
        self.app=app;self.path=app.DATA/'camera/automation.json';self.lock=threading.RLock();self.stopped=threading.Event()
        self.started=False;self.revision=0;self.gate=ChangeGate();self.seen={};self.result=None;self.result_id=0
        self.browser_voice_until=0
        self.camera1_state='준비 중';self.home_state='꺼짐';self.voice_error='';self.voice_queue=collections.deque(maxlen=5)
        self.unknown_hits=0;self.last_home_alert=-float('inf');self.absent_since=None;self.home_alerted=False
        self.home_checked_at=0;self.home_frame_count=0;self.family_seen={}
        self.visitor=homecam_dialogue.Conversation(app,self)
    def settings(self):
        try:
            data=json.loads(self.path.read_text());return {**DEFAULTS,**{k:v for k,v in data.items() if k in DEFAULTS}}
        except (OSError,ValueError,TypeError):return dict(DEFAULTS)
    def save(self,values):
        if set(values)-{'camera1_auto','camera1_speak'} or any(type(v) is not bool for v in values.values()):raise ValueError('자동 카메라 설정 값을 확인해 줘.')
        with self.lock:
            c={**self.settings(),**values};camera_bridge.atomic_json(self.path,c);self.revision+=1
            if not c['camera1_auto']:
                usb_camera_preview.service(self.app).set_continuous(False);self.camera1_state='꺼짐';self.voice_queue.clear()
        return self.status()
    def set_home(self,enabled,cfg):
        if type(enabled) is not bool:raise ValueError('감시 설정을 확인해 줘.')
        if enabled:
            if not cfg.get('enabled') or not cfg.get('chat_id') or not cfg.get('user_id'):raise ValueError('먼저 텔레그램 본인 계정을 연결해 줘.')
            if not cfg.get('notifications',True):raise ValueError('텔레그램 알림이 꺼져 있어. 알림을 켠 뒤 홈캠 감시를 시작해 줘.')
            if not camera_presence.service(self.app).owner():raise ValueError('등록된 얼굴이 없어. AIRI 설정 → 비전에서 User 얼굴을 먼저 등록해 줘. 감시는 아직 켜지 않았어.')
            c=camera_sources.service(self.app,2).config()
            if not c['enabled'] or not all(c.get(k) for k in ('host','username','password')):raise ValueError('카메라 2 홈캠 연결 설정을 먼저 확인해 줘.')
        with self.lock:
            c={**self.settings(),'home_armed':enabled,'home_generation':cfg.get('generation','') if enabled else ''}
            camera_bridge.atomic_json(self.path,c);self.revision+=1;self.unknown_hits=0;self.home_alerted=False
            self.home_state='감시 준비 중 · 첫 영상 확인 대기' if enabled else '꺼짐'
            self.home_checked_at=0;self.family_seen.clear()
            self.voice_queue=collections.deque((x for x in self.voice_queue if not x[0].startswith('home')),maxlen=5)
            if not enabled:camera_preview.service(self.app).stop();self.visitor.cancel()
            else:self.visitor.prewarm()
        return self.status()
    def status(self):
        c=self.settings()
        presence=camera_presence.service(self.app).status()
        import telegram_bridge
        active=self.active_home(telegram_bridge.config(self.app)) and time.time()-self.home_checked_at<5 and self.home_state.startswith('감시 중')
        with self.lock:return {k:c[k] for k in ('camera1_auto','camera1_speak','home_armed')}|{'camera1_state':self.camera1_state,'home_state':self.home_state,
                'registered':camera_presence.service(self.app).owner() is not None,'registered_name':'User','result_id':self.result_id,'last_result':self.result,'voice_error':self.voice_error,
                'automatic_interval_seconds':1.2,'home_interval_seconds':1,'home_warning':homecam_dialogue.WARNING,'camera1_retention':'latest_frame_memory_only',
                'home_active':active,'home_checked_at':self.home_checked_at or None,'home_frame_count':self.home_frame_count,
                'family':presence['family'],'enrolling':presence.get('enrolling',False),'pending_samples':presence.get('pending_samples',0),
                'enrollment_target':presence.get('enrollment_target'),'visitor_dialogue':self.visitor.status()}
    def diagnose_home(self):
        presence=camera_presence.service(self.app)
        with presence.lock:r=presence.observe(False,force=True)
        return {'connected':True,'fresh':r.get('fresh',False),'elapsed_ms':r.get('elapsed_ms'),
                'faces':[{k:f[k] for k in ('label','quality') if k in f} for f in r.get('faces',[])],
                'message':'홈캠 영상 연결됨 · '+str(len(r.get('faces',[])))+'개 얼굴 감지'}
    def active_home(self,cfg):
        c=self.settings()
        return bool(c['home_armed'] and cfg.get('enabled') and cfg.get('notifications',True) and cfg.get('chat_id') and cfg.get('user_id') and c['home_generation']==cfg.get('generation'))
    def announce(self,kind,text):
        if not text:return
        with self.lock:
            item=(kind,str(text)[:350],time.monotonic()+60)
            if kind=='home':self.voice_queue.appendleft(item)
            else:self.voice_queue.append(item)
    def idle(self):
        voice=getattr(self.app,'VOICE_SERVICE',None)
        return not self.visitor.active and not self.app.CHAT_LOCK.locked() and not self.app.STT_LOCK.locked() and not (voice and voice.active) and time.monotonic()>max(getattr(self.app,'LISTEN_UNTIL',0),self.browser_voice_until)
    def scan(self):
        c=self.settings();camera=camera_sources.service(self.app,1);preview=usb_camera_preview.service(self.app)
        enabled=c['camera1_auto'] and camera.config()['enabled']
        preview.set_continuous(True) if enabled else preview.set_continuous(False)
        if not enabled:self.camera1_state='꺼짐';return
        frame=preview.get();self.camera1_state='상시 켜짐 · 새 물건 대기'
        if not self.idle():self.camera1_state='상시 켜짐 · 대화가 끝나면 물건 확인';return
        evidence=camera.local_evidence(frame)
        if not self.gate.update(evidence,time.monotonic()):return
        revision=self.revision;self.camera1_state='새 물건 인식 중'
        code=retail_code(evidence)
        if code:
            wanted={'gtin':code,'query':code,'searchable':True,'search_basis':'barcode','category':'제품','candidate_query':''}
        else:
            observation=camera.run('camera_describe',question='한국어로 답해. 중앙에 새로 보여준 손에 든 물건 또는 가까이 놓은 제품 하나만 식별해. 사람, 얼굴, 방 배경, 가구, 화면 속 글자는 대상이 아니야. 제품이 없으면 product.category를 unknown, bbox를 null로 해. 읽을 수 있는 실제 라벨만 제품명으로 써.',_frame=frame,_evidence=evidence,detail=False)
            wanted=product_search.identity(observation)
            if not wanted.get('searchable') and not wanted.get('candidate_query'):self.camera1_state='물건 라벨이 잘 보이도록 가까이 보여 줘';return
        if revision!=self.revision or not self.settings()['camera1_auto']:return
        key=product_search.norm(wanted.get('query') or wanted.get('candidate_query',''))
        if time.monotonic()-self.seen.get(key,-1000)<300:self.camera1_state='같은 물건 · 안내 반복하지 않음';return
        self.seen={k:v for k,v in self.seen.items() if time.monotonic()-v<300};self.seen[key]=time.monotonic()
        if c['camera1_speak'] and not code:self.announce('product',short_identity(wanted))
        self.camera1_state='제품 판매처 확인 중'
        result=product_search.search_identity(wanted);result.update(camera_id=1,camera='카메라 1 · PS5 HD Camera',capture_time=camera.last)
        result['text']=product_search.summary(result)
        if revision!=self.revision or not self.settings()['camera1_auto']:return
        # A barcode's product name is taken only from an exact matching retailer record.
        exact=[o for o in result.get('offers',[]) if o['match_basis']=='same_barcode']
        if c['camera1_speak'] and code:
            self.announce('product',('바코드가 '+exact[0]['title'][:130]+'와 일치해. '+exact[0]['price']+' '+exact[0]['currency']+'로 표시된 판매처가 있어.' if exact else '바코드는 읽었어. 다만 연결한 판매 페이지에서 정확한 제품명과 가격은 확인하지 못했어. 앞면 제품명도 보여 줘.'))
        with self.lock:self.result=result;self.result_id+=1;self.camera1_state='인식 완료 · 다른 물건을 보여 줘'
    def observe_home(self):
        import telegram_bridge
        cfg=telegram_bridge.config(self.app)
        if not self.active_home(cfg):
            if self.settings()['home_armed']:self.home_state='감시 일시중지 · 텔레그램 연결·알림 설정 확인'
            return
        presence=camera_presence.service(self.app)
        if presence.enrollment_until>time.monotonic():
            self.home_state='얼굴 등록 중 · 방문자 경고 잠시 멈춤';self.unknown_hits=0;return
        if not presence.owner():
            self.set_home(False,cfg);telegram_bridge.enqueue(self.app,cfg,'camera:missing-owner:'+str(int(time.time())),'홈캠 감시를 껐어. 등록된 얼굴 정보가 없어 다시 등록해야 해.');return
        rev=self.revision
        with presence.lock:r=presence.observe(False,force=True)
        if rev!=self.revision or not self.active_home(telegram_bridge.config(self.app)):return
        faces=[f for f in r.get('faces',[]) if f.get('quality')]
        labels=[f['label'] for f in faces]
        now=time.monotonic()
        self.home_frame_count+=1
        if r.get('fresh'):self.home_checked_at=time.time()
        self.home_state=('감시 중 · ' if r.get('fresh') else '영상 연결 중 · ')+('미등록 얼굴 확인 중' if 'unmatched' in labels else '등록 얼굴과 일치' if any(x in labels for x in ('owner_match','known_match')) else '얼굴 대기 / 불확실')
        self.greet_family(faces,now,r.get('fresh',False),'unmatched' in labels)
        unknown=r.get('fresh') and 'unmatched' in labels
        self.unknown_hits=self.unknown_hits+1 if unknown else 0
        if 'unmatched' not in labels:
            if self.absent_since is None:self.absent_since=now
            if now-self.absent_since>30:self.home_alerted=False
        else:self.absent_since=None
        if self.unknown_hits>=3 and not self.home_alerted and now-self.last_home_alert>120:
            self.home_alerted=True;self.last_home_alert=now
            self.announce('home',homecam_dialogue.WARNING)
            telegram_bridge.enqueue(self.app,cfg,'camera:visitor:'+str(int(time.time())), '홈캠에서 등록되지 않은 얼굴을 반복해서 확인했어. Mac 스피커로 “'+homecam_dialogue.WARNING+'”라고 묻고 홈캠 마이크로 대답을 잠깐 들을게. 오인식 가능성이 있으니 ‘홈캠 / 상황’으로 확인해 줘.',{'camera_alert':True,'expires':time.time()+120})
    def greet_family(self,faces,now,fresh,unknown_present=False):
        if not fresh:return
        self.family_seen={k:v for k,v in self.family_seen.items() if now-v['last']<30}
        visible={f['person_id']:f for f in faces if f.get('label')=='known_match' and f.get('person_id')}
        for key,face in visible.items():
            previous=self.family_seen.get(key,{'last':0,'hits':0,'greeted':False})
            previous['hits']=previous['hits']+1 if now-previous['last']<2.5 else 1
            previous['last']=now
            if previous['hits']>=3 and not previous['greeted'] and not unknown_present:
                self.announce('home_greeting','안녕하세요, '+face['greeting_name']+'.');previous['greeted']=True
            self.family_seen[key]=previous
    def speak_pending(self):
        import telegram_bridge
        if not self.idle():return
        with self.app.VOICE_LOCK:
            if self.app.SPEECH and self.app.SPEECH.poll() is None:return
        with self.lock:
            if not self.voice_queue:return
            kind,text,until=self.voice_queue.popleft()
        c=self.settings()
        if time.monotonic()>until or (kind.startswith('home') and not self.active_home(telegram_bridge.config(self.app))) or (kind=='product' and not (c['camera1_auto'] and c['camera1_speak'])):return
        if kind.startswith('home'):
            greeting=text.removeprefix('안녕하세요, ').rstrip('.') if kind=='home_greeting' else None
            if not self.visitor.start(text,greeting):
                with self.lock:self.voice_queue.appendleft((kind,text,until))
            return
        try:
            result=telegram_bridge.local(self.app,'speech-prepare',{'text':text},timeout=90)
            current=self.settings()
            still_allowed=current['home_armed'] if kind=='home' else current['camera1_auto'] and current['camera1_speak']
            if not still_allowed or time.monotonic()>until:return
            if not self.idle():
                with self.lock:self.voice_queue.appendleft((kind,text,until))
                return
            if result.get('id'):result=telegram_bridge.local(self.app,'speech-play',{'id':result['id'],'generation':result['generation']},timeout=10)
            if result.get('busy'):
                with self.lock:self.voice_queue.appendleft((kind,text,until))
            elif result.get('ok'):self.voice_error=''
        except Exception:self.voice_error='자동 음성 재생 실패 · 음성 설정에서 테스트해 줘'
    def start(self):
        if self.started:return
        self.started=True
        def loop(action,interval,field=None):
            while not self.stopped.is_set():
                try:action()
                except Exception as error:
                    if field:setattr(self,field,'연결 확인 필요 · '+(str(error)[:160] if isinstance(error,(ValueError,camera_bridge.CameraError)) else type(error).__name__))
                self.stopped.wait(interval)
        if self.settings()['home_armed']:self.visitor.prewarm()
        for name,action,interval,field in [('objects',self.scan,1.2,'camera1_state'),('home',self.observe_home,1,'home_state'),('voice',self.speak_pending,.2,None)]:
            threading.Thread(target=loop,args=(action,interval,field),name='airi-camera-'+name,daemon=True).start()
    def stop(self):
        self.stopped.set();self.visitor.cancel();usb_camera_preview.service(self.app).close();camera_preview.service(self.app).close()

_SERVICES={};_LOCK=threading.Lock()
def service(app):
    with _LOCK:
        key=str(app.DATA)
        if key not in _SERVICES:_SERVICES[key]=Service(app)
        return _SERVICES[key]
