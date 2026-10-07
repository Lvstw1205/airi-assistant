"""Explicit Muse delegation from AIRI chat/Telegram, with durable result delivery."""
import re, threading, time
from muse_mailbox import Mailbox

def availability(box=None):
    box=box or Mailbox()
    last=box.status()['last_poll']
    ready=last is not None and 0 <= time.time()-last <= 900
    return {'available':ready,'last_poll':last,'default_backend':'M6 Ollama',
            'reason':'Muse worker recently polled' if ready else 'Muse worker has not authenticated and polled recently'}

def needs_external_browser(text):
    # Capability gap, not model complexity: ordinary research already has local tools.
    return bool(re.search(r'브라우저|browser',text,re.I) and re.search(r'탐색|열어서|페이지.*비교|navigate|browse|interact|click through',text,re.I))

def delegate(app,text,request_key=None,source='chat',generation='',explicit=False,box=None):
    box=box or Mailbox()
    if not explicit and not needs_external_browser(text):
        return {'state':'local','text':'이 작업은 AIRI의 M6 Ollama와 기존 도구로 처리하세요.'}
    if not availability(box)['available']:
        return {'state':'unavailable','text':'Muse 연결이 아직 검증되지 않아 이 작업을 전달하지 못했어요. AIRI의 M6 로컬 모델과 기존 도구는 계속 사용할 수 있어요.'}
    j=box.submit(text,request_key,source,generation)
    return {'state':'queued','id':j['id'],'text':'티모에게 전달할 요청을 등록했어요. 아직 완료된 것은 아니에요.\n작업 ID: '+j['id']+'\n완료되면 AIRI에서 결과를 전할게요.'}

def chat_request(app,text,request_key=None,source='chat',generation=''):
    match=re.match(r'^\s*(?:/muse\b|(?:뮤즈|티모)(?:에게|한테)\s*|(?:muse|timo)[:,]\s*)(.*)$',text,re.I|re.S)
    if not match:
        if needs_external_browser(text):
            return delegate(app,text,request_key,source,generation)
        return None
    prompt=match[1].strip();box=Mailbox()
    try:
        if not prompt:
            reply='/muse 작업 지시: Muse에 맡기기\n/muse status: 진행 확인\n/muse result 작업ID: 결과\n/muse cancel 작업ID: 취소\nMuse 연결은 무료 계정 사용 한도의 영향을 받아요.'
        elif prompt in ('status','상태'):
            s=box.status();last=s['last_poll']
            reply=('Muse 마지막 확인: '+str(int(time.time()-last))+'초 전' if last else 'Muse 작업함을 확인한 기록이 아직 없어요.')+'\n'+'\n'.join(j['id']+' · '+j['state']+' · '+j['prompt'][:70] for j in s['jobs'])
        elif re.match(r'^(result|결과|cancel|취소)\s+',prompt):
            action,key=prompt.split(None,1)
            j=box.cancel(key.strip()) if action in ('cancel','취소') else box.status(key.strip())
            reply=j['id']+' · '+j['state']+'\n'+(j['result'] or '아직 결과가 없어요.')
        else:
            return delegate(app,prompt,request_key,source,generation,explicit=True,box=box)
    except ValueError as e:reply=str(e)
    return {'text':reply}

def deliver(app,box=None):
    box=box or Mailbox()
    with app.db() as c:c.execute('CREATE TABLE IF NOT EXISTS muse_deliveries(id TEXT PRIMARY KEY)')
    for j in box.notifications():
        message='Muse 작업 '+j['id']+' · '+j['state']+'\n'+j['result']
        if j['source']=='telegram':
            import telegram_bridge as tg
            cfg=tg.config(app)
            if not cfg.get('enabled') or cfg.get('generation')!=j['generation']:continue
            for index in range(0,len(message),2800):tg.enqueue(app,cfg,'muse:'+j['id']+':'+str(index),message[index:index+2800])
        else:
            with app.db() as c:
                added=c.execute('INSERT OR IGNORE INTO muse_deliveries VALUES(?)',(j['id'],)).rowcount
                if added:c.execute("INSERT INTO messages(session,role,content,created) VALUES('main','assistant',?,?)",(message,app.now()))
        box.notified(j['id'])

def start(app):
    def loop():
        while True:
            try:deliver(app)
            except Exception:pass
            time.sleep(5)
    threading.Thread(target=loop,name='airi-muse-results',daemon=True).start()
