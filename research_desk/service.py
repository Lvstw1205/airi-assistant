import json
import re
from urllib.parse import parse_qs, urlsplit
from . import contracts as C
from . import core

def is_research(profile,opts):
    if opts.get('delivery_style')=='professional_research':return not bool(opts.get('_research_id'))
    text=str(opts.get('query') or '')
    return profile in ('market','company') or opts.get('delivery_style')=='investment_v2' or bool(re.search(r'투자|증시|주식|채권|재무|실적|밸류에이션|investment|equities|fixed income|valuation',text,re.I))

def public(record):
    d=record['payload'];data={k:v for k,v in d.items() if k not in ('pack','plan_attempts','plan_reviews','draft_notes','draft_notes_version','notes_audit','notes_review_key','resume_candidate')}
    pack=d.get('pack') or {}
    # Polling clients need citation metadata, not repeated full article/PDF bodies.
    source_fields=('id','title','publisher','name','published','url','page','tier','primary_attachment','retrieved','sha256')
    data['sources']=[{k:v for k,v in source.items() if k in source_fields} for source in pack.get('sources',{}).values()];data['gaps']=pack.get('gaps',[])
    data['evidence_count']=len(pack.get('evidence',{}))
    from .render import source_names
    data['citations']={k:source_names(pack,[k]) for k in pack.get('evidence',{})}
    return {k:record[k] for k in ('id','revision','state','created','updated')} | data

def start(app,raw,destination='web',generation=None):
    import intelligence
    # Dedicated local research model; leave ordinary chat/voice model settings alone.
    selected=raw.get('research_model') or 'qwen3.5:9b'
    if selected not in ('qwen3.5:9b','gemma4:latest','gemma4:26b'):raise ValueError('Choose an installed local research model.')
    opts=C.options({**intelligence.settings(app),**raw,'model':selected});s=intelligence.store(app)
    job_opts={**intelligence.settings(app),'language':'en','delivery_style':'professional_research','deadline_seconds':2400,'model':opts['model'],
              '_destination':destination,'_generation':generation}
    record,job_id=core.new(s,opts,job_opts);intelligence.ensure_worker(app)
    return {'id':job_id,'workflow_id':record['id'],'state':'queued','progress':'Stage 1: source research',
            'url':'/research-desk/?id='+record['id'],'notice':'근거 10–15개와 핵심 논지·목차를 먼저 만들게. 본문은 승인 후 작성해.'}

def status(app,id=None):
    import intelligence
    s=intelligence.store(app);core.setup(s)
    def live(record):
        result=public(record)
        with s.db() as c:job=c.execute("SELECT state,progress,error FROM jobs WHERE request_key LIKE ? AND state IN ('running','waiting_storage') ORDER BY created DESC LIMIT 1",('research:'+record['id']+':'+str(record['revision'])+':%',)).fetchone()
        if job:
            result['progress']=job['progress'];text=job['progress']
            result['active_node']='M6' if 'M6' in text else 'M1' if text.startswith('M1 ') and '자료 정리' in text else None
            if job['state']=='waiting_storage':result.update(state='waiting_storage',error=job['error'],active_node=None)
        else:result['active_node']=None
        return result
    if id:return live(core.get(s,id))
    with s.db() as c:rows=c.execute('SELECT id FROM research_workflows ORDER BY created DESC LIMIT 30').fetchall()
    return {'workflows':[live(core.get(s,r['id'])) for r in rows]}

def action(app,body,destination='web',generation=None):
    import intelligence
    from .evidence import files
    if body.get('action')=='create':return start(app,body,destination,generation)
    id=body.get('id');revision=body.get('revision')
    if not isinstance(id,str) or type(revision) is not int:raise ValueError('Workflow ID and revision required.')
    if body.get('research_model'):
        selected=body['research_model']
        if selected not in ('qwen3.5:9b','gemma4:latest','gemma4:26b'):raise ValueError('Choose an installed local research model.')
        record=core.get(intelligence.store(app),id)
        if body.get('action') not in ('retry','retry_plan') or record['state'] not in ('failed','needs_sources') or record['revision']!=revision:raise ValueError('Model changes require a failed revision and a fresh plan.')
        record['payload']['options']['model']=selected;core.save(intelligence.store(app),record)
    opts={**intelligence.settings(app),'model':core.get(intelligence.store(app),id)['payload']['options']['model'],'language':'en','deadline_seconds':2400,'_destination':destination,'_generation':generation}
    if body.get('action')=='retry' and any(k in body for k in ('source_urls','attachments','query')):
        record=core.get(intelligence.store(app),id)
        if record['revision']!=revision or record['state'] not in ('failed','needs_sources'):raise ValueError('Only evidence-limited revisions may receive new source material.')
        record['payload']['options']=C.options({**record['payload']['options'],**{k:body[k] for k in ('source_urls','attachments','query') if k in body}})
        core.save(intelligence.store(app),record)
    job=core.advance(intelligence.store(app),id,body.get('action'),revision,opts)
    intelligence.ensure_worker(app);return {'id':job,'workflow_id':id,'workflow':status(app,id)}

def notice(report):
    r=report['professional_research'];d=r['payload'];id=r['id'][:8]
    if r['state']=='awaiting_approval':
        from .render import source_names
        p=d['plan'];parts=['리서치 1·2단계를 마쳤어. 근거와 논지를 확인해 줘. 본문은 승인 후 작성해.','http://127.0.0.1:8766/research-desk/?id='+r['id'],'Thesis: '+p['thesis']['text'],'Consensus: '+(p['consensus']['text'] if p.get('consensus') else 'Data not available; dated consensus required.'),'Variant: '+p['variant']['text']]
        for i,u in enumerate(d['notes']):parts.append(str(i+1)+'. '+u['text']+'\nSource: '+source_names(d['pack'],u['evidence_ids']))
        parts.append('Outline: '+'; '.join(x['title'] for x in p['outline']))
        if p['valuation']['available']:parts.append('Valuation assumptions (Estimate): '+'; '.join(a['name']+' = '+str(a['value'])+' '+a['unit']+'; '+a['basis']+'; '+a['method'] for a in p['valuation']['assumptions']))
        parts.extend('Evidence limit: '+x for x in p['missing_data'])
        parts.append('진행: 리서치 승인 '+id+' '+str(r['revision']))
        return '\n\n'.join(parts)
    if r['state']=='awaiting_continue':return '심층 보고서의 다음 두 섹션을 작성했어. 확인 후 “리서치 계속 '+id+'”라고 해 줘.\n/research-desk/?id='+r['id']
    return '리서치에 추가 근거가 필요해. '+d.get('progress','')+'\n/research-desk/?id='+r['id']

def chat_request(app,text,destination='web'):
    # Only explicit research commands can approve a report. Generic yes/continue does not.
    match=re.fullmatch(r'\s*(?:리서치|research)\s+(승인|계속|재시도|취소|approve|continue|retry|cancel)\s+([a-f0-9]{8,32})(?:\s+(\d+))?\s*',text,re.I)
    if not match:return None
    import intelligence
    s=intelligence.store(app);core.setup(s)
    with s.db() as c:rows=c.execute('SELECT id,revision FROM research_workflows WHERE id LIKE ?',(match[2].lower()+'%',)).fetchall()
    if len(rows)!=1:return {'text':'해당 리서치 ID를 확인해 줘.'}
    act={'승인':'approve','계속':'continue','재시도':'retry','취소':'cancel'}.get(match[1],match[1].lower())
    if act=='approve' and not match[3]:return {'text':'계획의 버전까지 넣어 줘. 예: 리서치 승인 '+match[2]+' '+str(rows[0]['revision'])}
    cfg=app.telegram_bridge.config(app) if destination=='telegram' else {}
    try:
        action(app,{'id':rows[0]['id'],'revision':int(match[3] or rows[0]['revision']),'action':act},destination,cfg.get('generation'))
        return {'text':'리서치 '+{'approve':'승인을 기록하고 본문 작성을 시작했어.','continue':'다음 두 섹션을 이어서 작성할게.','retry':'근거를 다시 조사할게. 이전 승인은 해제했어.','cancel':'진행을 취소했어.'}[act]}
    except ValueError as error:return {'text':str(error)}

def handle_get(app,handler,path):
    if not path.startswith('/api/research-desk'):return False
    from .evidence import files
    args=parse_qs(urlsplit(handler.path).query);id=args.get('id',[None])[0]
    if path=='/api/research-desk/files':handler.send_json({'files':files()});return True
    if path=='/api/research-desk':handler.send_json(status(app,id));return True
    handler.send_json({'error':'Not found'},404);return True

def handle_post(app,handler,path,body):
    if path!='/api/research-desk':return False
    try:handler.send_json(action(app,body))
    except (ValueError,TypeError,KeyError) as error:handler.send_json({'error':str(error)},400)
    return True
