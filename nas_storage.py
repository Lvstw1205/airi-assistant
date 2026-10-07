"""Bounded NAS document access; local database remains authoritative."""
from pathlib import Path
import collections, json, os, re, secrets, subprocess, time, threading
DEFAULT_ROOT=Path(__import__('os').environ.get('AIRI_NAS_ROOT','/Volumes/AIRI-Shared'))
ALLOWED={'.md','.markdown','.txt','.csv','.tsv','.xlsx','.xls','.pdf','.docx','.doc','.rtf','.pptx','.json'}
MAX_BYTES=20*1024*1024
def root(app):return DEFAULT_ROOT
_status_lock=threading.Lock()
_status_checks={}

def status(app):
    base=root(app)
    # macOS can hold scandir/access until the user answers the NAS privacy dialog.
    # Keep that wait out of HTTP handlers, with only one probe per mount in flight.
    if not str(base).startswith('/Volumes/'):
        return _status(app)
    key=str(base)
    with _status_lock:
        check=_status_checks.get(key)
        if check is None or (check['done'].is_set() and time.monotonic()-check['at']>5):
            check={'done':threading.Event(),'at':time.monotonic(),'result':None}
            _status_checks[key]=check
            def inspect():
                try:check['result']=_status(app)
                except OSError:pass
                finally:
                    check['at']=time.monotonic();check['done'].set()
            threading.Thread(target=inspect,daemon=True).start()
    check['done'].wait(.15)
    if check['result'] is not None:return dict(check['result'])
    return {'connected':False,'mounted':None,'readable':False,'writable':False,
            'write_verified':False,'checking':True,'root':key,'name':'Configured network share',
            'output':'AIRI-results','error':'NAS 접근 확인 중입니다. Mac의 네트워크 볼륨 접근 허용 창을 확인해 주세요.'}

def _status(app):
    base=root(app)
    mounted=base.is_dir()
    readable=mounted and os.access(base,os.R_OK|os.X_OK)
    if readable:
        try:
            with os.scandir(base) as entries:next(entries,None)
        except OSError:readable=False
    writable=readable and os.access(base,os.W_OK)
    error=None if readable else ('NAS는 마운트되어 있지만 AIRI 프로세스의 접근 권한 거부로 읽을 수 없습니다. macOS 개인정보 보호 및 보안에서 AIRI 실행 Python의 네트워크 볼륨 접근을 확인하세요.' if mounted else 'Finder에서 AIRI-Shared를 연결해 주세요.')
    return {'connected':bool(readable),'mounted':mounted,'readable':bool(readable),'writable':bool(writable),'write_verified':False,'root':str(base),'name':'Configured network share','output':'AIRI-results','error':error}
def safe_path(app,name=''):
    base=root(app)
    if not base.is_dir():raise ValueError('NAS가 오프라인입니다. Finder에서 AIRI-Shared를 연결해 주세요.')
    if not isinstance(name,str) or len(name)>1024:raise ValueError('파일 경로를 확인해 주세요.')
    rel=Path(name)
    if rel.is_absolute():
        try:rel=rel.relative_to(base)
        except ValueError:raise ValueError('공유폴더 밖의 경로입니다.')
    if any(p=='..' or p.startswith('.') for p in rel.parts):raise ValueError('숨김 파일과 상위 경로는 접근할 수 없습니다.')
    target=base
    for part in rel.parts:
        target=target/part
        if target.is_symlink():raise ValueError('NAS 심볼릭 링크는 접근할 수 없습니다.')
    if target.resolve()!=base.resolve() and base.resolve() not in target.resolve().parents:raise ValueError('공유폴더 밖의 경로입니다.')
    return target
def listing(app,limit=100,query=''):
    connection=status(app)
    if not connection['mounted']:return []
    if not connection['readable']:raise ValueError(connection['error'])
    queue=collections.deque([(root(app),0)]);out=[];visited=0;deadline=time.monotonic()+2
    while queue and visited<2000 and time.monotonic()<deadline and len(out)<limit:
        folder,depth=queue.popleft()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    visited+=1
                    if visited>2000 or time.monotonic()>deadline:break
                    if entry.name.startswith('.') or entry.is_symlink():continue
                    if entry.is_dir(follow_symlinks=False) and depth<3:queue.append((Path(entry.path),depth+1));continue
                    if not entry.is_file(follow_symlinks=False):continue
                    rel=str(Path(entry.path).relative_to(root(app)))
                    if query.casefold() not in rel.casefold():continue
                    out.append({'name':rel,'size':entry.stat(follow_symlinks=False).st_size,'supported':Path(entry.name).suffix.lower() in ALLOWED})
                    if len(out)>=limit:break
        except OSError as error:
            raise ValueError('NAS 폴더를 읽지 못했습니다: '+str(folder.relative_to(root(app)))+' · '+('접근 권한 거부' if error.errno in (1,13) else 'NAS 응답 오류')+'. macOS 네트워크 볼륨 접근 권한과 NAS 공유 권한을 확인하세요.') from error
    return out

def probe(app):
    """Verify through the actual server process, using only our disposable file."""
    result=status(app)
    result['write_verified']=False
    if not result['connected']:return result
    try:
        with os.scandir(root(app)) as entries:
            next(entries,None)
        folder=safe_path(app,'AIRI-results');folder.mkdir(exist_ok=True)
        target=safe_path(app,'AIRI-results/airi-connection-check-'+secrets.token_hex(12)+'.txt')
        created=False
        try:
            with target.open('x',encoding='utf8') as out:
                created=True;out.write('AIRI read/write connection check')
            if target.read_text()!='AIRI read/write connection check':raise ValueError('NAS 저장 내용 검증 실패')
            result.update(writable=True,write_verified=True,error=None)
        finally:
            if created:target.unlink()
    except OSError as error:
        result.update(writable=False,error='AIRI 프로세스에서 NAS 읽기·쓰기를 완료하지 못했습니다 · '+('접근 권한 거부' if error.errno in (1,13) else str(error)))
    return result
def extract(app,name):
    path=safe_path(app,name)
    if not path.is_file():raise ValueError('NAS 파일이 없습니다.')
    if path.suffix.lower() not in ALLOWED:raise ValueError('지원하지 않는 문서 형식입니다.')
    if path.stat().st_size>MAX_BYTES:raise ValueError('20MB 이하 파일만 읽을 수 있습니다.')
    cache=app.DATA/'nas-cache';cache.mkdir(mode=0o700,exist_ok=True)
    local=cache/(secrets.token_hex(16)+path.suffix.lower())
    try:
        with path.open('rb') as f:raw=f.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('20MB 이하 파일만 읽을 수 있습니다.')
        local.write_bytes(raw);local.chmod(0o600)
        result=subprocess.run([str(app.ROOT/'.venv/bin/python'),str(app.ROOT/'scripts/extract-file.py'),str(local)],capture_output=True,text=True,timeout=45)
        try:data=json.loads(result.stdout)
        except ValueError:raise ValueError('문서 추출 환경을 확인해 주세요.')
        if result.returncode or data.get('error'):raise ValueError(data.get('error','문서 추출 실패'))
        app.event('nas_read','NAS 자료 읽기: '+name)
        return data,raw
    finally:local.unlink(missing_ok=True)
def read_text(app,name,limit=14000):
    data,_=extract(app,name)
    return data['text'][:limit]
def import_file(app,name):
    data,raw=extract(app,name);key=secrets.token_hex(16);filename=Path(name).name
    dest=app.DATA/'attachments'/(key+Path(name).suffix.lower());dest.write_bytes(raw);dest.chmod(0o600)
    with app.db() as c:c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?)',(key,filename,len(raw),data['text'],int(data['truncated']),app.now()))
    return {'id':key,'name':filename,'size':len(raw)}
def export_text(app,text,name='result'):
    if not isinstance(text,str) or not text.strip() or len(text)>500000:raise ValueError('저장할 결과가 없거나 너무 큽니다.')
    folder=safe_path(app,'AIRI-results')
    try:
        # SMB shares can reject POSIX mode bits even when the user has write
        # access. Let the NAS ACL decide permissions instead of forcing 0700.
        folder.mkdir(parents=True,exist_ok=True)
    except OSError as error:
        raise ValueError('NAS 공유폴더에 쓸 수 없습니다. Finder에서 AIRI-Shared의 쓰기 권한과 여유 공간을 확인해 주세요.') from error
    stem=re.sub(r'[^\w가-힣 -]','',name)[:60].strip() or 'result'
    target=safe_path(app,'AIRI-results/'+stem+'-'+secrets.token_hex(6)+'.md')
    try:
        with target.open('x',encoding='utf-8') as f:f.write(text)
    except OSError as error:
        raise ValueError('NAS 공유폴더에 파일을 만들 수 없습니다. Finder에서 쓰기 권한을 확인해 주세요.') from error
    app.event('nas_write','NAS 저장 완료: '+target.name)
    return {'saved':True,'path':str(target),'name':target.name}
def snapshot(app):
    data={'created':app.now(),'memories':app.rows('SELECT content,created FROM memories'),
          'skills':app.rows('SELECT name,content,enabled FROM skills'),
          'tasks':app.rows('SELECT id,title,due_date,due_time,status,result FROM tasks')}
    return export_text(app,'# AIRI 사용자 자료 스냅샷\n\n'+json.dumps(data,ensure_ascii=False,indent=2),'airi-snapshot')
def command_response(app,text):
    if not re.search(r'(?<![a-z])nas(?![a-z])',text,re.I):return None
    if re.search(r'하지\s*마|하지\s*말|do not|don.t|설명|방법|how to',text,re.I):return None
    try:
        connection=status(app)
        if not connection['connected']:return {'text':connection['error']}
        if re.search(r'저장|save|export',text,re.I):
            match=re.search(r'(?:작업|task|#)\s*(\d+)',text,re.I)
            records=app.rows('SELECT result AS content FROM tasks WHERE id=?',(int(match[1]),)) if match else app.rows("SELECT content FROM messages WHERE role='assistant' AND session='main' ORDER BY id DESC LIMIT 1")
            if not records or not records[0]['content']:return {'text':'저장할 결과가 아직 없어요. 작업 번호를 지정하거나 답변을 받은 뒤 NAS에 저장해 달라고 해주세요.'}
            saved=export_text(app,records[0]['content'],'task-'+match[1] if match else 'conversation')
            return {'text':'NAS에 저장했어요: '+saved['path']}
        if re.search(r'목록|리스트|list|파일 뭐|자료 보여',text,re.I):
            files=listing(app,30)
            return {'text':'NAS 파일 목록 (최대 30개·하위 3단계):\n'+('\n'.join('• '+f['name'] for f in files) or '찾은 파일이 없습니다.')}
        if re.search(r'상태|연결|경로|status',text,re.I):return {'text':'NAS 연결됨 · '+str(root(app))+(' · 읽기·쓰기 권한 있음' if connection['writable'] else ' · 읽기 가능, 쓰기 권한 확인 필요')}
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:return {'text':'NAS 작업을 완료하지 못했어요: '+str(e)}
    return None
