"""Durable, private image generation/edit jobs using registered OpenAI credentials."""
import base64,json,re,secrets,subprocess,threading,time,urllib.request,urllib.error
from pathlib import Path

MODELS=('gpt-image-2.5-flare','gpt-image-2.5-sunburst','gpt-image-1.5','gpt-image-1')
SIZES=('1024x1024','1536x1024','1024x1536')
MAX_PROMPT=12000
def init(app):
    folder=app.DATA/'images';folder.mkdir(exist_ok=True);folder.chmod(0o700)
    with app.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS image_inputs(id TEXT PRIMARY KEY,name TEXT,created TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS image_jobs(id TEXT PRIMARY KEY,task_id INTEGER,prompt TEXT,model TEXT,size TEXT,quality TEXT,inputs TEXT,tool_id TEXT,state TEXT,result TEXT,created TEXT)')
        c.execute("UPDATE image_jobs SET state='unknown',result='서버가 재시작되어 생성 결과를 확인하지 못했습니다. 자동 재요청하지 않았습니다.' WHERE state='running'")

def metadata(app):
    return {'models':list(MODELS),'sizes':list(SIZES),'has_key':bool(app.llm_client.registered_openai('openai:auto')),
            'jobs':app.rows('SELECT id,task_id,prompt,model,size,quality,inputs,state,result,created FROM image_jobs ORDER BY created DESC LIMIT 30')}

def image_path(app,key):
    if not re.fullmatch(r'[a-f0-9]{32}',key):raise ValueError('이미지 ID를 확인하세요.')
    path=app.DATA/'images'/(key+'.png')
    if not path.is_file():raise ValueError('이미지 파일이 없습니다.')
    return path

def upload(app,handler):
    try:length=int(handler.headers.get('Content-Length','0'))
    except ValueError:return handler.send_json({'error':'파일 크기를 확인하세요.'},400)
    if not 0<length<=20*1024**2:return handler.send_json({'error':'이미지는 20MB 이하로 첨부하세요.'},400)
    key=secrets.token_hex(16);raw=app.DATA/'images'/(key+'.upload');target=raw.with_suffix('.png')
    try:
        data=handler.rfile.read(length)
        if len(data)!=length:raise ValueError('파일 전송이 완료되지 않았습니다.')
        raw.write_bytes(data);raw.chmod(0o600)
        done=subprocess.run([str(app.ROOT/'.venv/bin/python'),str(app.ROOT/'scripts/validate-image.py'),str(raw),str(target)],capture_output=True,timeout=30)
        if done.returncode:raise ValueError('PNG·JPEG·WebP 이미지(최대 1600만 화소)를 첨부하세요. 손상된 파일은 사용할 수 없습니다.')
        target.chmod(0o600)
        with app.db() as c:c.execute('INSERT INTO image_inputs VALUES(?,?,?)',(key,'reference.png',app.now()))
        return handler.send_json({'id':key})
    except (ValueError,subprocess.TimeoutExpired) as error:
        target.unlink(missing_ok=True)
        return handler.send_json({'error':str(error) if isinstance(error,ValueError) else '이미지 검사 시간이 초과되었습니다.'},400)
    finally:raw.unlink(missing_ok=True)

def submit(app,body):
    prompt=app.text_value(body,'prompt',MAX_PROMPT);model=body.get('model',MODELS[0]);size=body.get('size',SIZES[0]);quality=body.get('quality','medium');inputs=body.get('inputs',[])
    if model not in MODELS or size not in SIZES or quality not in ('low','medium','high'):raise ValueError('모델·크기·품질을 확인하세요.')
    if not isinstance(inputs,list) or len(inputs)>4 or any(not isinstance(i,str) for i in inputs) or len(set(inputs))!=len(inputs):raise ValueError('참고 이미지는 서로 다른 파일 최대 4장까지 가능합니다.')
    for key in inputs:image_path(app,key)
    endpoint=app.llm_client.registered_openai('openai:auto')
    if not endpoint:raise ValueError('설치·연결에 OpenAI API 키를 먼저 등록하세요.')
    key=body.get('request_id') or secrets.token_hex(16)
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('요청 ID를 확인하세요.')
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM image_jobs WHERE id=?',(key,)).fetchone()
        if old:
            if (old['prompt'],old['model'],old['size'],old['quality'],json.loads(old['inputs']))!=(prompt,model,size,quality,inputs):raise ValueError('같은 요청 ID로 다른 이미지를 생성할 수 없습니다.')
            return {'id':key,'task_id':old['task_id'],'state':old['state']}
        if c.execute("SELECT count(*) FROM image_jobs WHERE state IN ('queued','running')").fetchone()[0]>=3:raise ValueError('이미지 요청 3개가 처리 중입니다. 완료 후 다시 요청하세요.')
        cur=c.execute("INSERT INTO tasks(title,created,action,status,instructions) VALUES(?,?,'image','queued',?)",('이미지 '+('편집' if inputs else '생성')+' · '+prompt[:65],app.now(),prompt));task_id=cur.lastrowid
        c.execute('INSERT INTO image_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,task_id,prompt,model,size,quality,json.dumps(inputs),endpoint['tool_id'],'queued','',app.now()))
    return {'id':key,'task_id':task_id,'state':'queued'}

def multipart(fields,images):
    boundary='AIRI'+secrets.token_hex(16);parts=[]
    for name,value in fields.items():parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
    for index,data in enumerate(images):parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="reference-{index}.png"\r\nContent-Type: image/png\r\n\r\n').encode()+data+b'\r\n')
    parts.append(('--'+boundary+'--\r\n').encode());return b''.join(parts),'multipart/form-data; boundary='+boundary

def generate(app,job):
    endpoint=app.llm_client.registered_openai('openai:'+job['tool_id'])
    if not endpoint:raise ValueError('요청에 사용한 OpenAI API 키가 삭제되었거나 꺼졌습니다.')
    fields={'model':job['model'],'prompt':job['prompt'],'size':job['size'],'quality':job['quality'],'n':1,'output_format':'png'}
    inputs=json.loads(job['inputs'])
    if inputs:body,content_type=multipart(fields,[image_path(app,k).read_bytes() for k in inputs]);method='edits'
    else:body=json.dumps(fields).encode();content_type='application/json';method='generations'
    request=urllib.request.Request('https://api.openai.com/v1/images/'+method,data=body,headers={'Authorization':'Bearer '+endpoint['key'],'Content-Type':content_type})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=240) as response:
            raw=response.read(80*1024**2+1)
            if len(raw)>80*1024**2:raise ValueError('이미지 응답이 허용 크기를 초과했습니다.')
            result=json.loads(raw)
    except urllib.error.HTTPError as error:
        code='';detail=''
        try:
            error_body=json.loads(error.read(4000)).get('error',{})
            code=error_body.get('code','') or ''
            detail=error_body.get('message','') or ''
        except Exception:pass
        if code=='moderation_blocked':raise ValueError('이미지 서비스가 이 요청을 허용하지 않았습니다. 프롬프트나 참고 이미지를 수정하세요.') from None
        if error.code==401 and ('api.model.images.request' in detail or 'insufficient permissions' in detail.lower()):
            raise ValueError('OpenAI 키에 이미지 생성 권한이 없습니다. OpenAI 프로젝트에서 이미지 요청 권한(api.model.images.request)을 포함한 Writer·Member 이상 키를 등록하세요.') from None
        raise ValueError({401:'OpenAI API 키를 확인하세요.',403:'이 API 계정에 이미지 모델 사용 권한이 없습니다. 조직 인증과 모델 권한을 확인하세요.',404:'이 API 계정에서 선택한 이미지 모델을 사용할 수 없습니다. 다른 이미지 모델을 선택하세요.',429:'OpenAI API 사용 한도 또는 잔액을 확인하세요.'}.get(error.code,'이미지 생성 API 요청이 실패했습니다. HTTP '+str(error.code))) from None
    try:data=base64.b64decode(result['data'][0]['b64_json'],validate=True)
    except (KeyError,IndexError,ValueError):raise ValueError('API가 완성된 이미지를 반환하지 않았습니다.')
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>40*1024**2:raise ValueError('API 이미지 형식을 확인하지 못했습니다.')
    path=app.DATA/'images'/(job['id']+'.png');temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.chmod(0o600);temp.replace(path)
    return '이미지 '+('편집' if inputs else '생성')+' 완료. 이미지 작업실에서 확인하고 다운로드하세요.'

def run_one(app):
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE image_jobs SET state='failed',result='작업이 삭제 또는 취소되어 생성하지 않았습니다.' WHERE state='queued' AND task_id NOT IN (SELECT id FROM tasks WHERE status='queued' AND archived_at='')")
        row=c.execute("SELECT * FROM image_jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:return False
        job=dict(row);c.execute("UPDATE image_jobs SET state='running' WHERE id=?",(job['id'],));c.execute("UPDATE tasks SET status='running' WHERE id=?",(job['task_id'],))
    try:result=generate(app,job);state='completed'
    except ValueError as error:result=str(error);state='failed'
    except Exception:result='생성 응답을 확인하지 못했습니다. 중복 과금을 막기 위해 자동 재요청하지 않았습니다.';state='unknown'
    with app.db() as c:
        c.execute('UPDATE image_jobs SET state=?,result=? WHERE id=?',(state,result,job['id']))
        c.execute('UPDATE tasks SET status=?,result=?,done=? WHERE id=?',(state,result,int(state=='completed'),job['task_id']))
    app.event('image','이미지 작업 '+state+' · #'+str(job['task_id']));return True

def start(app):
    def loop():
        while True:
            try:run_one(app)
            except Exception:pass
            time.sleep(2)
    threading.Thread(target=loop,name='airi-images',daemon=True).start()

def chat_request(app,text):
    lead=re.split(r'[\n.!?。]',text,maxsplit=1)[0]
    # A negative visual constraint (e.g. "글자를 넣지 마") is not a request
    # to cancel generation. Method/translation questions are checked separately.
    if re.search(r'(?:생성|제작|수정)\s*(?:하지\s*(?:마|말|않)|(?:은|는)?\s*안\s*해)|만들지\s*(?:마|말)|(?:do not|don.t)\s+(?:generate|create|draw|make|edit)|ne\s+(?:génère|crée|dessine).{0,20}pas',text,re.I):return None
    if re.search(r'방법|어떻게|할\s*수|번역해|번역해줘|번역$|설명해|예시|how\s+(?:to|do|can)|\bcomment\b|\b(translate|explain|example)\b',lead,re.I):return None
    visual=re.search(r'이미지|사진|그림|포스터|일러스트|image|picture|photo|poster|illustration',text,re.I)
    imperative=re.search(r'만들어|생성\s*해|그려\s*줘|바꿔\s*줘|수정\s*해|\b(generate|create|draw|edit|make|dessine|génère|crée|transforme)\b',text,re.I)
    # Korean commands commonly omit 해줘: “사무실 사진 생성”, “그럼 강아지 사진 생성”.
    short_command=re.search(r'(?:생성|제작|만들기|그리기)(?:\s*(?:요청|부탁)(?:해요|해|드립니다)?)?[.!:：\t ]*$',text,re.M)
    if not (visual and (imperative or short_command)):return None
    if re.search(r'이\s*(?:사진|이미지)|첨부|this\s+(?:image|photo)|attached|cette\s+(?:image|photo)',text,re.I):return {'text':'이미지 작업실에서 참고 사진을 첨부하고 수정할 내용을 적어줘. 원본을 받은 뒤 편집할게.'}
    job=submit(app,{'prompt':text});return {**job,'text':'이미지 생성 작업 #'+str(job['task_id'])+'을 접수했어. 완성되면 이미지 작업실에서 볼 수 있어.'}
