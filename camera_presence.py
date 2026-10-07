"""Local owner face comparison. Never an authentication/authorization mechanism."""
import base64,json,os,re,secrets,sys,threading,time
from pathlib import Path
import camera_preview

class Presence:
 def __init__(self,app):
  self.app=app;self.root=Path(__file__).resolve().parent/'.runtime/presence'
  self.path=app.DATA/'presence'/'owner.json';self.settings_path=app.DATA/'presence'/'settings.json'
  self.family_path=app.DATA/'presence'/'family.json';self.target=None;self.enrollment_until=0
  self.lock=threading.Lock();self.engine=None;self.pending=[];self.unknown_hits=0;self.last_seen=0;self.last_ask=0;self.asked=False
 def settings(self):
  try:data=json.loads(self.settings_path.read_text())
  except (OSError,ValueError):data={}
  return {'enabled':data.get('enabled',True) is True}
 def owner(self):
  try:
   data=json.loads(self.path.read_text());samples=data['samples']
   if len(samples)!=3 or any(len(s)!=128 for s in samples):return None
   return data
  except (OSError,ValueError,KeyError,TypeError):return None
 def status(self):
  return {**self.settings(),'registered':self.owner() is not None,'name':'User','pending_samples':len(self.pending),'required_samples':3,'local_only':True,'authentication':False,
          'family':[{'id':p['id'],'name':p['name'],'greeting_name':p['greeting_name']} for p in self.family()], 'enrollment_target':self.target,'enrolling':self.enrollment_until>time.monotonic()}
 def family(self):
  try:
   people=json.loads(self.family_path.read_text())['people']
   return [p for p in people if re.fullmatch(r'[a-f0-9]{16}',p['id']) and isinstance(p['name'],str) and isinstance(p['greeting_name'],str) and len(p['samples'])==3 and all(len(s)==128 for s in p['samples'])][:12]
  except (OSError,ValueError,KeyError,TypeError):return []
 def enrollment_target(self,body):
  if body.get('kind','owner')=='owner':return None
  if body.get('kind')!='family':raise ValueError('등록 대상을 확인해 줘.')
  values={key:str(body.get(key,'')).strip() for key in ('name','greeting_name')}
  if any(not re.fullmatch(r'[가-힣A-Za-z0-9 ._-]{1,24}',v) for v in values.values()):raise ValueError('가족 이름과 부를 호칭을 각각 24자 이내로 입력해 줘.')
  if len(self.family())>=12:raise ValueError('가족은 최대 12명까지 등록할 수 있어.')
  return {'id':secrets.token_hex(8),**values}
 def write(self,path,data):
  path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  temp=path.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
  with os.fdopen(fd,'w') as f:json.dump(data,f)
  os.replace(temp,path);os.chmod(path,0o600)
 def load(self):
  if self.engine:return self.engine
  sys.path.insert(0,str(self.root/'deps'))
  import cv2,numpy as np
  cv2.setNumThreads(1)
  detector=cv2.FaceDetectorYN.create(str(self.root/'models/face_detection_yunet_2023mar.onnx'),'',(640,360),.85,.3,100)
  recognizer=cv2.FaceRecognizerSF.create(str(self.root/'models/face_recognition_sface_2021dec.onnx'),'')
  self.engine=(cv2,np,detector,recognizer);return self.engine
 def detect(self,jpeg):
  cv,np,detector,recognizer=self.load()
  image=cv.imdecode(np.frombuffer(jpeg,np.uint8),cv.IMREAD_COLOR)
  if image is None:raise ValueError('Camera image could not be decoded.')
  h,w=image.shape[:2];detector.setInputSize((w,h));_,found=detector.detect(image)
  results=[]
  for face in ([] if found is None else found):
   x,y,fw,fh=map(float,face[:4]);x0=max(0,int(x));y0=max(0,int(y));crop=image[y0:min(h,int(y+fh)),x0:min(w,int(x+fw))]
   sharp=float(cv.Laplacian(cv.cvtColor(crop,cv.COLOR_BGR2GRAY),cv.CV_64F).var()) if crop.size else 0
   quality=fw>=55 and fh>=55 and sharp>=35
   feature=None
   if quality:
    feature=recognizer.feature(recognizer.alignCrop(image,face)).reshape(-1)
    feature=feature/max(float(np.linalg.norm(feature)),1e-9)
   results.append({'box':[max(0,x/w),max(0,y/h),min(1,fw/w),min(1,fh/h)],'quality':quality,'width':fw,'sharpness':sharp,'feature':feature})
  return results
 def similarity(self,feature,samples):
  _,np,_,_=self.load()
  scores=sorted((float(np.dot(feature,np.asarray(s,dtype=np.float32))) for s in samples),reverse=True)
  return sum(scores[:2])/min(2,len(scores))
 def enroll(self):
  jpeg=camera_preview.service(self.app).get();faces=self.detect(jpeg)
  if len(faces)!=1:raise ValueError('등록할 사람 혼자 홈캠 앞에 서 줘. 얼굴이 정확히 하나 보여야 등록돼.')
  face=faces[0]
  if not face['quality'] or face['width']<90:raise ValueError('얼굴을 더 가까이, 밝고 선명하게 보여 주세요.')
  feature=face['feature']
  if self.target:
   known=([self.owner()] if self.owner() else [])+self.family()
   if any(self.similarity(feature,p['samples'])>=.45 for p in known):raise ValueError('이미 등록된 얼굴과 일치해. 같은 사람을 다른 가족으로 중복 등록하지 않아.')
  if self.pending and self.similarity(feature,self.pending)<.45:raise ValueError('앞서 등록한 얼굴과 일치하지 않습니다. 같은 사람인지 확인하고 다시 등록해 주세요.')
  self.pending.append(feature.tolist())
  if len(self.pending)==3:
   person={'model':'SFace-2021dec','samples':self.pending,'purpose':'personalization_only','created':time.time()}
   if self.target:
    self.write(self.family_path,{'people':self.family()+[{**person,**self.target}]})
   else:self.write(self.path,{**person,'name':'User'})
   self.pending=[];self.target=None;self.enrollment_until=0;self.unknown_hits=0;self.asked=False
  return self.status()
 def event(self,labels,now,can_greet):
  if not labels:
   self.unknown_hits=0
   if now-self.last_seen>20:self.asked=False
   return None
  self.last_seen=now
  self.unknown_hits=self.unknown_hits+1 if 'unmatched' in labels else 0
  if self.unknown_hits>=3 and not self.asked and now-self.last_ask>120 and can_greet:
   self.last_ask=now;self.asked=True;return '안녕하세요, 누구세요?'
  return None
 def observe(self,can_greet=False,force=False):
  if not force and not self.settings()['enabled']:return {'enabled':False,'faces':[]}
  started=time.monotonic();jpeg=camera_preview.service(self.app).get();faces=self.detect(jpeg);owner=self.owner();result=[]
  known=([{'id':'owner','greeting_name':'User',**owner}] if owner else [])+self.family()
  for face in faces:
   label='uncertain'
   matched=None
   if known and face['quality']:
    scores=sorted(((self.similarity(face['feature'],p['samples']),p) for p in known),key=lambda x:x[0],reverse=True)
    score,person=scores[0]
    if score>=.45 and (len(scores)==1 or score-scores[1][0]>=.05):
     matched=person;label='owner_match' if person['id']=='owner' else 'known_match'
    elif score<.30:label='unmatched'
   result.append({'box':face['box'],'label':label,'quality':face['quality'],**({'person_id':matched['id'],'greeting_name':matched['greeting_name']} if matched else {})})
  elapsed=time.monotonic()-started
  # Initial decode/model loading or a delayed frame cannot authorize movement or speech.
  fresh=elapsed<1.5
  if not fresh:self.unknown_hits=0
  greeting=self.event([f['label'] for f in result],time.monotonic(),can_greet and fresh) if owner and fresh else None
  return {'enabled':True,'registered':owner is not None,'faces':result,'greeting':greeting,'fresh':fresh,'elapsed_ms':round(elapsed*1000),'image':base64.b64encode(jpeg).decode()}
 def action(self,body):
  with self.lock:
   action=body.get('action')
   if action=='status':return self.status()
   if action=='settings':
    if type(body.get('enabled')) is not bool:raise ValueError('enabled must be boolean')
    self.write(self.settings_path,{'enabled':body['enabled']});self.unknown_hits=0
    return self.status()
   if action=='enroll_begin':self.target=self.enrollment_target(body);self.pending=[];self.enrollment_until=time.monotonic()+180;return self.status()
   if action=='enroll_cancel':self.pending=[];self.target=None;self.enrollment_until=0;return self.status()
   if action=='enroll_sample':
    if self.enrollment_until<time.monotonic():self.pending=[];self.target=None;raise ValueError('얼굴 등록 시간이 지났어. 등록 시작을 다시 눌러 줘.')
    self.enrollment_until=time.monotonic()+180;return self.enroll()
   if action=='forget_family':
    key=body.get('id')
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{16}',key):raise ValueError('가족 등록 ID를 확인해 줘.')
    self.write(self.family_path,{'people':[p for p in self.family() if p['id']!=key]});return self.status()
   if action=='forget':
    self.path.unlink(missing_ok=True);self.pending=[];self.unknown_hits=0;return self.status()
   if action=='observe':return self.observe(body.get('can_greet') is True)
   raise ValueError('Unknown visitor mode action.')

_SERVICES={};_LOCK=threading.Lock()
def service(app):
 with _LOCK:
  key=str(app.DATA)
  if key not in _SERVICES:_SERVICES[key]=Presence(app)
  return _SERVICES[key]

def identity_request(app,query):
 import re
 if not re.search(r'나.{0,6}(?:알아보|알아봐|누군지|누구인지)|내 얼굴.{0,8}(?:알아|인식)|recognize me|recognise me|who am i.*camera',query,re.I):return None
 p=service(app)
 with p.lock:
  if not p.owner():return {'text':'아직 User의 얼굴이 등록되지 않았어요. Settings의 User 얼굴 등록에서 먼저 등록해 주세요.'}
  try:
   confirmations=[]
   for _ in range(3):
    r=p.observe(False)
    confirmations.append(r.get('fresh') and any(f['label']=='owner_match' for f in r.get('faces',[])))
   return {'text':'지금 카메라에 보이는 얼굴이 등록된 User의 얼굴과 반복해서 일치했어요.' if all(confirmations) else '지금 영상만으로는 User인지 확실히 확인하지 못했어요. 얼굴을 정면으로 밝게 보여 주세요.'}
  except (ValueError,OSError):return {'text':'현재 카메라 얼굴 확인을 완료하지 못했어요. 카메라 연결과 방문자 모드를 확인해 주세요.'}
