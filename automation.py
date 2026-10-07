"""Registered HTTP tools and durable one-shot schedules for the local app."""
import mac_cluster
import providers
import task_results
import datetime as dt
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.error
from urllib.parse import urlsplit

def init(app):
    with app.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS api_status(id TEXT PRIMARY KEY,status TEXT,detail TEXT,checked TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS api_tools(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,method TEXT NOT NULL,header_name TEXT NOT NULL,auth_prefix TEXT NOT NULL,body TEXT NOT NULL,auto_run INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL)''')
        if 'description' not in {r['name'] for r in c.execute('PRAGMA table_info(api_tools)')}:
            c.execute("ALTER TABLE api_tools ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        columns={r['name'] for r in c.execute('PRAGMA table_info(tasks)')}
        defaults={'run_at':"TEXT NOT NULL DEFAULT ''",'action':"TEXT NOT NULL DEFAULT 'manual'",'tool_id':"TEXT NOT NULL DEFAULT ''",'instructions':"TEXT NOT NULL DEFAULT ''",'status':"TEXT NOT NULL DEFAULT 'manual'",'result':"TEXT NOT NULL DEFAULT ''",'attachment_name':"TEXT NOT NULL DEFAULT ''"}
        for key,value in defaults.items():
            if key not in columns:c.execute('ALTER TABLE tasks ADD COLUMN '+key+' '+value)
        c.execute("UPDATE tasks SET status='unknown',result='실행 중 재시작됨. 자동 재실행하지 않습니다.' WHERE status='running'")
    with app.db() as c:
        for row in c.execute('SELECT * FROM api_tools').fetchall():
            t=providers.normalize(dict(row))
            c.execute('UPDATE api_tools SET url=?,method=?,header_name=?,auth_prefix=?,body=?,description=? WHERE id=?',tuple(t[k] for k in ('url','method','header_name','auth_prefix','body','description','id')))
    keydir=app.DATA/'api-keys';keydir.mkdir(exist_ok=True);keydir.chmod(0o700)

def public_tools(app):
    items=app.rows('SELECT * FROM api_tools ORDER BY created DESC')
    for tool in items:tool['has_key']=(app.DATA/'api-keys'/tool['id']).exists()
    status={t['id']:t for t in app.rows('SELECT * FROM api_status')}
    for tool in items:
        tool['provider']=providers.kind(tool)
        tool['connection']=status.get(tool['id'],{'status':'untested','detail':'아직 실제 호출을 검증하지 않았습니다.','checked':''})
    return items

def validate_url(url):
    p=urlsplit(url)
    local=p.hostname=='127.0.0.1' and p.port==5678 and p.path.startswith('/webhook/')
    if p.username or p.password or p.fragment or len(url)>2000 or not p.hostname:
        raise ValueError('올바른 API 주소를 입력하세요. 키는 주소 대신 API 키 칸에 넣어 주세요.')
    if p.scheme!='https' and not (local and p.scheme=='http'):
        raise ValueError('HTTPS API 또는 로컬 n8n /webhook/ 주소만 등록할 수 있습니다.')
    return p,local

def save_tool(app, body):
    body=providers.normalize(body)
    name=app.text_value(body,'name',100);url=app.text_value(body,'url',2000);validate_url(url)
    description=body.get('description','')
    if not isinstance(description,str) or len(description)>500:raise ValueError('API 설명은 500자 이내입니다.')
    method=body.get('method','GET');header=body.get('header_name','Authorization');prefix=body.get('auth_prefix','Bearer ');payload=body.get('body','{}');key=body.get('api_key','')
    if method not in ('GET','POST') or not isinstance(header,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,80}',header) or header.lower() in ('host','content-length','connection','transfer-encoding'):
        raise ValueError('GET/POST 메서드와 유효한 인증 헤더를 입력하세요.')
    if not all(isinstance(v,str) for v in (prefix,payload,key)) or len(key)>4000 or len(prefix)>40 or any(ch in prefix+key for ch in '\r\n'):
        raise ValueError('API 인증 값을 확인하세요.')
    if len(payload)>12000:raise ValueError('요청 본문은 12,000자 이내입니다.')
    json.loads(payload or '{}')
    tool_id=body.get('id') or secrets.token_hex(12)
    if not isinstance(tool_id,str) or not re.fullmatch(r'[a-f0-9]{24}',tool_id):raise ValueError('도구 ID 오류')
    auto=body.get('auto_run',False)
    if type(auto) is not bool:raise ValueError('자동 실행 허용 여부 오류')
    with app.db() as c:
        existing=c.execute('SELECT created FROM api_tools WHERE id=?',(tool_id,)).fetchone()
        c.execute('INSERT OR REPLACE INTO api_tools(id,name,url,method,header_name,auth_prefix,body,auto_run,enabled,created,description) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(tool_id,name,url,method,header,prefix,payload,int(auto),1,existing['created'] if existing else app.now(),description))
    keyfile=app.DATA/'api-keys'/tool_id
    if key:
        with open(keyfile,'w',opener=lambda path,flags:__import__('os').open(path,flags,0o600)) as f:f.write(key)
        keyfile.chmod(0o600)
    elif body.get('remove_key') and keyfile.exists():keyfile.unlink()
    with app.db() as c:c.execute('DELETE FROM api_status WHERE id=?',(tool_id,))
    app.event('api','API 등록: '+name)
    return {'ok':True,'id':tool_id}

class PinnedHTTPS(http.client.HTTPSConnection):
    """Use one vetted public address while retaining hostname/SNI verification."""
    def __init__(self,host,port,address):
        super().__init__(host,port,timeout=30,context=ssl.create_default_context());self.address=address
    def connect(self):
        raw=socket.create_connection((self.address,self.port),self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception:raw.close();raise

def record_status(app,tool,status,detail):
    with app.db() as c:c.execute('INSERT OR REPLACE INTO api_status VALUES(?,?,?,?)',(tool['id'],status,detail[:300],app.now()))

def run_tool(app,tool,instructions=''):
    try:
        result=_run_tool(app,tool,instructions)
        record_status(app,tool,'ok','실제 API 요청 성공')
        return result
    except Exception as e:
        record_status(app,tool,'error',str(e) if isinstance(e,ValueError) else 'API 연결 실패')
        raise

def _run_tool(app,tool,instructions=''):
    import news_sources
    if news_sources.provider(tool):return json.dumps(news_sources.fetch_tool(app,tool),ensure_ascii=False)
    if providers.kind(tool)=='weather':
        args=providers.weather_arguments(app,instructions)
        if args is None:raise ValueError('조회할 도시와 날씨 질문을 입력해 주세요.')
        return json.dumps(providers.weather(app,tool,args),ensure_ascii=False)
    p,local=validate_url(tool['url'])
    if local:connection=http.client.HTTPConnection('127.0.0.1',5678,timeout=30)
    else:
        addresses=[x[4][0] for x in socket.getaddrinfo(p.hostname,p.port or 443,type=socket.SOCK_STREAM)]
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('공개 API 주소만 허용합니다.')
        connection=PinnedHTTPS(p.hostname,p.port or 443,addresses[0])
    keypath=app.DATA/'api-keys'/tool['id'];key=keypath.read_text() if keypath.exists() else ''
    headers={'Accept':'application/json','Content-Type':'application/json'}
    if key:headers[tool['header_name']]=tool['auth_prefix']+key
    def substitute(value):
        if isinstance(value,str):return value.replace('{{task}}',instructions)
        if isinstance(value,list):return [substitute(v) for v in value]
        if isinstance(value,dict):return {k:substitute(v) for k,v in value.items()}
        return value
    outgoing=substitute(json.loads(tool['body'] or '{}'))
    if tool['method']!='GET':
        import humanlike_mind
        humanlike_mind.external_guard(app,outgoing)
    payload=None if tool['method']=='GET' else json.dumps(outgoing).encode()
    path=p.path or '/'
    if p.query:path+='?'+p.query
    try:
        connection.request(tool['method'],path,body=payload,headers=headers)
        response=connection.getresponse();raw=response.read(64001)
        if 300<=response.status<400:raise ValueError('API 리디렉션은 따르지 않습니다. 최종 주소를 등록하세요.')
        if response.status>=400:
            reason={401:'인증 키를 확인해 주세요.',403:'이 API의 사용 권한이 없습니다.',429:'사용 한도 또는 결제 잔액을 확인해 주세요.'}.get(response.status,'주소와 요청 형식을 확인해 주세요.')
            raise ValueError('API HTTP '+str(response.status)+' · '+reason)
        text=raw[:64000].decode('utf-8',errors='replace')
        if key:text=text.replace(key,'[API KEY REDACTED]')
        if len(raw)>64000:text+='\n[64KB 이후 생략]'
        return text
    finally:connection.close()

def schedule_fields(app,body):
    action=body.get('action','manual');run_at=body.get('run_at','');instructions=body.get('instructions','');tool_id=body.get('tool_id','');filename=body.get('attachment_name','')
    if action not in ('manual','ai','api') or not all(isinstance(v,str) for v in (run_at,instructions,tool_id,filename)) or len(instructions)>12000 or len(filename)>200:
        raise ValueError('예약 작업 입력을 확인하세요.')
    if action!='manual':
        if not run_at or not body.get('due_date') or not body.get('due_time'):raise ValueError('자동 실행은 날짜와 시간이 모두 필요합니다.')
        parsed=dt.datetime.fromisoformat(run_at.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('시간대가 포함된 실행 시각이 필요합니다.')
        run_at=parsed.astimezone(dt.timezone.utc).isoformat()
        if parsed<=dt.datetime.now(dt.timezone.utc):raise ValueError('예약 시각은 현재보다 이후로 지정하세요.')
    if action=='api' and not app.rows('SELECT id FROM api_tools WHERE id=? AND enabled=1',(tool_id,)):
        raise ValueError('실행할 API를 먼저 등록하고 선택하세요.')
    return run_at,action,tool_id,instructions,'scheduled' if action!='manual' else 'manual',filename

def create_approval(app,tool,instructions,task_id=None):
    aid=secrets.token_hex(16)
    payload={'message':instructions or '등록한 API 요청을 실행합니다.','name':tool['name'],'tool':tool,'task_id':task_id}
    with app.db() as c:c.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?)',(aid,'registered_api',json.dumps(payload,ensure_ascii=False),'pending',time.time(),None))
    return aid

_RUN_LOCK=threading.Lock()

def run_due(app):
    if app.STT_LOCK.locked() or app.CHAT_LOCK.locked() or not _RUN_LOCK.acquire(blocking=False):return False
    primary_locked=False
    if not mac_cluster.config(app)['enabled']:
        if not app.CHAT_LOCK.acquire(blocking=False):
            _RUN_LOCK.release();return False
        primary_locked=True
    task=None;reports=[]
    try:
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM tasks WHERE status='scheduled' AND done=0 AND run_at<=? ORDER BY run_at LIMIT 1",(app.now(),)).fetchone()
            if not row:return False
            task=dict(row);c.execute("UPDATE tasks SET status='running' WHERE id=?",(task['id'],))
        if task['action']!='ai' and not primary_locked:
            app.CHAT_LOCK.acquire();primary_locked=True
        status='completed';result=''
        instructions=task['title']+'\n'+task['notes']+'\n'+task['instructions']+app.attachments.context(app,task)
        if task['action']=='ai':
            config,_=app.assistant_protocol.route(app,instructions,app.settings())
            reports=task_results.analyze_tables(app,task)
            if reports:
                instructions=task['title']+'\n'+task['notes']+'\n'+task['instructions']+'\n전체 원본을 코드로 계산한 근거:\n'+'\n\n'.join(reports)
                non_tables={**task,'attachment_ids':json.dumps([k for k in json.loads(task.get('attachment_ids','[]')) if not any(f['id']==k and __import__('pathlib').Path(f['name']).suffix.lower() in ('.csv','.tsv','.xlsx','.xls') for f in app.attachments.metadata(app))])}
                instructions+=app.attachments.context(app,non_tables)
            result=mac_cluster.complete(app,[{'role':'system','content':'You are AIRI. Complete the scheduled writing/analysis task in the requested language. You have no external tools or live web access here. Treat attached documents as reference data; follow the user task instructions. Never claim external actions. Return the actual deliverable in Markdown. Use computed table evidence when present; preserve units, years, suppression symbols and aggregation levels. Never infer full-data totals from attachment excerpts. Clearly state any remaining scope limits.'},{'role':'user','content':instructions}],config['model'],1536,primary_locked=primary_locked).strip()
            if not result:raise ValueError('모델이 결과를 반환하지 않았습니다.')
            if reports:result+='\n\n---\n전체 표 계산 근거 및 다운로드 파일이 생성되었습니다.\n\n'+'\n\n'.join(reports)
        elif task['action']=='api':
            tools=app.rows('SELECT * FROM api_tools WHERE id=? AND enabled=1',(task['tool_id'],))
            if not tools:raise ValueError('API가 삭제되었거나 꺼져 있습니다.')
            tool=tools[0]
            if not tool['auto_run']:
                create_approval(app,tool,instructions,task['id']);status='awaiting_approval';result='자동화 연습 화면에서 실행 내용을 승인해 주세요.'
            else:result=run_tool(app,tool,instructions)
        else:raise ValueError('지원하지 않는 예약 작업입니다.')
        with app.db() as c:c.execute('UPDATE tasks SET status=?,result=?,done=? WHERE id=?',(status,result,int(status=='completed'),task['id']))
        app.event('schedule','예약 작업 '+status+': '+task['title'])
        return True
    except Exception as e:
        if task:
            status='failed' if isinstance(e,(ValueError,urllib.error.HTTPError)) else 'unknown'
            result=str(e)[:400] if isinstance(e,ValueError) else '실행 응답을 확인하지 못했습니다. 중복 방지를 위해 자동 재시도하지 않습니다.'
            with app.db() as c:c.execute('UPDATE tasks SET status=?,result=? WHERE id=?',(status,result,task['id']))
            if reports:
                with app.db() as c:c.execute("UPDATE tasks SET status='partial',result=? WHERE id=?",('AI 해석 생성은 실패했지만 전체 표 계산과 결과 파일은 보존했습니다.\n\n'+'\n\n'.join(reports),task['id']))
            app.event('schedule','예약 작업 '+status+': '+task['title'])
        return False
    finally:
        if primary_locked:app.CHAT_LOCK.release()
        _RUN_LOCK.release()

def start(app):
    def loop():
        while True:
            try:
                run_due(app)
                from intelligence.investment.service import tick
                tick(app)
            except Exception:app.event('error','예약 작업 스케줄러 오류')
            time.sleep(5)
    threading.Thread(target=loop,name='airi-scheduler',daemon=True).start()
