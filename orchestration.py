"""Existing AIRI tool-loop adapters for a bounded, durable department workflow."""
import json,re,threading,time,uuid
from pathlib import Path
from urllib.parse import urlsplit
from airi_node.ledger import Ledger,encoded
from airi_core.execution.registry import Registry,Plan,financial_plan
from airi_core.execution.permissions import PermissionGate,redact

_services={};_lock=threading.Lock()

def classify(query):
    if re.search(r'(?:아이리|AIRI|M1|M6|맥|노드|작업자).{0,18}(?:상태|뭐\s*하|연결|작업\s*중)|^/(?:status|health|agents|tasks)$',query,re.I):return 'STATUS'
    if re.search(r'예약|매일|매주|내일.{0,12}(?:보고서|만들)|schedule',query,re.I):return 'SCHEDULE'
    if re.search(r'분석|보고서|조사|research|analy[sz]e',query,re.I):return 'TASK'
    if re.search(r'날씨|몇\s*시|시간|weather|time|환율',query,re.I):return 'QUICK_TOOL'
    return 'CHAT'

def service(app):
    with _lock:
        key=str(app.DATA)
        if key not in _services:_services[key]=Orchestrator(app)
        return _services[key]

class Orchestrator:
    def __init__(self,app):
        self.app=app;self.ledger=Ledger(app.DATA/'airi.sqlite3');self.registry=Registry(app.ROOT)
        self.gate=PermissionGate(self.ledger);self.generating=threading.Lock()

    def status(self):
        jobs=self.ledger.tasks(limit=50)
        return {'agents':[a.model_dump() for a in self.registry.agents.values()],
          'tasks':jobs,'approvals':self.gate.pending(),'max_tasks':8,'max_depth':3,'tool_limit':25,
          'existing_reports':'Existing PDF/news workflows retain their executor; new department workflow is explicit.'}

    def plan(self,body):
        query=body.get('query','');key=body.get('request_key','')
        if not isinstance(query,str) or not 1<=len(query)<=2000 or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',key):raise ValueError('Invalid plan request')
        ticker=body.get('symbol','NVDA').upper()
        if not re.fullmatch(r'[A-Z]{1,8}(?:\.(?:TO|KS|KQ))?',ticker):raise ValueError('Invalid equity symbol')
        plan=financial_plan(query,ticker)
        root=str(uuid.uuid5(uuid.NAMESPACE_URL,'airi-plan:'+key))
        ids={t.key:str(uuid.uuid5(uuid.UUID(root),t.key)) for t in plan.subtasks}
        values=[]
        for task in plan.subtasks:
            values.append({'task_id':ids[task.key],'root_task_id':root,'correlation_id':root,'idempotency_key':key+':'+task.key,
              'agent_id':task.agent_id,'tool_id':'agent.run','node_target':'prime','objective':task.objective,
              'input':{'agent_id':task.agent_id,'arguments':task.inputs},'constraints':{'max_total_seconds':plan.max_total_seconds},
              'depends_on':[ids[d] for d in task.depends_on],'optional':task.optional,'safe_retry':True,
              'max_retries':1,'timeout_seconds':task.deadline_seconds,'priority':self.registry.agents[task.agent_id].priority})
        jobs=self.ledger.submit_batch(values)
        return {'root_task_id':root,'plan':plan.model_dump(),'tasks':[t['task_id'] for t in jobs],'status':'QUEUED'}

    def call(self,tool,args,task):
        from agent_runtime import execute
        if tool not in self.registry.agents[task['agent_id']].tools:raise PermissionError('Tool is outside this department')
        with self.ledger.db(True) as c:
            count=c.execute('SELECT count(*) FROM airi_exec_audit WHERE task_id IN (SELECT task_id FROM airi_exec_tasks WHERE root_task_id=?) AND action LIKE ?',(task['root_task_id'],'tool:%')).fetchone()[0]
            if count>=25:raise ValueError('Root tool-call limit reached')
            c.execute('INSERT INTO airi_exec_audit(ts,task_id,actor,action,tier,result,detail_json) VALUES(?,?,?,?,?,?,?)',
                      (time.time(),task['task_id'],task['agent_id'],'tool:'+tool,'READ_ONLY','STARTED',encoded(redact(args))))
        if tool=='stock101_read':
            import stock101.service
            return stock101.service.analyze(self.app,args['symbol'])
        return execute(self.app,tool,args,task['objective'])

    def evidence(self,agent,args,task):
        mapping={'news':('web_search',{'query':args.get('query',task['objective'][:450])}),
          'research':('web_search',{'query':args.get('query',task['objective'][:450])}),
          'finance':('market_quote',{'symbol':args.get('symbol','NVDA')}),
          'stock101':('stock101_read',{'symbol':args.get('symbol','NVDA')}),
          'memory_manager':('memories_read',{}),'secretary':('tasks_read',{})}
        if agent in mapping:
            tool,parameters=mapping[agent];value=self.call(tool,parameters,task)
            if agent=='memory_manager':
                terms=re.findall(r'[A-Za-z가-힣0-9]{2,}',str(args.get('query','')))
                value={'memories':[m for m in value.get('memories',[]) if any(t.lower() in m['content'].lower() for t in terms)]}
            if agent=='stock101':
                value={k:v for k,v in value.items() if k!='bars'}
            return value
        if agent in ('coding','data_analyst','youtube'):
            if 'attachment_id' in args:return self.call('attachment_read',{'id':args['attachment_id']},task)
            return {'provided_text':str(args.get('text',''))[:8000],'current_data_unavailable':True}
        return {}

    def run(self,body):
        task=self.ledger.get(body.get('task_id',''))
        if not task or task['state']!='RUNNING' or task['node_actual']!='prime' or task['lease_owner']!=body.get('owner') or task['fence']!=body.get('fence'):
            raise ValueError('Task lease is not valid')
        if task['tool_id']!='agent.run':raise ValueError('Not an agent task')
        agent=task['agent_id'];config=self.registry.agents[agent]
        if not config.enabled:raise ValueError('Agent disabled')
        permission=self.gate.check('agent:'+agent,{},'READ_ONLY',task['task_id'],agent)
        if not permission['allowed']:raise PermissionError(permission['status'])
        with self.ledger.db() as c:
            first=c.execute('SELECT min(created) FROM airi_exec_tasks WHERE root_task_id=?',(task['root_task_id'],)).fetchone()[0]
        if time.time()-first>json.loads(task['constraints_json']).get('max_total_seconds',300):raise TimeoutError('Root deadline exceeded')
        refs=[]
        for identifier in json.loads(task['depends_on_json']):
            row=self.ledger.get(identifier);value=json.loads(row['output_json']) if row and row['output_json'] else {}
            refs.append({'task_id':identifier,'state':row['state'] if row else 'UNKNOWN','summary':str(value.get('summary',''))[:1600],
                         'sources':value.get('sources',[]),'claims':value.get('claims',[]),'error':row['error'] if row else 'missing'})
        if agent=='critic':
            issues=[{'type':'tool_failure','detail':r['error'] or r['state'],'task_id':r['task_id']} for r in refs if r['state']!='COMPLETE']
            for r in refs:
                for claim in r['claims']:
                    if claim.get('label') in ('OBSERVED','RETRIEVED') and not claim.get('as_of'):issues.append({'type':'missing_evidence','detail':'Observation missing timestamp','task_id':r['task_id']})
                    if claim.get('stale'):issues.append({'type':'stale_data','detail':'기록 시세가 오래되어 현재 가격으로 사용할 수 없어.','task_id':r['task_id']})
                    if claim.get('label')=='UNKNOWN':issues.append({'type':'missing_evidence','detail':claim.get('text','확인되지 않은 근거'),'task_id':r['task_id']})
            return {'summary':'검수: '+('자료 누락이 있어 확인된 부분만 사용해.' if issues else '자료 수집 기록과 시각을 확인했어. 해석은 별도 모델 의견이야.'),
                    'verdict':'PASS_WITH_WARNINGS' if issues else 'PASS','issues':issues,'context_refs':refs,
                    'claims':[v for r in refs for v in r['claims']],'sources':[v for r in refs for v in r['sources']]}
        args=json.loads(task['input_json'])['arguments']
        if agent=='ceo':
            review=self.ledger.get(json.loads(task['depends_on_json'])[0]);evidence=json.loads(review['output_json']) if review and review['output_json'] else {'error':'Review unavailable'}
        else:evidence=self.evidence(agent,args,task)
        observed=time.time();source_id='tool:'+task['task_id']
        from airi_core.execution.evidence import result as evidence_result
        grounded=evidence_result(agent,redact(evidence),task['task_id'],observed)
        if grounded:return grounded
        if agent in ('memory_manager','secretary'):
            summary=encoded(evidence)
        else:
            import humanlike_mind
            model=humanlike_mind.service(self.app).cfg['model']
            if model=='airi:auto':model='qwen3:4b'
            for endpoint in self.app.llm_client.endpoints_for(model):
                if urlsplit(endpoint['base_url']).hostname not in ('127.0.0.1','localhost','::1') or endpoint.get('key'):
                    raise ValueError('Only local models may run department jobs')
            prompt=self.registry.prompts[agent]+'\n출처 자료만 사용한다. 자료에 없는 현시세·숫자·날짜를 만들지 않는다. 3문장 이내로 요약하고 의견에는 [해석]을 붙인다.'
            if agent=='ceo':prompt+=' 관측 사실은 코드가 그대로 붙인다. 너는 조건부 해석만 JSON {"interpretation":"한 문장","scenario":"조건부 한 문장"}으로 반환한다. 검색 제목으로 원인을 단정하지 마.'
            messages=[{'role':'system','content':prompt},{'role':'user','content':encoded({'question':task['objective'],'evidence':evidence})[:18000]}]
            from intelligence.priority import foreground_busy
            deadline=time.monotonic()+max(0,min(config.timeout_seconds,first+json.loads(task['constraints_json']).get('max_total_seconds',300)-time.time()))
            while foreground_busy(self.app) or not self.generating.acquire(blocking=False):
                if time.monotonic()>deadline:raise TimeoutError('Foreground conversation is busy')
                time.sleep(.25)
            parts=[]
            stream=None
            try:
                stream=self.app.llm_client.stream(messages,model,max_tokens=450)
                for part in stream:
                    if foreground_busy(self.app):raise InterruptedError('Conversation preempted background inference')
                    if self.ledger.get(task['task_id'])['state']=='CANCELLED':raise InterruptedError('Task cancelled')
                    if time.monotonic()>deadline:raise TimeoutError('Agent deadline exceeded')
                    if part.get('type')=='token':parts.append(part['text'])
            finally:
                if stream is not None:stream.close()
                self.generating.release()
            summary=''.join(parts)
            if agent=='ceo':
                from pixel_floor import grounded_comment
                try:
                    if re.search(r'때문|덕분|상승했|하락했|오른 이유|내린 이유',summary):raise ValueError('Unverified causal assertion')
                    commentary=grounded_comment(summary,evidence)
                except ValueError:commentary='[미확인] 모델 의견이 근거 검사를 통과하지 못해 생략했어.'
                summary='\n\n'.join(r['summary'] for r in evidence.get('context_refs',[]))+ '\n\n'+commentary
                return {'summary':summary,'claims':evidence.get('claims',[])+[{'text':commentary,'label':'INFERRED','source_ids':[],'as_of':None}],
                        'sources':evidence.get('sources',[]),'issues':evidence.get('issues',[]),'agent_id':agent,'node_actual':'prime','verified_facts':False}
        claims=[{'text':summary,'label':'INFERRED','source_ids':[source_id],'as_of':None}]
        return {'summary':summary,'claims':claims,'sources':[{'id':source_id,'url_or_path':source_id,'retrieved_at':observed}],
                'evidence':redact(evidence),'agent_id':agent,'node_actual':'prime','verified_facts':False}

def direct_status(app,query):
    if classify(query)!='STATUS':return None
    import expansion_ui
    data=expansion_ui.snapshot(app);n=data.get('node') or {};e=n.get('executor') or {};peer=n.get('peer') or {}
    loaded=', '.join(m['name'] for m in (n.get('models') or {}).get('loaded',[])) or '확인되지 않음'
    return f"M6 아이리 본부는 {'실행 중' if n else '연결 확인 필요'}이고, M1은 {peer.get('state','미확인')} 상태야. 연결 지연은 {peer.get('latency_ms','미확인')}ms야. 현재 적재된 모델은 {loaded}, 공통 작업 상태는 {e.get('counts',{})}야. 자세한 기록은 SYSTEM / AGENTS에서 볼 수 있어."

def handle_get(app,handler,path):
    if path!='/api/execution/status':return False
    handler.send_json(service(app).status());return True

def handle_post(app,handler,path,body):
    if not path.startswith('/api/execution/'):return False
    runtime=service(app)
    if path=='/api/execution/plan':value=runtime.plan(body)
    elif path=='/api/execution/run':
        try:value=runtime.run(body)
        except InterruptedError:
            handler.send_json({'error':'Foreground conversation took priority','retryable':True},503);return True
        except TimeoutError:
            handler.send_json({'error':'Department deadline exceeded','retryable':False},504);return True
    elif path=='/api/execution/cancel':value=runtime.ledger.cancel_root(body['root_task_id']) if body.get('root_task_id') else runtime.ledger.cancel(body['task_id'])
    elif path=='/api/execution/approve':value={'state':runtime.gate.decide(body['approval_id'],body.get('allow') is True,'ui',True)}
    elif path=='/api/execution/reload':value={'agents':runtime.registry.reload()}
    else:handler.send_json({'error':'Not found'},404);return True
    handler.send_json(value);return True
