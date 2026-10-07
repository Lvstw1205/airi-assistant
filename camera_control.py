"""Bounded LAN-only ONVIF camera motion. No cloud credentials or new listener."""
import base64,datetime as dt,hashlib,json,os,re,threading,time,urllib.request,urllib.error
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
import camera_bridge
NS={'tt':'http://www.onvif.org/ver10/schema','trt':'http://www.onvif.org/ver10/media/wsdl'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('Camera redirect refused.')
class Controller:
 def __init__(self,app):self.app=app;self.lock=threading.Lock();self.cache=None;self.last_move=0;self.cancel=threading.Event()
 def config(self):
  c=camera_bridge.service(self.app).config()
  if not c['enabled']:raise ValueError('Camera is disabled.')
  if not all(c.get(k) for k in ('host','username','password')):raise ValueError('Camera account is not configured.')
  return c
 def base(self,c):return 'http://'+('['+c['host']+']' if ':' in c['host'] else c['host'])+':2020'
 def soap(self,url,action,body,c):
  parsed=urlsplit(url)
  if parsed.scheme!='http' or parsed.hostname!=c['host'] or parsed.port!=2020 or not parsed.path.startswith('/onvif/') or parsed.username or parsed.password:raise ValueError('Unexpected ONVIF endpoint.')
  nonce=os.urandom(16);created=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
  digest=base64.b64encode(hashlib.sha1(nonce+created.encode()+c['password'].encode()).digest()).decode()
  security=f'<wsse:Security s:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>{escape(c["username"])}</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</wsse:Nonce><wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security>'
  envelope=f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><s:Header>{security}</s:Header><s:Body>{body}</s:Body></s:Envelope>'
  passwords=urllib.request.HTTPPasswordMgrWithDefaultRealm();passwords.add_password(None,self.base(c),c['username'],c['password'])
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPDigestAuthHandler(passwords))
  try:
   req=urllib.request.Request(url,data=envelope.encode(),headers={'Content-Type':'application/soap+xml; charset=utf-8; action="'+action+'"'})
   with opener.open(req,timeout=4) as response:data=response.read(262145)
   if len(data)>262144:raise ValueError()
   root=ET.fromstring(data)
   if root.find('.//{http://www.w3.org/2003/05/soap-envelope}Fault') is not None:raise ValueError()
   return root
  except Exception:raise ValueError('ONVIF request failed. Check camera power and Camera Account permissions.') from None
 def discover(self):
  c=self.config();identity=(c['host'],c['username'],c['password'])
  if self.cache and self.cache[0]==identity:return c,self.cache[1]
  root=self.soap(self.base(c)+'/onvif/device_service','http://www.onvif.org/ver10/device/wsdl/GetCapabilities','<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>',c)
  media=root.find('.//tt:Media/tt:XAddr',NS);ptz=root.find('.//tt:PTZ/tt:XAddr',NS)
  if media is None or ptz is None:raise ValueError('Camera did not advertise ONVIF pan/tilt support.')
  profiles=self.soap(media.text,'http://www.onvif.org/ver10/media/wsdl/GetProfiles','<trt:GetProfiles/>',c)
  profile=next((x for x in profiles.findall('.//trt:Profiles',NS) if x.find('tt:PTZConfiguration',NS) is not None),None)
  if profile is None:raise ValueError('Camera has no PTZ-enabled video profile.')
  info={'endpoint':ptz.text,'token':profile.attrib['token'],'configuration_token':profile.find('tt:PTZConfiguration',NS).attrib['token']};self.cache=(identity,info);return c,info
 def send(self,verb,content=''):
  c,info=self.discover();token=escape(info['token'])
  return self.soap(info['endpoint'],'http://www.onvif.org/ver20/ptz/wsdl/'+verb,f'<tptz:{verb}><tptz:ProfileToken>{token}</tptz:ProfileToken>{content}</tptz:{verb}>',c)
 def status(self):
  root=self.send('GetStatus');pan=root.find('.//tt:PanTilt',NS)
  return {'available':True,'position':pan.attrib if pan is not None else None,'pulse_seconds':.65,'gesture_control':'browser opt-in only'}
 def stop(self):
  self.cancel.set()
  return self.halt()
 def halt(self):
  self.send('Stop','<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>')
  return {'ok':True,'direction':'stop','message':'카메라 정지 명령을 보냈어요.'}
 def move(self,direction,speed=.7,pulse=.65):
  if direction=='stop':return self.stop()
  if type(speed) not in (int,float) or not .2<=speed<=1:raise ValueError('Camera speed must be 0.2 to 1.')
  if type(pulse) not in (int,float) or not .15<=pulse<=.65:raise ValueError('Camera pulse must be 0.15 to 0.65 seconds.')
  vectors={'left':(-speed,0),'right':(speed,0),'up':(0,speed),'down':(0,-speed)}
  if direction not in vectors:raise ValueError('Choose left, right, up, down or stop.')
  if not self.lock.acquire(blocking=False):raise ValueError('Camera is already moving.')
  try:
   self.cancel.clear()
   if time.monotonic()-self.last_move<.15:raise ValueError('Wait briefly between camera movements.')
   before=self.status().get('position')
   x,y=vectors[direction]
   try:
    self.send('ContinuousMove',f'<tptz:Velocity><tt:PanTilt x="{x}" y="{y}"/></tptz:Velocity><tptz:Timeout>PT2S</tptz:Timeout>')
    time.sleep(pulse)
   finally:self.halt()
   self.last_move=time.monotonic()
   time.sleep(.1)
   try:after=self.status().get('position')
   except ValueError:after=None
   axis='x' if direction in ('left','right') else 'y'
   try:changed=abs(float(after[axis])-float(before[axis]))>.002
   except (TypeError,KeyError,ValueError):changed=False
   label={'left':'왼쪽','right':'오른쪽','up':'위쪽','down':'아래쪽'}[direction]
   message=(label+' 이동 후 정지했고, 카메라 위치 변화도 확인했어요.') if changed else ('이동 명령은 전송했지만 실제 위치 변화를 확인하지 못했어요. 카메라가 회전 끝 지점인지 확인해 주세요.')
   return {'ok':changed,'direction':direction,'speed':speed,'pulse_seconds':pulse,'movement_verified':changed,'verification':'onvif_position_change','before':before,'after':after,'message':message}

  finally:self.lock.release()
 def half_turn(self):
  if not self.lock.acquire(blocking=False):raise ValueError('Camera is already moving.')
  self.cancel.clear()
  try:
   c,info=self.discover()
   device=self.soap(self.base(c)+'/onvif/device_service','http://www.onvif.org/ver10/device/wsdl/GetDeviceInformation','<tds:GetDeviceInformation/>',c)
   models=[e.text or '' for e in device.iter() if e.tag.endswith('}Model')]
   if not any('C200' in model for model in models):raise ValueError('180-degree approximation is configured only for Tapo C200.')
   before=self.status()['position'];x=float(before['x']);y=float(before['y']);target=half_turn_target(x)
   self.send('AbsoluteMove',f'<tptz:Position><tt:PanTilt x="{target}" y="{y}"/></tptz:Position><tptz:Speed><tt:PanTilt x="0.7" y="0.7"/></tptz:Speed>')
   deadline=time.monotonic()+15;after=None;reached=False
   while time.monotonic()<deadline and not self.cancel.wait(.2):
    after=self.status()['position']
    if abs(float(after['x'])-target)<.015:reached=True;break
   cancelled=self.cancel.is_set()
   return {'ok':reached and not cancelled,'approximate_degrees':180,'before':before,'after':after,'cancelled':cancelled,'message':'약 180도 회전 목표 위치를 확인했습니다.' if reached and not cancelled else '회전을 멈췄습니다. 목표 위치 도달은 확인되지 않았습니다.'}
  finally:
   try:self.halt()
   finally:self.last_move=time.monotonic();self.lock.release()
_CONTROLLERS={};_LOCK=threading.Lock()
def half_turn_target(x):
 # C200 mechanical pan is 340 degrees; normalized ONVIF range is [-1,1].
 # This is an approximate angular conversion, not physical angle calibration.
 delta=180/170
 for candidate in (x-delta,x+delta):
  if -1<=candidate<=1:return candidate
 raise ValueError('현재 위치에서는 기계적 회전 한계 때문에 한 방향으로 180도 돌 수 없습니다. 먼저 조금 왼쪽이나 오른쪽으로 이동해 주세요.')
def service(app):
 with _LOCK:return _CONTROLLERS.setdefault(str(app.DATA),Controller(app))
def requested_direction(query):
 q=query.strip().lower()
 if re.search(r'번역|예시|코드|방법|translate|example|how to|do not|don.t|돌리지|움직이지',q):return None
 if re.search(r'(?:카메라|camera).{0,15}(?:멈춰|정지|stop)|^(?:stop camera|카메라 스톱)$',q):return 'stop'
 short=re.fullmatch(r'(?:아이리[ ,]*|airi[ ,]*)?(?:카메라(?:를|는)?|camera)\s*(?:좀\s*|to\s+the\s+)?(왼쪽|좌측|오른쪽|우측|위|위로|위쪽|아래|아래로|아래쪽|left|right|up|down)(?:으로|로)?(?:\s*(?:조금|좀|please))?[.! ]*',q)
 if short:
  return {'왼쪽':'left','좌측':'left','오른쪽':'right','우측':'right','위':'up','위로':'up','위쪽':'up','아래':'down','아래로':'down','아래쪽':'down'}.get(short[1],short[1])
 if not re.search(r'돌려|움직여|이동해|비춰|\b(pan|tilt|move|turn)\b',q):return None
 matches=[d for d,pattern in [('left',r'왼쪽|좌측|\bleft\b'),('right',r'오른쪽|우측|\bright\b'),('up',r'위로|위쪽|\bup\b'),('down',r'아래로|아래쪽|\bdown\b')] if re.search(pattern,q)]
 if len(matches)!=1:return None
 if not re.search(r'카메라|camera|\b(pan|tilt)\b|^(?:조금\s*(?:더\s*)?)?(?:왼쪽|오른쪽|위로|아래로|위쪽|아래쪽)',q):return None
 return matches[0]
def chat_request(app,query):
 direction=requested_direction(query)
 if not direction:
  if re.search(r'카메라|camera',query,re.I) and re.search(r'움직|돌릴|회전|이동.*기능|pan|tilt|movement',query,re.I) and re.search(r'기능|가능|할 수|있어|없어|못해|can|able|support',query,re.I):
   try:
    service(app).status()
    return {'text':'카메라 회전 기능이 연결되어 있어요. “카메라 왼쪽으로”, “카메라 오른쪽으로”, “카메라 위로”, “카메라 아래로”, “카메라 멈춰”로 조작할 수 있어요. 손 제스처는 Settings의 Camera movement에서 켤 수 있습니다.'}
   except ValueError as e:return {'text':'카메라 회전 기능은 설치되어 있지만 현재 연결 확인에 실패했어요: '+str(e)}
  return None
 try:return {'text':service(app).move(direction)['message']}
 except ValueError as e:return {'text':'카메라 이동을 완료하지 못했어요: '+str(e)}
