"""Local task attachments, retained originals and bounded text context."""
import json,re,secrets,subprocess
from pathlib import Path
from urllib.parse import unquote

EXTENSIONS={'.md','.markdown','.txt','.csv','.tsv','.xlsx','.xls','.pdf','.docx','.doc','.rtf','.pptx','.json'}

def init(app):
    folder=app.DATA/'attachments';folder.mkdir(exist_ok=True);folder.chmod(0o700)
    with app.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,name TEXT NOT NULL,size INTEGER NOT NULL,text TEXT NOT NULL,truncated INTEGER NOT NULL,created TEXT NOT NULL)')
        if 'attachment_ids' not in {r['name'] for r in c.execute('PRAGMA table_info(tasks)')}:
            c.execute("ALTER TABLE tasks ADD COLUMN attachment_ids TEXT NOT NULL DEFAULT '[]'")

def upload(app,handler):
    path=None
    try:
        length=int(handler.headers.get('Content-Length','0'))
        if not 0<length<=20*1024*1024:raise ValueError('파일당 최대 20MB까지 첨부할 수 있습니다.')
        name=unquote(handler.headers.get('X-AIRI-Filename',''))
        if not name or len(name)>200 or '/' in name or '\\' in name or any(ord(ch)<32 for ch in name):raise ValueError('파일 이름을 확인해 주세요.')
        ext=Path(name).suffix.lower()
        if ext not in EXTENSIONS:raise ValueError('MD, TXT, CSV, XLSX, XLS, PDF, DOCX, DOC, RTF, PPTX, JSON 파일을 첨부하세요.')
        key=secrets.token_hex(16);path=app.DATA/'attachments'/(key+ext)
        raw=handler.rfile.read(length)
        if len(raw)!=length:raise ValueError('파일 전송이 완료되지 않았습니다.')
        path.write_bytes(raw);path.chmod(0o600)
        process=subprocess.run([str(app.ROOT/'.venv/bin/python'),str(app.ROOT/'scripts/extract-file.py'),str(path)],capture_output=True,text=True,timeout=45)
        try:value=json.loads(process.stdout)
        except ValueError:raise ValueError('문서 읽기 환경을 확인해 주세요.')
        if process.returncode or value.get('error'):raise ValueError(value.get('error','문서를 읽지 못했습니다.'))
        with app.db() as c:c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?)',(key,name,length,value['text'],int(value['truncated']),app.now()))
        app.event('attachment','첨부 자료 읽기 완료: '+name)
        return handler.send_json({'id':key,'name':name,'size':length,**value})
    except (ValueError,subprocess.TimeoutExpired) as e:
        if path:path.unlink(missing_ok=True)
        return handler.send_json({'error':str(e) if isinstance(e,ValueError) else '문서 읽기 시간이 초과되었습니다. 파일을 나눠 주세요.'},400)

def validate_ids(app,ids):
    if not isinstance(ids,list) or len(ids)>5 or len(set(str(x) for x in ids))!=len(ids):raise ValueError('작업당 최대 5개의 서로 다른 파일을 첨부하세요.')
    for key in ids:
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key) or not app.rows('SELECT id FROM attachments WHERE id=?',(key,)):raise ValueError('첨부 파일을 다시 선택해 주세요.')
    return ids

def metadata(app):
    return app.rows('SELECT id,name,size,truncated,length(text) AS chars FROM attachments ORDER BY created DESC')

def context(app,task,budget=12000):
    out=[]
    for key in json.loads(task.get('attachment_ids','[]')):
        row=app.rows('SELECT name,text FROM attachments WHERE id=?',(key,))
        if row:
            part='\n[첨부 자료: '+row[0]['name']+']\n'+row[0]['text'];out.append(part[:budget]);budget-=len(out[-1])
            if budget<=0:
                out.append('\n[첨부 자료가 길어 이후 내용은 생략되었습니다. 전체 문서를 읽었다고 주장하지 마세요.]');break
    return '\n'.join(out)
