import datetime as dt
import json
import re
import time
import uuid
from . import contracts as C
from . import evidence as E
from . import valuation as V

STATES = {'queued','collecting','awaiting_approval','drafting','awaiting_continue','reviewing','complete','limited','needs_sources','failed','cancelled'}

def setup(store):
    with store.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS research_workflows(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, payload TEXT NOT NULL)')

def get(store, id):
    setup(store)
    with store.db() as c: row=c.execute('SELECT * FROM research_workflows WHERE id=?',(id,)).fetchone()
    if not row: raise ValueError('Research workflow not found.')
    return {**dict(row),'payload':json.loads(row['payload'])}

def save(store, record, **changes):
    if changes.get('state',record['state']) not in STATES:raise ValueError('Invalid research state')
    record={**record,**changes,'updated':dt.datetime.now(dt.timezone.utc).isoformat()}
    with store.db() as c:
        current=c.execute('SELECT state,revision FROM research_workflows WHERE id=?',(record['id'],)).fetchone()
        if not current or current['state']=='cancelled':raise ValueError('Research cancelled.')
        if current['revision']!=record['revision']:raise ValueError('Research revision changed.')
        c.execute('UPDATE research_workflows SET state=?,updated=?,payload=? WHERE id=? AND revision=?',
                  (record['state'],record['updated'],json.dumps(record['payload'],ensure_ascii=False),record['id'],record['revision']))
    return record

def new(store, opts, job_options):
    setup(store);id=uuid.uuid5(uuid.NAMESPACE_URL,'airi-research:'+opts['request_id']).hex if opts.get('request_id') else uuid.uuid4().hex;now=dt.datetime.now(dt.timezone.utc).isoformat()
    payload={'options':opts,'pack':None,'notes':[],'plan':None,'sections':[],'reviews':[], 'progress':'Queued for source research','model_calls':[], 'approval':None,'error':None}
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=c.execute('SELECT id FROM research_workflows WHERE id=?',(id,)).fetchone()
        if existing:
            job=c.execute('SELECT id FROM jobs WHERE request_key=?',('research:'+id+':1:plan:0',)).fetchone()
            return get(store,id),job['id']
        c.execute('INSERT INTO research_workflows VALUES(?,?,?,?,?,?)',(id,1,'queued',now,now,json.dumps(payload,ensure_ascii=False)))
        job_id=enqueue(c,id,1,'plan',0,job_options,now)
    return get(store,id),job_id

def enqueue(c,id,rev,stage,batch,opts,now):
    key=f'research:{id}:{rev}:{stage}:{batch}'
    value={**opts,'delivery_style':'professional_research','language':'en','_research_id':id,'_research_stage':stage,'_research_batch':batch}
    c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,key,'market',json.dumps(value),'queued','Research '+stage,now,now,None,None))
    return c.execute('SELECT id FROM jobs WHERE request_key=?',(key,)).fetchone()['id']

def advance(store,id,action,revision,job_options):
    setup(store);now=dt.datetime.now(dt.timezone.utc).isoformat()
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM research_workflows WHERE id=?',(id,)).fetchone()
        if not row or row['revision']!=revision:raise ValueError('Review the current research revision before approving.')
        data=json.loads(row['payload']);state=row['state']
        if action=='cancel':
            if state in ('complete','limited','cancelled'):raise ValueError('Research is already finished.')
            c.execute("UPDATE research_workflows SET state='cancelled',updated=? WHERE id=?",(now,id));return id
        if action=='approve':
            if state!='awaiting_approval':raise ValueError('This research plan is not awaiting approval.')
            if not data.get('plan') or len(data.get('notes',[]))<10:raise ValueError('Complete research notes and thesis are required before approval.')
            data['approval']={'at':now,'revision':revision,'plan_hash':C.digest({'plan':data['plan'],'pack':data['pack']})}
            stage='draft';state='drafting'
        elif action=='continue':
            if state!='awaiting_continue' or not data.get('approval'):raise ValueError('No approved deep-dive continuation is pending.')
            stage='draft';state='drafting'
        elif action in ('retry_plan','revise'):
            allowed=('awaiting_approval',) if action=='revise' else ('failed','needs_sources')
            if state not in allowed or not (data.get('pack') or {}).get('evidence') or (action=='revise' and len(data.get('notes',[]))<10):raise ValueError('Saved evidence is required to resume; complete notes are required to revise an approved-stage plan.')
            attempts=data.get('plan_attempts',[])
            data['resume_candidate']=attempts[-1]['raw'] if action=='retry_plan' and attempts and attempts[-1].get('revision')==revision else None
            revision+=1;data.update(approval=None,plan=None,notes=[],sections=[],reviews=[],error=None,reuse_evidence=True)
            stage='plan';state='queued'
        elif action=='retry':
            if state not in ('failed','needs_sources'):raise ValueError('Only failed or evidence-limited research can be retried.')
            # Re-research always invalidates approval and previous draft.
            revision+=1;data.update(approval=None,plan=None,sections=[],notes=[],draft_notes=None,pack=None,reviews=[],model_calls=[],error=None,reuse_evidence=False)
            stage='plan';state='queued'
        else:raise ValueError('Unknown research action.')
        data['progress']='Queued: '+stage
        c.execute('UPDATE research_workflows SET state=?,revision=?,updated=?,payload=? WHERE id=?',(state,revision,now,json.dumps(data,ensure_ascii=False),id))
        return enqueue(c,id,revision,stage,len(data['sections']),job_options,now)

def units(values,pool,forecast=False):
    return [u for value in values if (u:=C.valid_unit(value,pool,forecast=forecast))]

def plan_components(plan):
    out=[{'id':key,'content':plan[key]} for key in ('thesis','variant','consensus') if plan.get(key)]
    out += [{'id':'takeaway.'+str(i),'content':x} for i,x in enumerate(plan.get('takeaways',[]))]
    if plan.get('valuation',{}).get('available'):out.append({'id':'valuation','content':plan['valuation']})
    if plan.get('earnings_bridge',{} ) and plan['earnings_bridge'].get('available'):out.append({'id':'earnings_bridge','content':plan['earnings_bridge']})
    out += [{'id':'scenario.'+str(i),'content':x} for i,x in enumerate(plan.get('scenarios',[]))]
    out += [{'id':'risk.'+str(i),'content':x} for i,x in enumerate(plan.get('risks',[]))]
    return out

def check_plan_semantics(plan,opts,ctx,model):
    components=plan_components(plan)
    audit=model('desk_plan_review',C.PLAN_REVIEW,{'request':opts,'components':components,'evidence':ctx},3000)
    decisions={x['id']:x for x in audit.get('decisions',[]) if isinstance(x,dict) and x.get('id')}
    rejected=[x['id']+': '+str(decisions.get(x['id'],{}).get('reason','Missing review decision')) for x in components if decisions.get(x['id'],{}).get('decision')!='keep']
    return audit,rejected

def repair_plan_units(previous,ids,feedback,opts,notes,ctx,model):
    """Regenerate only rejected prose, not the entire otherwise valid plan."""
    previous_units={key:previous['takeaways'][int(key.split('.')[1])] if key.startswith('takeaway.') else previous[key] for key in ids}
    used={r for u in previous_units.values() for r in u.get('evidence_ids',[])}
    missing=set()
    for u in previous_units.values():
        support=' '.join(n['text'] for n in notes if set(n.get('evidence_ids',[])) & set(u.get('evidence_ids',[])))
        missing|=C.number_tokens(u.get('text',''))-C.number_tokens(support)
    candidates=[n for n in notes if C.number_tokens(n['text']) & missing]
    if missing:
        used|={r for n in candidates for r in n['evidence_ids']}
        byid={f['id']:f for f in ctx}
        # Include reference targets needed to resolve deduplicated quotes.
        for _ in range(3):
            used|={f[k] for r in list(used) if (f:=byid.get(r)) for k in ('quote_from','sources_from') if f.get(k)}
        ctx=[f for f in ctx if f['id'] in used]
    raw=model('desk_plan_repair',C.COMMON+' Repair only the specified rejected units. When a number belongs to another supplied observation, cite that observation ID as well. Do not retain a number while citing only an unrelated issuer metric. Preserve source entity, comparison period, BY versus TO, and the investor implication. Return {"corrections":{"exact component ID":unit}} with precisely one object member for every repair_ids entry.',
              {'topic':opts['query'],'as_of':opts['as_of'],'repair_ids':ids,'validation_feedback':feedback,'previous_units':previous_units,'numeric_citation_candidates':candidates,'evidence':ctx},2200)
    patches=raw.get('corrections',{})
    if not isinstance(patches,dict) or set(patches)!=set(ids):raise ValueError('Missing or unexpected targeted plan correction')
    corrected=json.loads(json.dumps(previous))
    for key,replacement in patches.items():
        if key.startswith('takeaway.'):corrected['takeaways'][int(key.split('.')[1])]=replacement
        else:corrected[key]=replacement
    return corrected

def make_plan(record,store,model,progress):
    d=record['payload'];opts=d['options'];record=save(store,record,state='collecting')
    # A recovered job resumes from its last durable evidence checkpoint.
    # Full re-research clears the pack in advance(); new approval is still required.
    reuse=bool(d.pop('reuse_evidence',False) or d.get('pack')) and bool((d.get('pack') or {}).get('evidence'))
    pack=d['pack'] if reuse else E.collect(store,opts,model,progress);d['pack']=pack;pool=pack['evidence']
    for key in ('Q_VALUATION','Q_RISKS','Q_EARNINGS','Q_SCENARIOS'):pool.pop(key,None)
    if not pool:
        d['progress']='Data not available: add dated primary sources.'
        return save(store,record,state='needs_sources')
    changed=E.add_source_context(pack)
    for fact in pool.values():
        fact['source_publication_dates']=list(dict.fromkeys(pack['sources'][sid]['published'] for sid in fact.get('source_ids',[]) if sid in pack['sources'] and pack['sources'][sid].get('published')))
    save(store,record)
    ctx=E.context(pack,opts['query'])
    visible={f['id'] for f in ctx}
    required=[fid for fid in E.required_metric_ids(pack,opts['query']) if fid in visible]
    raw=d.get('draft_notes') if reuse and not changed and d.get('draft_notes_version')==3 else None
    if not raw:
        selection=[{'id':f['id'],'text':pool[f['id']]['text'],'sources':[{k:pack['sources'][sid].get(k) for k in ('publisher','published','page')} for sid in f.get('source_ids',[]) if sid in pack['sources']]} for f in ctx]
        selected=model('desk_notes',C.SELECT_NOTES,{'request':opts,'evidence':selection,'required_evidence_ids':required},650)
        visible={f['id'] for f in ctx};ids=list(dict.fromkeys(selected.get('evidence_ids',[])))
        raw={'notes':[{'text':pool[fid]['text'],'kind':'Fact','evidence_ids':[fid],'method':''} for fid in ids if fid in visible],'missing_data':[]}
    existing={fid for note in raw.get('notes',[]) for fid in note.get('evidence_ids',[])}
    missing_required=[{'text':pool[fid]['text'],'kind':'Fact','evidence_ids':[fid],'method':''} for fid in required if fid not in existing]
    raw={**raw,'notes':(missing_required+raw.get('notes',[]))[:15]}
    d['draft_notes']=raw;d['draft_notes_version']=3;save(store,record)
    draft_notes=[{'id':'note.'+str(i),'content':n} for i,n in enumerate(raw.get('notes',[]))]
    used={r for n in raw.get('notes',[]) for r in n.get('evidence_ids',[]) if r in pool}
    ctx=E.context({**pack,'evidence':{r:pool[r] for r in used}},opts['query'])
    if used-{f['id'] for f in ctx}:raise ValueError('Selected notes exceed source-review context; reduce source passages before reviewing.')
    review_input={'request':opts,'draft_notes':draft_notes,'evidence':ctx}
    review_key=C.digest({'input':review_input,'contract':C.REVIEW_NOTES})
    checked=d.get('notes_audit') if d.get('notes_review_key')==review_key else None
    if not checked:
        checked=model('desk_notes_review',C.REVIEW_NOTES,review_input,2500)
        d['notes_review_key']=review_key
    decisions=checked.get('decisions',{})
    # Legacy checkpoints are read only after a matching contract digest.
    if isinstance(decisions,list):decisions={x.get('id'):x for x in decisions if isinstance(x,dict)}
    audited=[]
    for note in draft_notes:
        choice=decisions.get(note['id'],{})
        if choice.get('action')=='keep':audited.append(note['content'])
    d['notes_audit']=checked
    raw={'notes':audited,'missing_data':raw.get('missing_data',[])+checked.get('missing_data',[])}
    notes=units(raw.get('notes',[]),pool)
    notes=[n for n in notes if n['kind']=='Fact'][:15]
    # Repetition is not evidence coverage.
    seen=set();d['notes']=[]
    for n in notes:
        k=re.sub(r'\W','',n['text'].lower())
        if k not in seen:seen.add(k);d['notes'].append(n)
    pack['gaps']+=raw.get('missing_data',[])[:10]
    if len(d['notes'])<10:
        d['progress']=f'Only {len(d["notes"])} supported research notes; more dated sources required.'
        return save(store,record,state='needs_sources')
    save(store,record)
    # Only reviewed, selected evidence goes to synthesis; unrelated or rejected
    # raw extraction cannot reintroduce errors which the notes review corrected.
    used={r for n in d['notes'] for r in n['evidence_ids']}
    selected_pack={**pack,'evidence':{r:pool[r] for r in used}}
    ctx=E.context(selected_pack,opts['query'])
    progress('M6 · 핵심 논지·컨센서스 차이·목차')
    def validate_plan(plan):
        for key in ('thesis','variant'):
            value=plan.get(key);clean=C.valid_unit(value,pool,forecast=True)
            if not clean:raise ValueError('Invalid '+key+': '+C.unit_error(value,pool))
            plan[key]=clean
        plan['consensus']=C.valid_unit(plan.get('consensus'),pool)
        takeaways=[];errors=[]
        for i,value in enumerate(plan.get('takeaways',[])[:5]):
            clean=C.valid_unit(value,pool,forecast=True)
            if not clean:errors.append('takeaway '+str(i+1)+': '+C.unit_error(value,pool))
            elif not C.number_tokens(clean['text']):errors.append('takeaway '+str(i+1)+': missing a numerical observation')
            else:takeaways.append(clean)
        if errors or len(takeaways)<3:raise ValueError('Need 3–5 supported numerical takeaways with investor implications. '+'; '.join(errors))
        plan['takeaways']=takeaways
        outline=plan.get('outline',[])
        if not isinstance(outline,list) or not 2<=len(outline)<=4 or any(not isinstance(x,dict) or not x.get('title') or not x.get('question') for x in outline):
            raise ValueError('Need two to four distinct core-analysis sections.')
        try:plan['valuation']=V.build(plan.get('valuation',{}),pool)
        except ValueError as error:plan['valuation']={'available':False,'reason':str(error)};pack['gaps'].append('Valuation: '+str(error))
        scenarios=[]
        for item in plan.get('scenarios',[])[:3]:
            if not isinstance(item,dict):continue
            p=item.get('probability');trigger=C.valid_unit(item.get('trigger'),pool,forecast=True);outcome=C.valid_unit(item.get('outcome'),pool,forecast=True)
            if item.get('name') not in ('Bull','Base','Bear') or type(p) not in (int,float) or not 0<=p<=100 or not item.get('method') or not trigger or not outcome:continue
            scenarios.append({**item,'trigger':trigger,'outcome':outcome,'basis':'Estimate'})
        if len(scenarios)!=3 or {x['name'] for x in scenarios}!={'Bull','Base','Bear'} or abs(sum(x['probability'] for x in scenarios)-100)>1e-8:
            scenarios=[];pack['gaps'].append('Data not available: defensible Bull/Base/Bear probability set totalling 100%.')
        plan['scenarios']=scenarios
        if scenarios:
            pool['Q_SCENARIOS']={'id':'Q_SCENARIOS','text':json.dumps(scenarios,ensure_ascii=False),'quote':'','basis':'Estimate',
                                 'method':'Explicit analyst subjective scenario weights summing to 100%; not empirically calibrated probabilities.',
                                 'source_ids':list(dict.fromkeys(s for x in scenarios for r in x['trigger']['evidence_ids'] for s in pool[r].get('source_ids',[])))}
        plan['missing_data']=list(dict.fromkeys(str(x) for x in plan.get('missing_data',[]) if isinstance(x,str)))[:20]
        if not plan['consensus']:plan['missing_data'].append('Data not available: dated consensus expectations; the house thesis is not a measured consensus divergence.')
        plan['risks']=V.build_risks(plan.get('risks',[]),pool)
        if not plan['risks']:plan['missing_data'].append('Data not available: defensible probabilities and impact ranking for the top thesis risks.')
        try:plan['earnings_bridge']=V.build_earnings(plan.get('earnings_bridge') or {},pool,opts['as_of']) if opts['focus']=='company' else None
        except ValueError as error:plan['earnings_bridge']={'available':False,'reason':str(error)}
        if opts['focus']=='company' and not plan['earnings_bridge']['available']:plan['missing_data'].append(plan['earnings_bridge']['reason'])
        return plan
    feedback=None;previous_plan=None;repair_ids=[];resumed_plan=d.pop('resume_candidate',None)
    for attempt in range(2):
        brief=' For this Spot Comment use exactly two outline sections, three takeaways and three risks at most. Keep each unit to one concise sentence and each method to one concise sentence. Do not expand the topic to unrelated macro indicators. Do not restate source passages. Empty unavailable scenario/valuation fields are preferable to invented assumptions.' if opts['report_type']=='Spot Comment' else ''
        plan=resumed_plan if not attempt and resumed_plan else repair_plan_units(previous_plan,repair_ids,feedback,opts,d['notes'],ctx,model) if attempt and repair_ids else model('desk_plan',C.PLAN+'\n'+C.FOCUS_RULES[opts['focus']]+brief,{'request':opts,'research_notes':d['notes'],'evidence':ctx,'validation_feedback':feedback,'previous_plan':previous_plan},5500)
        d.setdefault('plan_attempts',[]).append({'revision':record['revision'],'raw':json.loads(json.dumps(plan))})
        try:
            plan=validate_plan(plan)
            progress('M6 · 지표 의미·인과관계·추정 가정 검수')
            audit,rejected=check_plan_semantics(plan,opts,ctx,model)
            d.setdefault('plan_reviews',[]).append({'revision':record['revision'],**audit})
            if rejected:
                rejected_ids=[x['id'] for x in audit.get('decisions',[]) if x.get('decision')!='keep']
                if all(re.fullmatch(r'thesis|variant|consensus|takeaway\.\d+',x) for x in rejected_ids):repair_ids=rejected_ids
                raise ValueError('Source-meaning review rejected these components: '+'; '.join(rejected))
            break
        except (ValueError,TypeError,KeyError) as error:
            if attempt:
                d['error']=str(error)[:900];d['progress']='The proposed thesis or assumptions did not pass source review; more evidence or a revised topic is required.'
                pack['gaps'].append(str(error)[:1800]);d['plan']=None
                return save(store,record,state='needs_sources')
            feedback=str(error)
            previous_plan=d['plan_attempts'][-1]['raw']
            if not repair_ids:
                repair_ids=[key for key in ('thesis','variant') if not C.valid_unit(previous_plan.get(key),pool,forecast=True)]
                repair_ids += ['takeaway.'+str(i) for i,u in enumerate(previous_plan.get('takeaways',[])) if not C.valid_unit(u,pool,forecast=True) or not C.number_tokens(u.get('text',''))]
            progress('M6 · 논지의 근거·형식 오류 수정')
    d['plan']=plan;d['progress']='Stage 1 and 2 complete. Waiting for your approval.'
    return save(store,record,state='awaiting_approval')

def outline(plan):
    return [{'key':'call','title':'The Call'},{'key':'background','title':'Background'}]+[
        {'key':'core_'+str(i),'title':x['title'],'question':x['question']} for i,x in enumerate(plan['outline'])]+[
        {'key':'consensus','title':'Consensus vs Our View'},{'key':'valuation','title':'Valuation'},
        {'key':'scenarios','title':'Scenario Analysis'},{'key':'risks','title':'Risks'},
        {'key':'monitoring','title':'Monitoring Checklist'}]

def clean_section(value,pool,key):
    if not isinstance(value,dict) or value.get('key')!=key:raise ValueError('Draft section key mismatch')
    conclusion=C.valid_unit(value.get('conclusion'),pool,forecast=True)
    paragraphs=units(value.get('paragraphs',[]),pool,forecast=True)
    tables=[]
    for table in value.get('tables',[])[:2]:
        if not isinstance(table,dict) or not 2<=len(table.get('columns',[]))<=6:continue
        rows=table.get('rows',[]);refs=table.get('evidence_ids',[])
        if not rows or len(rows)>15 or any(not isinstance(row,list) or len(row)!=len(table['columns']) for row in rows):continue
        probe={'kind':table.get('basis','Interpretation'),'method':table.get('method',''),'text':' '.join(str(v) for row in rows for v in row)+' '+str(table.get('note','')),'evidence_ids':refs}
        if not C.valid_unit(probe,pool,forecast=True):continue
        tables.append(table)
    if not conclusion or not paragraphs:raise ValueError('Draft lacks supported analysis: '+key)
    result={**value,'conclusion':conclusion,'paragraphs':paragraphs,'tables':tables}
    for i,u in enumerate([conclusion]+paragraphs):u['id']=key+'.'+str(i)
    return result

def draft(record,store,model,progress):
    d=record['payload'];plan=d['plan'];pack=d['pack'];approval=d.get('approval')
    if not approval or approval['plan_hash']!=C.digest({'plan':plan,'pack':pack}):raise ValueError('The current evidence and plan have not been approved.')
    wanted=outline(plan);done={x['key'] for x in d['sections']};pending=[x for x in wanted if x['key'] not in done]
    deep=d['options']['report_type']=='Sector Deep Dive';limit=2
    for descriptor in pending[:limit]:
        progress('본문 작성 · '+descriptor['title'])
        raw=model('desk_draft',C.DRAFT+'\n'+C.FOCUS_RULES[d['options']['focus']],
                  {'request':d['options'],'approved_plan':plan,'requested_sections':[descriptor],
                   'evidence':E.context(pack,d['options']['query']), 'prior_conclusions':[s['conclusion'] for s in d['sections']]},
                  4000 if deep and descriptor['key'].startswith('core') else 2500)
        value=next((x for x in raw.get('sections',[]) if x.get('key')==descriptor['key']),None)
        try:
            section=clean_section(value,pack['evidence'],descriptor['key'])
            if deep and descriptor['key'].startswith('core') and sum(len(u['text'].split()) for u in section['paragraphs'])<500:raise ValueError('Deep-dive core section needs at least 500 evidence-backed words with causal mechanism and investor implications.')
            if descriptor['key']=='background' and len(section['paragraphs'])>2:raise ValueError('Background must contain at most two paragraphs.')
        except ValueError as error:
            raw=model('desk_draft',C.DRAFT+' Repair the section using this exact validation failure: '+str(error),
                {'request':d['options'],'approved_plan':plan,'requested_sections':[descriptor],'evidence':E.context(pack,d['options']['query']),'rejected_draft':value},5500 if deep else 2500)
            section=clean_section(next((x for x in raw.get('sections',[]) if x.get('key')==descriptor['key']),None),pack['evidence'],descriptor['key'])
            if deep and descriptor['key'].startswith('core') and sum(len(u['text'].split()) for u in section['paragraphs'])<500:raise ValueError('Evidence-backed deep-dive depth remains insufficient. Add source material.')
        d['sections'].append(section)
        record=save(store,record,state='drafting')
    if len(d['sections'])<len(wanted):
        d['progress']='Two sections drafted. Say “리서치 계속 '+record['id'][:8]+'” to continue.' if deep else 'Continuing approved report in bounded batches.'
        return save(store,record,state='awaiting_continue' if deep else 'drafting')
    d['progress']='Full draft ready; numerical and argument review queued.'
    return save(store,record,state='reviewing')

def report_units(d):
    result=[]
    for key in ('thesis','variant','consensus'):
        if d['plan'].get(key):result.append({**d['plan'][key],'id':'plan.'+key})
    result += [{**u,'id':'takeaway.'+str(i)} for i,u in enumerate(d['plan']['takeaways'])]
    for section in d['sections']:
        result.extend([section['conclusion']]+section['paragraphs'])
        for i,t in enumerate(section['tables']):
            result.append({'id':section['key']+'.table.'+str(i),'text':t['title']+'; '+str(t['columns'])+'; '+str(t['rows'])+'; '+t.get('note',''),
                           'kind':t.get('basis','Interpretation'),'method':t.get('method',''),'evidence_ids':t['evidence_ids']})
    v=d['plan']['valuation']
    if v.get('available'):
        for a in v['assumptions']:
            result.append({'id':'valuation.'+a['name'],'text':a['name']+' = '+str(a['value'])+' '+a['unit'],
                           'kind':'Fact' if a['basis']=='Verified' else 'Estimate','method':a['method'],'evidence_ids':a['evidence_ids']})
    for i,x in enumerate(d['plan']['scenarios']):
        result.extend([{**x[k],'id':'scenario.'+str(i)+'.'+k} for k in ('trigger','outcome')])
        result.append({'id':'scenario.'+str(i)+'.weight','text':x['name']+' '+str(x['probability'])+'%',
                       'kind':'Estimate','method':x['method'],'evidence_ids':x['trigger']['evidence_ids']})
    for key in ('Q_RISKS','Q_EARNINGS'):
        if key in d['pack']['evidence']:
            e=d['pack']['evidence'][key]
            result.append({'id':key,'text':e['text'],'kind':'Estimate','method':e['method'],'evidence_ids':e['input_ids']})
    return result

def review(record,store,model,progress):
    d=record['payload'];pool=d['pack']['evidence'];all_units=report_units(d)
    decisions={};weak=[];contradictions=[]
    def assess(batch):
        used={r for u in batch for r in u['evidence_ids']}
        raw=model('desk_review',C.REVIEW,{'thesis':d['plan']['thesis'],'takeaways':d['plan']['takeaways'],
                   'units':batch,'evidence':[pool[k] for k in used], 'approved_valuation':d['plan']['valuation']},3400)
        decisions.update({x['id']:x for x in raw.get('decisions',[]) if isinstance(x,dict) and x.get('id') in {u['id'] for u in batch}})
        return raw
    for i in range(0,len(all_units),10):
        progress(f'M6 · 숫자·논증 검수 {i+1}/{len(all_units)}')
        raw=assess(all_units[i:i+10]);weak.extend(raw.get('weakest_arguments',[])[:3])
    # Rewrites receive a fresh source review. Approved thesis/assumptions are never silently replaced.
    corrections=[];replacements=[];byid={u['id']:u for u in all_units}
    for w in weak:
        if len(corrections)>=3:break
        if not isinstance(w,dict) or w.get('id') not in byid or any(x['unit']==w['id'] for x in corrections):continue
        editable=any(w['id']==u['id'] for sec in d['sections'] for u in [sec['conclusion']]+sec['paragraphs'])
        u=C.valid_unit(w.get('replacement'),pool,forecast=True) if editable else None
        if not u or u['text']==byid[w['id']]['text']:continue
        replacements.append({**u,'id':w['id']+'.rewrite'})
        corrections.append({'unit':w['id'],'issue':str(w.get('problem','')),'original':byid[w['id']]['text'],'correction':u['text']})
    if replacements:
        assess(replacements)
        for u in replacements:
            if decisions.get(u['id'],{}).get('decision')!='keep':continue
            original=u['id'][:-8];byid[original]={**u,'id':original};decisions[original]=decisions[u['id']]
            for sec in d['sections']:
                if sec['conclusion']['id']==original:sec['conclusion']=byid[original]
                sec['paragraphs']=[byid[original] if p['id']==original else p for p in sec['paragraphs']]
        corrections=[c for c in corrections if decisions.get(c['unit']+'.rewrite',{}).get('decision')=='keep']
    all_units=list(byid.values())
    audit=[];kept={}
    for u in all_units:
        decision=decisions.get(u['id'],{'decision':'remove','reason':'No independent review decision returned.'})
        passed=decision.get('decision')=='keep';kept[u['id']]=passed
        for number in sorted(C.number_tokens(u['text'])):
            estimated=u['kind'] in ('Estimate','Forecast') or any(pool[r].get('basis')=='Estimate' for r in u['evidence_ids'])
            audit.append({'unit':u['id'],'number':number,'classification':('Estimate' if estimated else 'Verified') if passed else 'Unsupported',
                          'evidence_ids':u['evidence_ids'],'action':'Retained' if passed else 'Removed / publication blocked','reason':decision.get('reason',''),'method':u.get('method','')})
    for sec in d['sections']:
        sec['paragraphs']=[u for u in sec['paragraphs'] if kept.get(u['id'])]
        if not kept.get(sec['conclusion']['id']):sec['conclusion']=None
        sec['tables']=[t for i,t in enumerate(sec['tables']) if kept.get(sec['key']+'.table.'+str(i))]
    critical_bad=any(not ok for key,ok in kept.items() if key.startswith(('plan.','valuation.','scenario.','Q_RISKS','Q_EARNINGS')))
    enough_takeaways=sum(kept.get('takeaway.'+str(i),False) for i in range(len(d['plan']['takeaways'])))>=3
    prelim=not critical_bad and enough_takeaways and all(sec['conclusion'] and sec['paragraphs'] for sec in d['sections'])
    final={};counter=None
    if prelim:
        final=model('desk_consistency',C.HOLISTIC,{'approved_plan':d['plan'],'final_sections':d['sections'],
                    'evidence':E.context(d['pack'],d['options']['query'])},2600)
        counter=C.valid_unit(final.get('counterargument'),pool,forecast=True)
        if counter:
            counter={**counter,'id':'review.counterargument'};assess([counter])
            if decisions.get(counter['id'],{}).get('decision')!='keep':counter=None
        if counter:
            risk=next((x for x in d['sections'] if x['key']=='risks'),None)
            if risk and not final.get('addressed'):risk['paragraphs'].append(counter)
            audit += [{'unit':counter['id'],'number':n,'classification':'Estimate' if counter['kind'] in ('Estimate','Forecast') else 'Verified','evidence_ids':counter['evidence_ids'],'action':'Retained','reason':'Counterargument separately source-reviewed','method':counter.get('method','')} for n in sorted(C.number_tokens(counter['text']))]
    contradictions=final.get('contradictions',[])
    # Calculated cells and plotted observations are also in the audit, not just prose.
    v=d['plan']['valuation']
    if v.get('available'):
        for label,value in [('base',v['base'])]+[(str(i)+','+str(j),z) for i,row in enumerate(v['rows']) for j,z in enumerate(row) if z is not None]+[('axis_x',x) for x in v['x']]:
            audit.append({'unit':'sensitivity.'+label,'number':str(value),'classification':'Estimate','evidence_ids':v['evidence_ids'],'action':'Recomputed by code','reason':v['formula'],'method':v['sensitivity_method']})
    for i,chart in enumerate(d['pack'].get('charts',[])):
        for row in chart['values']:
            audit.append({'unit':'chart.'+str(i),'number':str(row['value']),'classification':'Verified','evidence_ids':chart['source_ids'],'action':'Stored provider observation','reason':row['date']+' · '+chart['unit']})
    pm=final.get('pm_readable') is True
    d['reviews']=[{'numeric_audit':audit,'weakest_arguments':corrections,'counterargument':counter,
                   'contradictions':contradictions,'pm_readable':pm,'unsupported_removed':sum(a['classification']=='Unsupported' for a in audit)}]
    if not prelim or final.get('consistent') is not True or contradictions or not counter or not pm or len(corrections)<3:
        d['progress']='Review found unresolved evidence/argument gaps; final publication blocked.'
        return save(store,record,state='needs_sources')
    d['plan']['takeaways']=[u for i,u in enumerate(d['plan']['takeaways']) if kept.get('takeaway.'+str(i))]
    d['progress']='Review complete'
    limited=d['plan']['missing_data'] or not v['available'] or any(sec.get('missing_data') for sec in d['sections'])
    return save(store,record,state='limited' if limited else 'complete')

def envelope(record,model):
    from .render import text_report
    d=record['payload'];final=record['state'] in ('complete','limited')
    text=text_report(record)
    return {'id':uuid.uuid5(uuid.NAMESPACE_URL,record['id']+':'+str(record['revision'])+':'+str(len(d['sections']))+':'+record['state']).hex,
            'profile':'market','profile_label':'AIRI / TIM WORKS Research Desk','created':dt.datetime.now(dt.timezone.utc).isoformat(),
            'events':[],'context_events':[],'sources':list((d.get('pack') or {}).get('sources',{}).values()),
            'professional_research':record,'delivery_style':'professional_research','query':d['options']['query'],
            'status':record['state'],'final':final,'model_calls':getattr(model,'calls',[]),'language':'en',
            'spoken_briefing':[u['text'] for u in (d.get('plan') or {}).get('takeaways',[])]},text

def run(store,opts,model,progress):
    record=get(store,opts['_research_id']);d=record['payload']
    if record['state']=='cancelled':raise ValueError('Research cancelled.')
    stage=opts['_research_stage']
    # A recovered completed queue item must not redo an approved plan or a continued batch.
    completed = (stage=='plan' and record['state'] not in ('queued','collecting','failed')) or (stage=='draft' and int(opts.get('_research_batch',0))<len(d['sections']) and record['state'] in ('awaiting_continue','reviewing','complete','limited')) or (stage=='review' and record['state'] in ('complete','limited','needs_sources'))
    if completed:
        report,text=envelope(record,model);store.save_report(report,text);return report,text
    previous_calls=list(d.get('model_calls',[]))
    def update(message):
        d['progress']=message;d['model_calls']=previous_calls+getattr(model,'calls',[]);save(store,get(store,record['id']),payload=d);progress(message)
    try:
        stage=opts['_research_stage']
        if stage=='plan':record=make_plan(record,store,model,update)
        elif stage=='draft':record=draft(record,store,model,update)
        elif stage=='review':record=review(save(store,record,state='reviewing'),store,model,update)
        else:raise ValueError('Unknown research stage')
    except Exception as error:
        if get(store,record['id'])['state']!='cancelled':
            d['error']=type(error).__name__+': '+str(error)[:350];d['progress']='Research requires attention'
            d['model_calls']=previous_calls+getattr(model,'calls',[])
            save(store,record,state='failed')
        raise
    record['payload']['model_calls']=previous_calls+getattr(model,'calls',[]);record=save(store,record)
    if record['state'] in ('drafting','reviewing'):
        next_stage='review' if record['state']=='reviewing' else 'draft'
        with store.db() as c:
            enqueue(c,record['id'],record['revision'],next_stage,len(record['payload']['sections']),opts,dt.datetime.now(dt.timezone.utc).isoformat())
    report,text=envelope(record,model);store.save_report(report,text);return report,text
