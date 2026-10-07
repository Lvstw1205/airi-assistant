"""AIRI and its existing single Telegram receiver share the AIRIStudio controller."""
import json,re,time,urllib.request
from pathlib import Path
ROOT=Path(__import__('os').environ.get('AIRI_STUDIO_ROOT',str(Path(__file__).resolve().parent/'integrations/airi-studio')))
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
HELP='\nAIRIStudio/부서 지시: 바로 배정 (예: AIRIStudio/중정 애플 새 기사 검증해)\nAIRIStudio/부서: 부서 현황\n/studio: 전체 현황\n/studio 부서 ECON: 부서 현황\n/studio 직원 ECON-W05: 직원 조회\n/studio 작업 ID: 작업 조회\n/studio 배정 내용: 업무 배정\n/studio 중정: 중정 보고\n/studio 감옥: 격리 현황\n/studio 일시정지 | 재개\n/studio 재계획 ID 내용\n/studio 신규주문차단\n역할 지침은 M1 앱에서 편집합니다. 전문 리포트의 논지 승인·반려는 연결된 Research Desk에서 처리합니다.'
STATES={'completed':'완료','failed':'오류로 중단','connection_wait':'연결·승인 대기',
        'replan_required':'재계획 필요','reviewer_unavailable':'검토자 대기',
        'working':'작업 중','reviewing':'검토 중','queued':'대기 중','delivery_wait':'산출물 검증 중','cancelled':'취소'}

def task_report(task,staff=()):
    lines=['['+task['department']+' / 업무 보고]',task['goal'],
           '상태: '+STATES.get(task['state'],task['state'])]
    failed=next((s for s in task.get('steps',[]) if s['state']=='failed'),None)
    if failed:
        person=next((s for s in staff if s['slot_id']==failed.get('executor_slot',failed['slot'])),{})
        lines.append('중단 단계: '+failed['id']+' · '+person.get('name',failed['slot'])+' · '+failed['node'].upper())
    error=task.get('error')
    if error:lines.append('원인: '+error)
    if task['state']=='failed':
        completed=sum(s['state']=='completed' for s in task.get('steps',[]))
        lines.append(f'완료된 {completed}단계의 기록은 보존했어. 이 작업은 아직 완료되지 않았어.')
    elif task['state']=='completed':lines.append('검토와 산출물 저장을 마쳤어.')
    lines.append('작업 ID: '+task['id'])
    return '\n'.join(lines)

def call(action,body=None):
    route='/org/state' if action=='state' else '/org/command'
    req=urllib.request.Request('http://127.0.0.1:8771'+route,data=json.dumps(body or {},ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+(ROOT/'data/token').read_text().strip()})
    with OPENER.open(req,timeout=12) as r:return json.load(r)

def status_text(state):
    active=[t for t in state['tasks'] if t['state'] in ('working','reviewing','queued')]
    nodes=' · '.join(n['id'].upper()+(' 연결' if n.get('online') else ' 오프라인') for n in state['nodes'])
    return f"AIRI Studio · 9개 부서 / {len(state['staff'])}명\n{nodes}\n실행·대기 프로젝트 {len(active)}개 · 완료 {state['metrics']['completed']}개\n"+('전체 일시정지 상태야.' if state['settings']['paused'] else '직원들은 실제 배정된 업무만 실행해. M1 앱에서 역할·기록·승인 흐름을 볼 수 있어.')

NAMES={'PLAN':'기획부','VIDEO':'영상제작부','ECON':'경제분석부','HR':'인사부','RISK':'위험관리부','RND':'연구개발부','IT':'IT 개발부','DES':'디자인부','CID':'중앙정보부'}
SHORT={'중정':'CID','중앙정보부':'CID','기획':'PLAN','영상':'VIDEO','영상제작':'VIDEO','경제':'ECON','경제분석':'ECON','인사':'HR','위험':'RISK','위험관리':'RISK','리스크':'RISK',
       '연구':'RND','연구개발':'RND','알앤디':'RND','개발':'IT','디자인':'DES'}

def department_token(token):
    t=token.strip().upper().replace(' ','')
    if t in NAMES:return t
    t=re.sub(r'부$','',token.strip().replace(' ',''))
    return SHORT.get(t) or department_of(token)

def assigned(t):
    lead='각하, 중앙정보부가 접수했습니다. ' if t['department']=='CID' else ''
    return lead+NAMES.get(t['department'],t['department'])+'에 배정했어. 담당자와 검토 과정은 AIRI Studio 앱에서 볼 수 있어.\n작업 ID: '+t['id']

def slash_order(text,request_id=None):
    """AIRIStudio/부서 지시 — e.g. 'AIRIStudio/중정 애플 새 기사 검증해'. No verb needed; the prefix is the order."""
    m=re.match(r'^\s*/?(?:airi\s*studio?|팀\s*웍스)\s*/\s*([^\s/]+)\s*(.*)$',text,re.I|re.S)
    if not m:return None
    dep=department_token(m[1])
    if not dep:return '부서를 못 찾았어. 예: AIRIStudio/중정, AIRIStudio/경제, AIRIStudio/ECON\n부서: '+', '.join(f'{v}({k})' for k,v in NAMES.items())
    goal=m[2].strip()
    if not goal:
        s=call('state');members=[x for x in s['staff'] if x['department']==dep]
        open_tasks=[t for t in s['tasks'] if t['department']==dep and t['state'] not in ('completed','cancelled')]
        return NAMES[dep]+f' · {len(members)}명 · 진행 중 {len(open_tasks)}건\n'+'\n'.join(t['id'][:8]+' · '+t['state']+' · '+t['goal'][:50] for t in open_tasks)
    body={'action':'start','goal':goal,'department':dep}
    if request_id:body['request_id']=request_id
    return assigned(call('command',body))

def command(text,request_id=None):
    order=slash_order(text,request_id)
    if order is not None:return order
    if not re.match(r'^/(?:timwork|studio)(?:\s|$)',text,re.I):return None
    arg=re.sub(r'^/studios?\s*','',text,flags=re.I).strip()
    if arg in ('','현황','상태','전체 현황','status'):return status_text(call('state'))
    actions={'일시정지':'pause','중지':'pause','재개':'resume','신규주문차단':'orders_stop'}
    if arg in actions:
        r=call('command',{'action':actions[arg],'request_id':request_id});return 'AIRI Studio '+arg+' 적용. '+('기존 포지션과 다른 실행 엔진 설정은 변경하지 않았어.' if arg=='신규주문차단' else '')
    if arg.startswith('배정 '):
        t=call('command',{'action':'start','goal':arg[3:],'request_id':request_id});return '업무를 실제 큐에 등록했어.\n'+t['id']+' · '+t['department']+'\n'+t['goal']
    if arg.startswith('재계획 '):
        pieces=arg.split(' ',2)
        if len(pieces)<3:raise ValueError('/studio 재계획 ID 변경내용')
        call('command',{'action':'retry','task_id':pieces[1],'change':pieces[2],'request_id':request_id});return '변경 내용을 기록하고 같은 승인 경로로 재개했어.'
    s=call('state')
    if arg.startswith('부서 '):
        dep=arg[3:].strip().upper();members=[x for x in s['staff'] if x['department']==dep]
        return '\n'.join(x['name']+' · '+x['role']+' · '+x['node'].upper()+' · '+x['work_state'] for x in members) or '부서 ID: PLAN VIDEO ECON HR RISK RND IT DES CID'
    if arg.startswith('직원 '):
        key=arg[3:].strip();p=next((x for x in s['staff'] if key in (x['slot_id'],x['name'])),None)
        return json.dumps({k:p.get(k) for k in ('name','role','node','work_state','current_task','prompt_revision')},ensure_ascii=False) if p else '직원을 찾지 못했어.'
    if arg.startswith('작업 '):
        t=next((x for x in s['tasks'] if x['id']==arg[3:].strip()),None)
        return task_report(t,s['staff']) if t else '작업을 찾지 못했어.'
    if arg=='감옥':return '\n'.join(i['id']+' · '+i['slot_id']+' · '+i['cell']+' · '+i['state'] for i in s['incidents']) or '현재 격리 사건이 없어.'
    if arg=='중정':return '\n'.join(t['goal']+' · '+t['state'] for t in s['tasks'] if t['department']=='CID') or '아직 중정 보고가 없어. 등록된 공개정보 점검 주기에 실행해.'
    return HELP

# AIRI Studio departments are fictional units of User's own AI organization, not real agencies.
DEPARTMENTS=[(r'중앙\s*정보부|중정|요원','CID'),(r'기획\s*부','PLAN'),(r'영상\s*(제작)?\s*부','VIDEO'),(r'경제\s*(분석)?\s*부','ECON'),
             (r'인사\s*부','HR'),(r'위험\s*(관리)?\s*부|리스크\s*팀','RISK'),(r'연구\s*개발\s*부|R&D|알앤디','RND'),(r'IT\s*(개발)?\s*부|개발\s*부','IT'),
             (r'디자인\s*부|디자인\s*스튜디오|UX\s*부','DES')]
ASK=r'라고\s*해|알아보|조사하|부탁해|배정해|맡겨|시켜|해\s*줘|해줘|해\s*봐|하라고|만들어|작성해|제작해|실행해|진행해|수행해|조사해|알아봐|분석해|찾아|보고해|감찰해|정리해|검토해|기획해|확인해|점검해'

def department_of(text):
    return next((dep for pattern,dep in DEPARTMENTS if re.search(pattern,text,re.I)),None)

def chat_request(app,text):
    result=command(text)
    if result is not None:return {'text':result}
    dep=department_of(text)
    mention=dep or re.search(r'User\s*Works?|팀\s*웍스|팀워크|회사|조직|직원',text,re.I)
    if not mention:return None
    if re.search(r'일시\s*정지|전체\s*중지',text):call('command',{'action':'pause'});return {'text':'AIRI Studio 확장팩을 일시정지했어.'}
    if re.search(r'하지\s*마|취소|방법|가능해\?|어떻게\s*(하|해)',text):return None
    state=None
    if re.search(r'연행|불러|소환',text):
        state=call('state')
        who=next((s for s in state['staff'] if s['name'] in text or s['slot_id'] in text.upper()),None)
        if who:
            r=call('command',{'action':'arrest','slot_id':who['slot_id'],'reason':'AIRI 지시: '+text[:300]})
            return {'text':f"각하, 요원 2명이 {who['name']}을(를) 연행합니다. 취조·고문·수감 후 심각성 조사로 사형 또는 교화를 판정하겠습니다."}
    if re.search(r'현황|상태|뭐\s*하|누가|연결',text) and not re.search(ASK,text):
        return {'text':status_text(state or call('state'))}
    explicit=dep or re.search(r"User\s*Works?|팀\s*웍스",text,re.I)
    strict=r"배정해|맡겨|만들어|작성해|제작해|실행해|진행해|수행해"
    if re.search(ASK if explicit else strict,text):
        body={'action':'start','goal':text}
        if dep:body['department']=dep
        return {'text':assigned(call('command',body))}
    return None

_last=0

def notifications(app,cfg,bridge):
    global _last
    if time.time()-_last<20:return
    _last=time.time()
    try:state=call('state')
    except Exception:return
    for t in state['tasks'][:40]:
        if t.get('test') or t['state'] not in ('completed','failed','connection_wait','replan_required'):continue
        key='studio:'+t['id']+':'+str(t['revision'])+':'+t['state']
        text=task_report(t,state['staff'])
        bridge.enqueue(app,cfg,key,text[:3500])
    for event in state['events']:
        if event['event_type']!='일일운영보고':continue
        report=event['payload'];bridge.enqueue(app,cfg,'studio:daily:'+report['day'],'[AIRI Studio / 일일 운영]\n'+report['day']+'\n완성 앱 '+str(report['app_completed'])+' / 목표 '+str(report['app_target'])+'\n'+('목표 달성' if report['target_met'] else '목표 미달 · M1 운영 화면에서 차단 원인을 확인해.'))
