"""MCP registration/discovery; third-party tool calls use explicit approval."""
import json,os,re,secrets,subprocess,signal,time
from urllib.parse import urlsplit

def builtin(app):return {'id':'market','name':'Canada / US Market Data','transport':'stdio','command':str(app.ROOT/'.venv/bin/python'),'args':[str(app.ROOT/'scripts/market_mcp.py')]}
def init(app):
    with app.db() as c:c.execute('CREATE TABLE IF NOT EXISTS mcp_servers(id TEXT PRIMARY KEY,name TEXT,config TEXT,tools TEXT,status TEXT)')
    folder=app.DATA/'mcp-secrets';folder.mkdir(exist_ok=True,mode=0o700)
def servers(app):
    return [{'id':'market','name':'Canada / US Market Data','transport':'stdio','builtin':True,'status':'Built in · yfinance + Bank of Canada','tools':[{'name':n} for n in ('market_exchange_rate','market_quote','market_search')]}]+[{**{k:r[k] for k in ('id','name','status')},'transport':json.loads(r['config'])['transport'],'tools':json.loads(r['tools']),'has_token':(app.DATA/'mcp-secrets'/r['id']).exists()} for r in app.rows('SELECT * FROM mcp_servers')]
def save(app,body):
    name=app.text_value(body,'name',100);transport=body.get('transport','http')
    if transport=='http':
        url=app.text_value(body,'url',2000);p=urlsplit(url)
        if p.username or p.password or p.query or p.fragment or not (p.scheme=='https' or (p.scheme=='http' and p.hostname in ('localhost','127.0.0.1') and (p.port or 80)>=1024)):raise ValueError('Use an HTTPS MCP endpoint or local HTTP port. Put the token in its own field.')
        config={'transport':'http','url':url}
    elif transport=='stdio':
        command=app.text_value(body,'command',1000);args=body.get('args',[])
        if not os.path.isabs(command) or not os.path.isfile(command) or not isinstance(args,list) or len(args)>30 or any(not isinstance(a,str) or len(a)>2000 for a in args):raise ValueError('Use an installed executable’s absolute path and a JSON argument array.')
        config={'transport':'stdio','command':command,'args':args}
    else:raise ValueError('Supported transports: HTTP or stdio.')
    token=body.get('token','')
    if not isinstance(token,str) or len(token)>4000 or '\n' in token or '\r' in token:raise ValueError('Invalid token.')
    key=secrets.token_hex(12)
    with app.db() as c:c.execute('INSERT INTO mcp_servers VALUES(?,?,?,?,?)',(key,name,json.dumps(config),'[]','Registered · not tested'))
    if token:
        path=app.DATA/'mcp-secrets'/key;path.write_text(token);path.chmod(0o600)
    return {'id':key}
def config(app,key):
    if key=='market':return builtin(app)
    rows=app.rows('SELECT config FROM mcp_servers WHERE id=?',(key,))
    if not rows:raise ValueError('MCP server not registered.')
    value=json.loads(rows[0]['config']);secret=app.DATA/'mcp-secrets'/key
    if secret.exists():value['headers']={'Authorization':'Bearer '+secret.read_text()}
    return value

def request(app,key,op,tool=None,arguments=None):
    cfg=config(app,key);payload={'server':cfg,'op':op,'tool':tool,'arguments':arguments or {}}
    process=subprocess.Popen([str(app.ROOT/'.venv/bin/python'),str(app.ROOT/'scripts/mcp_client.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True,env={**os.environ,'AIRI_DATA':str(app.DATA)})
    try:
        out,_=process.communicate(json.dumps(payload),timeout=50)
        result=json.loads(out)
        if result.get('error'):
            error=result['error']
            for secret in cfg.get('headers',{}).values():error=error.replace(secret,'[redacted]').replace(secret.removeprefix('Bearer '),'[redacted]')
            raise ValueError(error)
        return result['result']
    except (subprocess.TimeoutExpired,json.JSONDecodeError):raise ValueError('MCP timed out or returned an invalid response. No automatic retry.') from None
    finally:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        process.wait(timeout=3)

def discover(app,key):
    value=request(app,key,'list')
    if key!='market':
        with app.db() as c:c.execute('UPDATE mcp_servers SET tools=?,status=? WHERE id=?',(json.dumps(value['tools']),'Connected · '+str(len(value['tools']))+' tools',key))
    return value

def prepare(app,body):
    key=app.text_value(body,'server_id',24);tool=app.text_value(body,'tool',120);args=body.get('arguments',{})
    if not isinstance(args,dict) or len(json.dumps(args))>12000:raise ValueError('Tool arguments must be a JSON object under 12 KB.')
    available=discover(app,key)['tools']
    if not any(t['name']==tool for t in available):raise ValueError('Tool not found on the server.')
    aid=secrets.token_hex(16);name=next(s['name'] for s in servers(app) if s['id']==key)
    payload={'server_id':key,'tool':tool,'arguments':args,'name':name+' / '+tool,'message':'MCP tool call · '+name+' / '+tool+'\n'+json.dumps(args,ensure_ascii=False)}
    with app.db() as c:c.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?)',(aid,'mcp_tool',json.dumps(payload),'pending',time.time(),None))
    return {'id':aid}
