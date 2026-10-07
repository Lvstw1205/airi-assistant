"""One shared, bounded view of API tools, tasks, files and execution results."""
import json,re,video_production

def catalog(app):
    return [{'id':t['id'],'name':t['name'],'description':t.get('description',''),
             'method':t['method'],'provider':t['provider'],'connection':t['connection'],'enabled':bool(t['enabled']),
             'scheduled_auto_run':bool(t['auto_run'])}
            for t in app.automation.public_tools(app)]

def related_files(app,query):
    files=app.attachments.metadata(app)
    matched=[f for f in files if f['name'].lower() in query.lower()]
    if not matched and re.search(r'첨부|업로드|파일|문서|attachment|uploaded|document',query,re.I):
        matched=files[:3]
    result=[]
    for f in matched[:3]:
        row=app.rows('SELECT text FROM attachments WHERE id=?',(f['id'],))
        result.append({'name':f['name'],'excerpt':row[0]['text'][:2000] if row else '',
                       'partial':bool(f['chars']>2000 or f['truncated'])})
    return result

def snapshot(app,query):
    tasks=app.rows('SELECT id,title,due_date,due_time,status,done,action,tool_id,attachment_ids,result FROM tasks ORDER BY id DESC LIMIT 12')
    files=app.attachments.metadata(app)
    file_names={f['id']:f['name'] for f in files}
    tools=catalog(app);tool_names={t['id']:t['name'] for t in tools}
    for task in tasks:
        task['api_name']=tool_names.get(task.pop('tool_id'),'')
        task['files']=[file_names.get(key,'파일') for key in json.loads(task.pop('attachment_ids'))]
        task['result']=task['result'][:700]
    executions=[]
    for a in app.rows('SELECT id,action,status,payload,result FROM approvals ORDER BY created DESC LIMIT 5'):
        payload=json.loads(a['payload'])
        executions.append({'id':a['id'],'name':payload.get('name','n8n 연습'),'status':a['status'],'result':(a['result'] or '')[:1200]})
    import mac_cluster
    return {'airi_topology':{'identity':'User의 개인 비서 AIRI','primary_roles':mac_cluster.ROLES['primary'],'worker_roles':mac_cluster.ROLES['M1']},'registered_mcps':[{'id':s['id'],'name':s['name'],'tools':[t['name'] for t in s['tools']]} for s in app.mcp_bridge.servers(app)],'registered_apis':tools,'tasks':tasks,'files':[{'name':f['name'],'chars':f['chars']} for f in files[:12]],
            'related_file_excerpts':related_files(app,query),'recent_executions':executions,
            'video_generation':video_production.capability(app),
            'image_generation':{'available':bool(app.llm_client.registered_openai('openai:auto')),'interface':'이미지 작업실 · 설명으로 생성 또는 참고 이미지 최대 4장 편집',
                                'subjects':'General image generation: scenes, offices, animals, objects and illustrations. No subject whitelist. Previous successful images are examples, not capability restrictions. Provider policy and account permissions still apply.'},
            'telegram':{k:v for k,v in app.telegram_bridge.public(app).items() if k in ('enabled','paired','notifications','status','news_schedule')}}

def prepare_api_request(app,query):
    """Only an explicit named imperative creates a reviewable request, never executes."""
    if re.search(r'하지\s*마|하지\s*말|실행하지|호출하지|don.t|do not',query,re.I):return None
    action=re.search(r'실행해|호출해|사용해\s*줘|실행\s*해\s*줘|호출\s*해\s*줘|\b(run|call|execute)\b',query,re.I)
    if not action:return None
    tools=[t for t in app.automation.public_tools(app) if t['enabled'] and t['name'].lower() in query.lower()]
    if not tools:return None
    if len(tools)>1:return {'message':'실행할 API가 여러 개 언급됐어. 먼저 실행할 API 이름을 하나 골라줘.'}
    tool=tools[0]
    if any(json.loads(a['payload']).get('tool',{}).get('id')==tool['id'] for a in app.rows("SELECT payload FROM approvals WHERE status='pending'")):
        return {'message':tool['name']+'의 승인 대기 요청이 이미 있어. 자동화 연습에서 내용을 확인해줘.'}
    # Include document data in an external request only when the user named the file.
    files=[f for f in related_files(app,query) if f['name'].lower() in query.lower()]
    content=query
    if files:content+='\n첨부 참고 자료(JSON): '+json.dumps(files,ensure_ascii=False)
    aid=app.automation.create_approval(app,tool,content)
    return {'id':aid,'name':tool['name'],'message':tool['name']+' 실행 요청을 만들었어. 아래에서 실제 전송 내용을 확인하고 승인하면 실행돼.'}
