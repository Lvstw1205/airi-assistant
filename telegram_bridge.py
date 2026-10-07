import sys
import video_telegram
import homecam_telegram
import stock101_telegram
"""Private-owner Telegram bridge using outbound polling and a durable outbox."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import telegram_news
from urllib.parse import quote

LOCK=threading.RLock()
STATUS='봇 연결 전'
HELP='AIRI 원격 명령\n일반 메시지: 대화·일정·스킬 요청\n/tasks: 일정과 작업 목록\n/work 지시: 백그라운드 작업 생성\n/result 번호: 결과와 생성 파일 받기\n/approvals: 실행 승인 목록\n/alerts on 또는 off: 알림 켜기/끄기\n문서에 /work 지시를 캡션으로 붙이거나, 보낸 파일에 답장으로 /work 지시를 보내세요. MD 파일에 /skill 캡션을 붙이면 스킬로 저장합니다. 음성 메시지도 지원합니다.'

HELP+='\n/muse 지시: Muse 작업 요청 · /muse status: 상태 · /muse result ID: 결과'

HELP+='\n/video 지시: 30초 이상 영상 제작\n/videos: 영상 진행 상태\n/video_result [작업ID]: 영상 받기\n/video_review 작업ID approve|reject 피드백: 검토 결과 저장'

HELP+=stock101_telegram.HELP
HELP+=homecam_telegram.HELP
import airi_studio
HELP+=airi_studio.HELP

def init(app):
    telegram_news.init(app)
    folder=app.DATA/'telegram';folder.mkdir(exist_ok=True);folder.chmod(0o700)
    with app.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS telegram_config(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS telegram_inbox(generation TEXT,update_id INTEGER,state TEXT,created REAL,PRIMARY KEY(generation,update_id))')
        c.execute('CREATE TABLE IF NOT EXISTS telegram_outbox(generation TEXT,key TEXT,payload TEXT,state TEXT,attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,created REAL,PRIMARY KEY(generation,key))')
        c.execute('CREATE TABLE IF NOT EXISTS telegram_results(generation TEXT,task_id INTEGER,version TEXT,PRIMARY KEY(generation,task_id))')
        c.execute('CREATE TABLE IF NOT EXISTS telegram_files(generation TEXT,message_id INTEGER,attachment_id TEXT,PRIMARY KEY(generation,message_id))')
        c.execute("UPDATE telegram_inbox SET state='unknown' WHERE state='processing'")
        c.execute("UPDATE telegram_outbox SET state='pending' WHERE state='sending'")


def config(app):
    rows=app.rows('SELECT value FROM telegram_config WHERE id=1')
    return json.loads(rows[0]['value']) if rows else {'enabled':False}


def store(app,value):
    with app.db() as c:c.execute('INSERT OR REPLACE INTO telegram_config VALUES(1,?)',(json.dumps(value),))


def token(app):
    path=app.DATA/'telegram/bot-token'
    return path.read_text().strip() if path.exists() else ''


class TelegramError(Exception):
    def __init__(self,code=0,retry_after=30):
        self.code=code;self.retry_after=min(3600,max(5,retry_after))
        super().__init__({401:'봇 토큰이 유효하지 않습니다.',403:'봇이 차단되었거나 대화를 시작하지 않았습니다.',409:'같은 봇을 다른 프로그램이 사용 중입니다.',429:'텔레그램 요청 제한으로 잠시 대기합니다.'}.get(code,'텔레그램 연결을 확인하지 못했습니다.'))


def request(app,method,body=None,secret=None,timeout=35):
    key=secret if secret is not None else token(app)
    if not re.fullmatch(r'\d{5,20}:[A-Za-z0-9_-]{20,100}',key):raise TelegramError(401)
    req=urllib.request.Request('https://api.telegram.org/bot'+key+'/'+method,
        data=json.dumps(body or {}).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:data=json.load(r)
    except urllib.error.HTTPError as error:
        retry=30
        try:retry=json.loads(error.read(4000)).get('parameters',{}).get('retry_after',30)
        except Exception:pass
        raise TelegramError(error.code,retry) from None
    except (OSError,ValueError):raise TelegramError() from None
    if not data.get('ok'):raise TelegramError(data.get('error_code',0))
    return data['result']


def public(app):
    cfg=config(app)
    return {'enabled':cfg.get('enabled',False),'has_token':bool(token(app)),
            'bot_username':cfg.get('bot_username',''),'paired':bool(cfg.get('user_id')),
            'pair_pending':cfg.get('pair_until',0)>time.time(),
            'notifications':cfg.get('notifications',True),'status':STATUS,'news_schedule':telegram_news.public(app),
            'owner':str(cfg.get('user_id',''))[-4:] if cfg.get('user_id') else '',
            'queued':len(app.rows("SELECT key FROM telegram_outbox WHERE generation=? AND state IN ('pending','sending')",(cfg.get('generation',''),)))}


def configure(app,body):
    with LOCK:
        cfg=config(app);key=body.get('token','').strip()
        for name in ('enabled','notifications','pair'):
            if name in body and type(body[name]) is not bool:raise ValueError('설정 값을 확인하세요.')
        if key:
            if not re.fullmatch(r'\d{5,20}:[A-Za-z0-9_-]{20,100}',key):raise ValueError('BotFather에서 받은 봇 토큰을 확인하세요.')
            me=request(app,'getMe',secret=key,timeout=10)
            if not me.get('is_bot'):raise ValueError('봇 계정이 아닙니다.')
            hook=request(app,'getWebhookInfo',secret=key,timeout=10)
            if hook.get('url'):raise ValueError('이 봇은 다른 웹훅에 연결되어 있습니다. AIRI 전용 봇을 사용하세요.')
            recent=request(app,'getUpdates',{'offset':-1,'timeout':0,'allowed_updates':['message','callback_query']},secret=key,timeout=10)
            path=app.DATA/'telegram/bot-token';temp=path.with_suffix('.tmp');temp.write_text(key);temp.chmod(0o600);temp.replace(path)
            cfg={'generation':secrets.token_hex(12),'enabled':True,'notifications':True,'bot_username':me.get('username',''),
                 'offset':max((u['update_id'] for u in recent),default=-1)+1,'user_id':None,'chat_id':None}
            body={**body,'pair':True}
        if not token(app):raise ValueError('먼저 봇 토큰을 등록하세요.')
        for name in ('enabled','notifications'):
            if name in body:
                if type(body[name]) is not bool:raise ValueError('설정 값을 확인하세요.')
                cfg[name]=body[name]
        code=None
        if body.get('pair'):
            code=secrets.token_urlsafe(18);cfg.update(pair_hash=hashlib.sha256(code.encode()).hexdigest(),pair_until=time.time()+600,pair_attempts=0)
        store(app,cfg)
        if 'news_schedule' in body:telegram_news.configure(app,body['news_schedule'])
        return {**public(app),**({'pair_url':'https://t.me/'+cfg['bot_username']+'?start=airi_'+code,'pair_command':'/start airi_'+code} if code else {})}


def chunks(text,limit=3500):
    part='';units=0
    for char in str(text):
        size=2 if ord(char)>0xffff else 1
        if units+size>limit:yield part;part='';units=0
        part+=char;units+=size
    if part:yield part


def enqueue(app,cfg,key,text,extra=None):
    if not cfg.get('chat_id'):return
    with app.db() as c:
        for index,part in enumerate(chunks(text[:60000])):
            payload={'chat_id':cfg['chat_id'],'text':part,**(extra or {} if index==0 else {})}
            c.execute("INSERT OR IGNORE INTO telegram_outbox(generation,key,payload,state,created) VALUES(?,?,?,'pending',?)",
                      (cfg['generation'],key+':'+str(index),json.dumps(payload),time.time()))


def local(app,path,body=None,raw=None,headers=None,timeout=260):
    req=urllib.request.Request('http://127.0.0.1:'+str(app.PORT)+'/api/'+path,
        data=raw if raw is not None else None if body is None else json.dumps(body).encode(),
        headers={'X-AIRI-Token':(app.DATA/'session-token').read_text().strip(),'Content-Type':'application/json',**(headers or {})})
    try:r=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout)
    except urllib.error.HTTPError as error:
        if error.code==409:raise ValueError('AIRI가 다른 요청을 처리 중이야. 잠시 뒤 다시 보내줘.') from None
        if error.code==400:
            try:message=json.loads(error.read(4000)).get('error','요청 내용을 확인해 주세요.')
            except ValueError:message='요청 내용을 확인해 주세요.'
            raise ValueError(message) from None
        raise ValueError('Mac의 AIRI가 요청을 완료하지 못했어. /tasks에서 상태를 확인해줘.') from None
    with r:
        if path=='chat':
            text='';finished=False
            for line in r:
                part=json.loads(line)
                if part['type']=='token':text+=part['text']
                if part['type']=='error':raise ValueError(part['message'])
                if part['type']=='done':finished=True
            if not finished:raise ValueError('처리가 완료됐는지 확인하지 못했습니다. /tasks에서 확인하세요. 자동 재실행하지 않습니다.')
            return text
        return json.load(r)


def private_owner(cfg,message):
    user=message.get('from',{});chat=message.get('chat',{})
    return (chat.get('type')=='private' and not user.get('is_bot') and user.get('id')==cfg.get('user_id')
            and chat.get('id')==cfg.get('chat_id') and cfg.get('user_id') is not None)


def pair(app,cfg,message):
    text=message.get('text','');chat=message.get('chat',{});user=message.get('from',{})
    if chat.get('type')!='private' or user.get('is_bot') or message.get('forward_origin') or not text.startswith('/start airi_'):return False
    if cfg.get('pair_until',0)<time.time() or cfg.get('pair_attempts',0)>=10:return False
    cfg['pair_attempts']=cfg.get('pair_attempts',0)+1
    code=text[len('/start airi_'):].strip()
    if not secrets.compare_digest(hashlib.sha256(code.encode()).hexdigest(),cfg.get('pair_hash','')):
        store(app,cfg);return False
    if cfg.get('user_id') and cfg['user_id']!=user['id']:
        cfg['generation']=secrets.token_hex(12)
    cfg.update(user_id=user['id'],chat_id=chat['id'],pair_until=0,pair_hash='',paired_at=time.time())
    store(app,cfg)
    with app.db() as c:
        for task in c.execute('SELECT id,status,result FROM tasks').fetchall():
            c.execute('INSERT OR REPLACE INTO telegram_results VALUES(?,?,?)',(cfg['generation'],task['id'],version(dict(task))))
    enqueue(app,cfg,'paired:'+str(message['message_id']),'User, AIRI 연결됐어. 이 개인 대화에서 명령하면 Mac의 AIRI가 처리할게.\n\n'+HELP)
    return True


def download(app,descriptor):
    if descriptor.get('file_size',0)>20*1024*1024:raise ValueError('파일은 20MB 이하로 보내세요.')
    result=request(app,'getFile',{'file_id':descriptor['file_id']})
    path=result.get('file_path','')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or '..' in path:raise ValueError('파일 경로를 확인하지 못했습니다.')
    try:
        with urllib.request.urlopen('https://api.telegram.org/file/bot'+token(app)+'/'+path,timeout=30) as r:data=r.read(20*1024*1024+1)
    except OSError:raise TelegramError() from None
    if len(data)>20*1024*1024:raise ValueError('파일은 20MB 이하로 보내세요.')
    return data


def work(app,instructions,attachment_ids):
    if not instructions.strip():raise ValueError('/work 뒤에 실행할 작업을 적어주세요.')
    app.attachments.validate_ids(app,attachment_ids)
    now=dt.datetime.now(app.schedule_features.ZONE)
    with app.db() as c:
        cursor=c.execute("INSERT INTO tasks(title,due_date,due_time,notes,created,action,status,run_at,instructions,attachment_ids) VALUES(?,?,?,'',?,'ai','scheduled',?,?,?)",
                         (instructions[:100],now.date().isoformat(),now.strftime('%H:%M'),app.now(),app.now(),instructions[:12000],json.dumps(attachment_ids)))
        key=cursor.lastrowid
    app.event('saved','텔레그램에서 작업 예약: '+str(key))
    return '작업 #'+str(key)+'을 등록했어. Mac이 작업 가능한 상태면 실행하고 완료 알림을 보낼게.'


def approvals(app,cfg,key):
    rows=app.rows("SELECT id,payload FROM approvals WHERE status='pending' ORDER BY created DESC LIMIT 10")
    if not rows:enqueue(app,cfg,key,'승인 대기 중인 작업이 없어.');return
    for row in rows:
        data=json.loads(row['payload'])
        keyboard={'inline_keyboard':[[{'text':'승인하고 실행','callback_data':'approve:'+row['id']},{'text':'거절','callback_data':'reject:'+row['id']}]]}
        enqueue(app,cfg,key+':'+row['id'],str(data.get('name','작업'))+'\n'+str(data.get('message',''))[:2800],{'reply_markup':keyboard})


def command(app,cfg,message,key):
    text=message.get('text',message.get('caption','')).strip();file_ids=[]
    if message.get('forward_origin'):return '전달한 메시지는 명령으로 실행하지 않았어. 원하는 작업을 직접 적어줘.'
    organization_reply=airi_studio.command(text,request_id='telegram-'+key)
    if organization_reply is not None:return organization_reply
    stock_reply=stock101_telegram.command(app,cfg,text,key,sys.modules[__name__])
    if stock_reply is not None:return stock_reply
    if message.get('document'):
        doc=message['document'];data=download(app,doc);name=doc.get('file_name','file.txt')
        result=local(app,'upload',raw=data,headers={'Content-Type':'application/octet-stream','X-AIRI-Filename':quote(name,safe='')})
        file_ids=[result['id']]
        with app.db() as c:c.execute('INSERT OR REPLACE INTO telegram_files VALUES(?,?,?)',(cfg['generation'],message['message_id'],result['id']))
        if text=='/skill':
            if Path(name).suffix.lower() not in ('.md','.markdown'):raise ValueError('/skill은 Markdown 파일에 사용하세요.')
            local(app,'skills',{'name':Path(name).stem[:100],'content':result['text']})
            return name+' 스킬을 저장했어.'
        if not text:return name+' 파일을 저장했어. 이 파일에 답장으로 /work 작업 지시를 보내면 분석할게.'
    if message.get('voice'):
        voice=message['voice']
        if voice.get('duration',0)>300:raise ValueError('음성은 5분 이내로 보내주세요.')
        with tempfile.TemporaryDirectory(dir=app.DATA/'telegram') as folder:
            source=Path(folder)/'voice.ogg';wav=Path(folder)/'voice.wav';source.write_bytes(download(app,voice))
            ffmpeg=shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
            subprocess.run([ffmpeg,'-v','error','-i',str(source),'-t','300','-ac','1','-ar','16000',str(wav)],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            text=local(app,'transcribe',raw=wav.read_bytes(),headers={'Content-Type':'audio/wav','X-AIRI-Language':'auto'})['text'].strip()
        if not text:return '음성을 이해하지 못했어. 다시 보내거나 글로 적어줘.'
    if not text:return '글, 문서 또는 음성 메시지로 보내줘. /help에서 사용법을 볼 수 있어.'
    camera_reply=homecam_telegram.command(app,cfg,text,key,sys.modules[__name__])
    if camera_reply is not None:return camera_reply
    import humanlike_mind,si_service
    direct=humanlike_mind.preflight(app,text) or si_service.command(app,text)
    if direct is not None:return direct
    if len(text)>12000:raise ValueError('한 번에 12,000자 이내로 보내세요.')
    if text in ('/start','/help'):return HELP+'\n/local: 로컬 작업실 종류\n/local summary 자료: 로컬 요약\n/local status: 작업 상태\n/local result ID: 결과 보기'
    import local_workbench,muse_dispatch
    muse_reply=muse_dispatch.chat_request(app,text,request_key='telegram:'+str(cfg['generation'])+':'+key,source='telegram',generation=cfg['generation'])
    if muse_reply:return muse_reply['text']
    if text.strip().startswith('/local'):
        reply=message.get('reply_to_message',{}).get('message_id')
        if reply and not file_ids:file_ids=[r['attachment_id'] for r in app.rows('SELECT attachment_id FROM telegram_files WHERE generation=? AND message_id=?',(cfg['generation'],reply))]
        local_reply=local_workbench.chat_request(app,text,request_key='telegram:'+str(cfg['generation'])+':'+key,attachment_ids=file_ids)
        if local_reply:return local_reply['text']
    video_reply=video_telegram.command(app,cfg,text,key,sys.modules[__name__])
    if video_reply is not None:return video_reply
    news=telegram_news.chat_request(app,text,destination="telegram")
    if news:return news['text']
    if text=='/tasks':
        rows=app.rows("SELECT id,title,due_date,due_time,status FROM tasks WHERE archived_at='' ORDER BY due_date,due_time LIMIT 30")
        return '\n'.join(f"#{t['id']} · {t['due_date']} {t['due_time']} · {t['title']} · {t['status']}" for t in rows) or '등록된 일정이 없어.'
    if text.startswith('/work '):
        reply=message.get('reply_to_message',{}).get('message_id')
        if reply and not file_ids:file_ids=[r['attachment_id'] for r in app.rows('SELECT attachment_id FROM telegram_files WHERE generation=? AND message_id=?',(cfg['generation'],reply))]
        return work(app,text[6:],file_ids)
    if file_ids and not text.startswith('/'):return work(app,text,file_ids)
    if text.startswith('/result '):
        number=text[8:].strip()
        if not number.isdigit():raise ValueError('/result 뒤에 작업 번호를 적어주세요.')
        rows=app.rows('SELECT * FROM tasks WHERE id=?',(int(number),))
        if not rows:raise ValueError('해당 작업을 찾지 못했어.')
        task=rows[0]
        if task['action']=='image':
            jobs=app.rows("SELECT id,task_id,prompt FROM image_jobs WHERE task_id=? AND state='completed' ORDER BY created DESC LIMIT 1",(task['id'],))
            if jobs:enqueue_image(app,cfg,key+':image',jobs[0])
        for file in app.task_results.files(app,int(number)):
            if file['size']<=20*1024*1024:enqueue(app,cfg,key+':file:'+file['key'],file['name'],{'document_task':int(number),'document_key':file['key']})
        return '#'+number+' · '+task['title']+'\n'+task['status']+'\n\n'+(task['result'] or '아직 결과가 없습니다.')
    if text=='/approvals':approvals(app,cfg,key);return ''
    if text in ('/alerts on','/alerts off'):
        with LOCK:
            latest=config(app);latest['notifications']=text.endswith(' on');store(app,latest)
        return '알림을 켰어.' if text.endswith(' on') else '알림을 껐어. 명령은 계속 받을게.'
    response=local(app,'chat',{'message':text,'voice':False})
    if re.search(r'승인|approval',response,re.I):approvals(app,cfg,key+':approvals')
    return response


def receive(app,update):
    with LOCK:
        cfg=config(app)
        if not cfg.get('enabled'):return
        generation=cfg.get('generation','');uid=update['update_id']
        callback=update.get('callback_query');message=callback.get('message',{}) if callback else update.get('message',{})
        if callback:message={**message,'from':callback.get('from',{})}
        with app.db() as c:
            cursor=c.execute("INSERT OR IGNORE INTO telegram_inbox VALUES(?,?,'processing',?)",(generation,uid,time.time()))
            if not cursor.rowcount:return
        cfg['offset']=max(cfg.get('offset',0),uid+1);store(app,cfg)
        if not callback and pair(app,cfg,message):
            with app.db() as c:c.execute("UPDATE telegram_inbox SET state='done' WHERE generation=? AND update_id=?",(generation,uid))
            return
        if not private_owner(cfg,message):
            with app.db() as c:c.execute("UPDATE telegram_inbox SET state='ignored' WHERE generation=? AND update_id=?",(generation,uid))
            return
    key='reply:'+str(uid)
    try:
        app.local_learning.touch()
        if callback:
            data=callback.get('data','')
            if data.startswith('st101:'):
                try:request(app,'answerCallbackQuery',{'callback_query_id':callback['id'],'text':'Stock101 상태를 확인하고 있습니다.'})
                except TelegramError:pass
                answer=stock101_telegram.callback(app,cfg,data,key,sys.modules[__name__])
            else:
                if not re.fullmatch(r'(approve|reject):[a-f0-9]{32}',data):raise ValueError('승인 버튼을 다시 확인해줘.')
                verb,aid=data.split(':')
                result=local(app,'decision',{'id':aid,'approve':verb=='approve'})
                answer='실행 상태: '+result.get('status','확인 필요')+'\n'+str(result.get('result','') or '')
                try:request(app,'answerCallbackQuery',{'callback_query_id':callback['id'],'text':answer[:180]})
                except TelegramError:pass
        else:answer=command(app,cfg,message,key)
        if answer:enqueue(app,cfg,key,answer)
        final='done'
    except Exception as error:
        text=str(error)[:300] if isinstance(error,(ValueError,TelegramError)) else '작업 결과를 확인하지 못했어. /tasks 또는 /result 번호로 확인해줘. 자동 재실행하지 않았어.'
        enqueue(app,cfg,key,'AIRI: '+text);final='unknown'
    with app.db() as c:c.execute('UPDATE telegram_inbox SET state=? WHERE generation=? AND update_id=?',(final,generation,uid))


def version(task):return hashlib.sha256((task['status']+'\n'+task.get('result','')).encode()).hexdigest()


def notifications(app,cfg,current=None):
    if not cfg.get('user_id') or not cfg.get('notifications',True):return
    video_telegram.notifications(app,cfg,sys.modules[__name__])
    airi_studio.notifications(app,cfg,sys.modules[__name__])
    current=current or dt.datetime.now(dt.timezone.utc)
    for job in app.rows("SELECT j.id,j.task_id,j.prompt FROM image_jobs j JOIN tasks t ON t.id=j.task_id WHERE j.state='completed' AND t.action='image' AND t.archived_at='' AND t.status='completed'"):
        enqueue_image(app,cfg,'result:image:'+job['id'],job)
    for task in app.rows("SELECT * FROM tasks WHERE archived_at='' AND status IN ('completed','partial','failed','unknown','awaiting_approval')"):
        digest=version(task)
        with app.db() as c:
            old=c.execute('SELECT version FROM telegram_results WHERE generation=? AND task_id=?',(cfg['generation'],task['id'])).fetchone()
            if old and old['version']==digest:continue
            enqueue(app,cfg,'result:'+str(task['id'])+':'+digest,'작업 #'+str(task['id'])+' · '+task['title']+'\n상태: '+task['status']+'\n'+task['result'][:2800]+'\n\n/result '+str(task['id'])+' 로 전체 결과와 파일을 받을 수 있어.')
            c.execute('INSERT OR REPLACE INTO telegram_results VALUES(?,?,?)',(cfg['generation'],task['id'],digest))
    for task in app.rows("SELECT id,title,due_date,due_time,reminder_minutes FROM tasks WHERE done=0 AND archived_at='' AND due_date<>'' AND status IN ('manual','scheduled','awaiting_approval')"):
        try:due=dt.datetime.fromisoformat(task['due_date']+'T'+(task['due_time'] or '09:00')).replace(tzinfo=app.schedule_features.ZONE)
        except ValueError:continue
        offsets=sorted(json.loads(task['reminder_minutes']))
        for minutes in offsets:
            if not task['due_time'] and minutes<1440:continue
            lag=(current-(due-dt.timedelta(minutes=minutes))).total_seconds()
            if not 0<=lag<(900 if minutes==0 else min(900,minutes*60)):continue
            key='reminder:'+str(task['id'])+':'+due.isoformat()+':'+str(minutes)
            enqueue(app,cfg,key,'일정 알림',{'reminder_task':task['id'],'reminder_offset':minutes,'reminder_due':due.isoformat(),'reminder_title':task['title'],'expires':(current+dt.timedelta(minutes=15)).timestamp()})
            break


def enqueue_image(app,cfg,key,job):
    try:path=app.image_studio.image_path(app,job['id'])
    except ValueError:return
    # Separate durable entries retain the original PNG alongside the preview.
    if path.stat().st_size<=10*1024*1024:
        enqueue(app,cfg,key+':preview','이미지 완성 · '+job['prompt'][:800],{'image_id':job['id'],'image_preview':True})
    enqueue(app,cfg,key+':original','원본 PNG · '+job['prompt'][:800],{'image_id':job['id'],'image_preview':False})


def send_image(app,payload):
    key=payload['image_id']
    jobs=app.rows("SELECT id FROM image_jobs WHERE id=? AND state='completed'",(key,))
    if not jobs:raise ValueError('완성된 이미지가 없습니다.')
    path=app.image_studio.image_path(app,key)
    if path.stat().st_size>40*1024*1024:raise ValueError('이미지 파일이 너무 큽니다.')
    field='photo' if payload.get('image_preview') else 'document'
    boundary='AIRI'+secrets.token_hex(16)
    parts=[]
    for name,value in [('chat_id',payload['chat_id']),('caption',payload.get('text','')[:900])]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="AIRI-{key}.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
    method='sendPhoto' if field=='photo' else 'sendDocument'
    req=urllib.request.Request('https://api.telegram.org/bot'+token(app)+'/'+method,data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=60) as r:result=json.load(r)
    except urllib.error.HTTPError as error:
        if error.code==400:raise ValueError('Telegram이 이미지 업로드를 거절했습니다. 원본 PNG 또는 웹 이미지 작업실에서 확인하세요.') from None
        raise TelegramError(error.code) from None
    except OSError:raise TelegramError() from None
    if not result.get('ok'):raise TelegramError(result.get('error_code',0))


def send_document(app,payload):
    if payload.get('analysis_report_id'):
        import report_service
        path=report_service.pdf_path(app,payload['analysis_report_id']);matches=[{'name':path.name}]
    else:
        task_id=payload['document_task'];key=payload['document_key']
        matches=[f for f in app.task_results.files(app,task_id) if f['key']==key]
        if not matches:raise ValueError('결과 파일이 없습니다.')
        path=app.DATA/'task-results'/str(task_id)/key
    if path.stat().st_size>20*1024*1024:raise ValueError('결과 파일이 20MB를 초과합니다.')
    boundary='AIRI'+secrets.token_hex(16)
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{payload["chat_id"]}\r\n--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{matches[0]["name"]}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
    req=urllib.request.Request('https://api.telegram.org/bot'+token(app)+'/sendDocument',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.urlopen(req,timeout=60) as r:result=json.load(r)
    except OSError:raise TelegramError() from None
    if not result.get('ok'):raise TelegramError(result.get('error_code',0))


def deliver(app,cfg):
    homecam_telegram.cleanup(app)
    with LOCK:
        current=config(app)
        if not current.get('enabled') or current.get('generation')!=cfg.get('generation') or current.get('chat_id')!=cfg.get('chat_id'):return
    rows=app.rows("SELECT * FROM telegram_outbox WHERE generation=? AND state='pending' AND next_try<=? ORDER BY created,key LIMIT 1",(cfg['generation'],time.time()))
    if not rows:return
    row=rows[0];payload=json.loads(row['payload'])
    if payload['chat_id']!=cfg.get('chat_id'):return
    cancelled=not current.get('notifications',True) and row['key'].startswith(('reminder:','result:'))
    if payload.get('camera_alert'):
        cancelled=cancelled or not homecam_telegram.camera_automation.service(app).active_home(current)
    if payload.get('reminder_task'):
        tasks=app.rows("SELECT * FROM tasks WHERE id=? AND done=0 AND archived_at='' AND status IN ('manual','scheduled','awaiting_approval')",(payload['reminder_task'],))
        task=tasks[0] if tasks else None
        due=dt.datetime.fromisoformat(payload['reminder_due'])
        cancelled=cancelled or not task or task['due_date']!=due.date().isoformat() or (task['due_time'] or '09:00')!=due.strftime('%H:%M') or payload['reminder_offset'] not in json.loads(task['reminder_minutes'])
        if task:payload['reminder_title']=task['title']
    if cancelled:
        with app.db() as c:c.execute("UPDATE telegram_outbox SET state='cancelled' WHERE generation=? AND key=?",(cfg['generation'],row['key']))
        return
    if payload.get('expires',time.time()+1)<time.time():
        with app.db() as c:c.execute("UPDATE telegram_outbox SET state='expired' WHERE generation=? AND key=?",(cfg['generation'],row['key']))
        return
    with app.db() as c:c.execute("UPDATE telegram_outbox SET state='sending' WHERE generation=? AND key=?",(cfg['generation'],row['key']))
    try:
        if 'homecam_clip' in payload:homecam_telegram.send_clip(app,payload,sys.modules[__name__])
        elif 'video_job_id' in payload:video_telegram.send_video(app,payload,sys.modules[__name__])
        elif 'image_id' in payload:send_image(app,payload)
        elif 'document_key' in payload or 'analysis_report_id' in payload:send_document(app,payload)
        else:
            outgoing={k:v for k,v in payload.items() if k in ('chat_id','text','reply_markup','protect_content')}
            if payload.get('reminder_due'):
                remaining=math.ceil((dt.datetime.fromisoformat(payload['reminder_due'])-dt.datetime.now(dt.timezone.utc)).total_seconds()/60)
                outgoing['text']='User, '+payload['reminder_title']+('까지 '+app.schedule_features.duration_label(remaining)+' 남았어.' if remaining>0 else ' 예정 시각이 됐거나 지났어.')
            request(app,'sendMessage',outgoing)
        with app.db() as c:c.execute("UPDATE telegram_outbox SET state='sent' WHERE generation=? AND key=?",(cfg['generation'],row['key']))
    except Exception as error:
        attempts=row['attempts']+1
        delay=max(min(300,5*2**min(attempts,6)),getattr(error,'retry_after',0))
        with app.db() as c:c.execute("UPDATE telegram_outbox SET state=?,attempts=?,next_try=? WHERE generation=? AND key=?",('failed' if isinstance(error,ValueError) else 'pending',attempts,time.time()+delay,cfg['generation'],row['key']))


def start(app):
    def polling():
        global STATUS
        while True:
            try:
                with LOCK:cfg=config(app);secret=token(app)
                if not cfg.get('enabled'):STATUS='연결 꺼짐' if token(app) else '봇 연결 전';time.sleep(5);continue
                updates=request(app,'getUpdates',{'offset':cfg.get('offset',0),'timeout':25,'allowed_updates':['message','callback_query']},secret=secret)
                STATUS='연결됨 · 메시지 대기' if cfg.get('user_id') else '봇 연결됨 · 본인 계정 연결 대기'
                if config(app).get('generation')!=cfg.get('generation'):continue
                for update in updates:receive(app,update)
            except Exception as error:
                STATUS=str(error) if isinstance(error,TelegramError) else '연결 재시도 대기'
                time.sleep(30)
    def outbound():
        while True:
            try:
                cfg=config(app)
                if cfg.get('enabled') and cfg.get('user_id'):
                    notifications(app,cfg)
                    telegram_news.run_due(app,cfg)
                    with LOCK:deliver(app,cfg)
            except Exception:pass
            time.sleep(2)
    threading.Thread(target=polling,name='airi-telegram-poll',daemon=True).start()
    threading.Thread(target=outbound,name='airi-telegram-send',daemon=True).start()
