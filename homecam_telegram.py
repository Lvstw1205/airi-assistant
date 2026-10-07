"""Private-owner commands: short homecam video and explicit visitor-guard arming."""
import datetime as dt, json, os, re, secrets, subprocess, threading, time, urllib.request, urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo
import camera_automation, camera_preview, camera_sources

HELP='\n홈캠 / 상황 또는 /homecam: 현재 6초 영상\n홈캠 감시 켜 / 홈캠 감시 꺼: 미등록 얼굴 음성·텔레그램 알림\n홈캠 감시 상태: 현재 감시·얼굴 등록 상태'
CLIP_LOCK=threading.Lock()

def intent(text):
    s=re.sub(r'\s+',' ',text.strip().lower())
    s=re.sub(r'^(?:아이리(?:야|아)?|airi)[,， ]+','',s).rstrip('.! ')
    if re.fullmatch(r'(?:/?홈캠|/homecam)(?:\s*/?\s*(?:상황|영상|보여줘|지금|show|video))?',s):return 'video'
    prefix=r'(?:(?:/?홈캠|/homecam|카메라\s*2(?:번)?)\s*)?(?:감시\s*(?:모드)?|guard)\s*'
    if re.fullmatch(prefix+r'(?:켜|켜줘|켜 줘|켜주세요|켜 주세요|시작|시작해|시작해줘|on)',s):return 'on'
    if re.fullmatch(prefix+r'(?:꺼|꺼줘|꺼 줘|꺼주세요|꺼 주세요|중지|중지해|중지해줘|off)',s):return 'off'
    if re.fullmatch(r'(?:/?홈캠|/homecam)\s*(?:감시\s*(?:모드)?\s*)?(?:상태|status)(?:\s*(?:알려줘|확인))?',s):return 'status'
    if re.fullmatch(prefix+r'(?:상태|status)',s):return 'status'
    return None

def guard_reply(app,cfg,action):
    service=camera_automation.service(app)
    if action in ('on','off'):
        s=service.set_home(action=='on',cfg)
        if action=='off':return '홈캠 감시와 방문자 대화를 껐어. 요청할 때만 영상을 가져올게.'
        return '홈캠 감시를 켜도록 설정했어. 첫 영상을 확인 중이야. 미등록 얼굴이 선명하게 3번 확인되면 Mac 스피커로 “'+s['home_warning']+'”라고 말하고 홈캠 마이크로 대답을 잠깐 들을게. 등록된 가족에게는 지정한 호칭으로 인사해.'
    s=service.status();voice=s['visitor_dialogue']
    return ('홈캠 '+('감시 중' if s['home_active'] else '감시 준비 / 연결 확인' if s['home_armed'] else '감시 꺼짐')+' · '+s['home_state']+
            '\nUser 얼굴 '+('등록됨' if s['registered'] else '등록 필요')+' · 가족 '+str(len(s['family']))+'명 등록'+
            '\n경고 음성 '+('준비됨' if voice['warning_ready'] else '준비 전')+' · 방문자 대화 '+voice['state']+
            ('\n'+voice['error'] if voice['error'] else ''))

def chat_request(app,text):
    action=intent(text)
    if action not in ('on','off','status'):return None
    import telegram_bridge
    return guard_reply(app,telegram_bridge.config(app),action)

def command(app,cfg,text,key,bridge):
    action=intent(text)
    if not action:return None
    if action in ('on','off','status'):return guard_reply(app,cfg,action)
    path,stamp=record_clip(app)
    bridge.enqueue(app,cfg,key+':home-video','카메라 2 · 요청 후 촬영한 약 6초 영상\n'+stamp+' · 음성 녹음 없음',{'homecam_clip':path.stem,'expires':time.time()+600,'protect_content':True})
    return '현재 홈캠 영상을 촬영했어. 약 6초 클립을 보낼게. 연속 실시간 방송은 아니야.'

def folder(app):
    p=app.DATA/'telegram/camera-clips';p.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(p,0o700);return p

def clip_path(app,key):
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{32}',key):raise ValueError('홈캠 영상 ID 오류')
    base=folder(app);p=base/(key+'.mp4')
    if p.is_symlink() or not p.is_file() or p.resolve().parent!=base.resolve() or not 0<p.stat().st_size<=10*1024*1024:raise ValueError('홈캠 영상이 만료되었거나 유효하지 않아.')
    return p

def cleanup(app):
    for p in folder(app).glob('*.mp4'):
        if re.fullmatch(r'[a-f0-9]{32}',p.stem) and not p.is_symlink() and p.stat().st_mtime<time.time()-600:p.unlink(missing_ok=True)

def record_clip(app):
    if not CLIP_LOCK.acquire(blocking=False):raise ValueError('홈캠 영상을 이미 촬영 중이야.')
    path=None
    try:
        cleanup(app);preview=camera_preview.service(app);frames=[]
        # Keep only a bounded six-second capture and discard frames after encoding.
        for _ in range(30):frames.append(preview.get())
        if sum(map(len,frames))>24*1024*1024:raise ValueError('홈캠 영상 크기 제한을 넘었어.')
        path=folder(app)/(secrets.token_hex(16)+'.mp4')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        p=subprocess.run([camera_sources.service(app,2).ffmpeg(),'-nostdin','-hide_banner','-loglevel','error','-f','image2pipe','-framerate','5','-vcodec','mjpeg','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(path)],input=b''.join(frames),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
        if p.returncode:raise ValueError('홈캠 영상을 MP4로 만들지 못했어.')
        clip_path(app,path.stem)
        return path,dt.datetime.now(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        if path:path.unlink(missing_ok=True)
        raise
    finally:CLIP_LOCK.release()

def send_clip(app,payload,bridge):
    path=clip_path(app,payload['homecam_clip']);boundary='AIRI'+secrets.token_hex(16);parts=[]
    for key,value in [('chat_id',payload['chat_id']),('caption',payload.get('text','')[:900]),('supports_streaming','true'),('protect_content','true')]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="AIRI-homecam.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
    req=urllib.request.Request('https://api.telegram.org/bot'+bridge.token(app)+'/sendVideo',data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=60) as r:result=json.load(r)
    except urllib.error.HTTPError as error:raise bridge.TelegramError(error.code) from None
    except (OSError,ValueError):raise bridge.TelegramError() from None
    if not result.get('ok'):raise bridge.TelegramError(result.get('error_code',0))
    path.unlink(missing_ok=True)
