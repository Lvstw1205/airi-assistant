"""Small adapter installed beside AIRI's current agent_runtime.py."""
import json,re,urllib.request
from pathlib import Path
BASE='http://127.0.0.1:8771'
TOKEN=Path(__import__('os').environ.get('AIRI_STUDIO_TOKEN_FILE',str(Path(__file__).resolve().parent/'integrations/airi-studio/data/token')))
def call(path,body=None):
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN.read_text().strip()})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8) as r:return json.load(r)
def status():
    state=call('/state')
    return {'nodes':state['nodes'],'jobs':state['jobs'][:12],'coordinator':'m6'}
def submit(args):
    body={k:args[k] for k in ('target','kind','instruction') if k in args};body['source']='airi'
    job=call('/submit',body)
    return {'id':job['id'],'target':job['target'],'status':job['status'],'completed':False,'note':'Queued on M6; target worker will execute. Read node_jobs_status for actual result.'}
def company_call(action,args):
    if action in ('goal','status'):
        import airi_studio
        return airi_studio.call('state') if action=='status' else airi_studio.call('command',dict(args,action='start'))
    paths={'goal':'office-company-goal','status':'office-company-status','project':'office-project-run'}
    req=urllib.request.Request('http://127.0.0.1:8773/'+paths[action],data=json.dumps(args).encode(),headers={'Content-Type':'application/json','Host':'127.0.0.1:8770','Authorization':'Bearer '+TOKEN.read_text().strip()})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=12) as r:return json.load(r)
def chat_request(app,text):
    import research_desk
    if re.search(r'User\s*Works|티모?\s*웍스|회사|직원|협업',text,re.I) and re.search(r'분석|리포트|보고서|analy|research',text,re.I) and research_desk.is_research('',{'query':text}) and not re.search(r'하지\s*마|취소|cancel|do not',text,re.I):
        result=research_desk.start(app,{'query':text,'origin':'studio'})
        return {'text':result['notice']+'\n'+result['url']}
    # Explicit device + task request. General discussion must not create work.
    if re.search(r'하지\s*마|실행\s*금지|취소|하지\s*않|don.t|do not|cancel',text,re.I):return None
    if re.search(r'직원|회사|협업|사무실|팀',text) and re.search(r'배정해|맡겨|만들어|만들자|제작해|작성해|실행해|진행해|수행해',text):
        try:
            mission=company_call('goal',{'goal':text})
            return {'text':'회사 목표를 접수했어. M6에서 필요한 역할을 선택하고 M1·M6 직원에게 배정할게. 목표 ID: '+mission['id']+'. M1 사무실의 회사·지식 창에서 실제 결과를 볼 수 있어.'}
        except Exception:return {'text':'M1 회사 작업실에 연결하지 못했어. 목표가 접수되었는지는 회사·지식 창에서 확인해 줘.'}
    match=re.search(r'\b(m1|m6)\b',text,re.I)
    if not match:return None
    if re.search(r'하지\s*마|실행\s*금지|취소|하지\s*않|don.t|do not|cancel',text,re.I):return None
    if not re.search(r'실행|점검|확인해|작성해|만들어|요약해|정리해|돌려|맡겨|배정|run\b|check\b|write\b|summarize\b',text,re.I):return None
    if re.search(r'방법|할\s*수|가능해|어떻게|how (to|can)|can (you|i)',text,re.I):return None
    arrow=re.search(r'\bm6\s*(?:->|→|에서)\s*(m1|m6)\b',text,re.I)
    target=arrow.group(1).lower() if arrow else match.group(1).lower()
    if re.search(r'삭제|백업|브라우저.{0,8}(조작|열어)|메일.{0,6}보내|셸|터미널|delete|backup|shell|browser',text,re.I):
        return {'text':'현재 노드에서 실행할 수 있는 작업은 시스템 점검, 로컬 AI 문서 작성, 제공한 글 요약이야. 파일 조작·브라우저 제어는 아직 연결하지 않았어.'}
    kind='health' if re.search(r'상태|점검|연결|health|status|check',text,re.I) else 'summarize' if re.search(r'요약|분석|summar',text,re.I) else 'write'
    try:
        job=submit({'target':target,'kind':kind,'instruction':text})
        return {'text':f"{job['target'].upper()}에 작업을 배정했어. 작업 ID: {job['id']}. 아직 완료된 건 아니야. M1의 AIRI OFFICE 창에서 진행 상태와 결과를 확인할 수 있어."}
    except Exception:return {'text':'M1 사무실 작업 서비스에 연결하지 못했어. 작업을 실행했다고 확인할 수 없어. AIRI OFFICE 연결 상태를 확인해 줘.'}
