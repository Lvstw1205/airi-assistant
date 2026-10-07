"""Read-only, bounded projection of the existing AIRI Studio company and workers."""
import copy,json,threading,time
from concurrent.futures import ThreadPoolExecutor
from airi_core.execution.permissions import redact

MAPPING={('m1','health'):'secretary',('m6','health'):'research',
         ('m1','write'):'writer',('m6','write'):'youtube',
         ('m1','summarize'):'business',('m6','summarize'):'instagram',('m1','atlas'):'business'}

def build_snapshot(company,state,now):
    if company.get('version','').startswith('2.0') and 'staff' in company:
        staff=[]
        for s in company['staff']:
            t=next((t for t in company.get('tasks',[]) if t['id']==s.get('current_task')),None)
            phase={'working':'working','reviewing':'working','queued':'queued','offline':'offline','rest':'idle'}.get(s['work_state'],'idle')
            if not s.get('online'):phase='offline'
            staff.append({'id':s['slot_id'],'name':s['name'],'role':s['role'],'node':s['node'],'state':phase,'department':s['department'],
                'current_task':{'id':t['id'],'title':t['goal'],'status':t['state']} if t else None,'last_task':None})
        return {'name':'AIRI Studio','available':True,'stale':False,'as_of':now,'automatic_enabled':company['settings']['autonomy'] and not company['settings']['paused'],'nodes':company['nodes'],'staff':staff,
            'counts':{key:sum(s['state']==key for s in staff) for key in ('working','queued','idle','offline')},
            'active_missions':[{'id':t['id'],'goal':t['goal'],'status':t['state']} for t in company.get('tasks',[]) if t['state'] in ('working','queued','reviewing')],
            'source':'AIRIStudio v2 persistent organization; actual task state', 'organization_version':company['version']}

    nodes={n['id']:{'id':n['id'],'online':n.get('online') is True and 0<=now-n.get('seen',0)<15,
                        'seen':n.get('seen')} for n in state.get('nodes',[])}
    jobs={j['id']:dict(j) for j in state.get('jobs',[])}
    for mission in company.get('missions',[])[:40]:
        for task in mission.get('tasks',[]):
            job=jobs.setdefault(task['job'],{'id':task['job'],'target':task.get('node'),'kind':'team_work',
                'status':task.get('status'),'created':mission.get('created'),'finished':mission.get('finished'),
                'result':task.get('output',''),'error':mission.get('error','') if task.get('status')!='completed' else ''})
            job.update(role=task.get('role'),title=task.get('task'),goal=mission.get('goal'))
    assigned={}
    for job in jobs.values():
        role=job.get('role') or MAPPING.get((job.get('target'),job.get('kind')))
        payload={}
        if job.get('kind','').startswith('team_'):
            try:payload=json.loads(job.get('instruction','{}'))
            except (ValueError,TypeError):pass
            if not isinstance(payload,dict):payload={}
            role=role or payload.get('role')
        if not role:continue
        title=job.get('title') or payload.get('task') or payload.get('goal') or job.get('instruction') or '작업 기록'
        item={'id':job['id'],'role_id':role,'node':job.get('target'),'kind':job.get('kind'),
              'title':redact(str(title))[:500],'status':job.get('status'),
              'created':job.get('created') or 0,'started':job.get('started'),'finished':job.get('finished'),
              'result':redact(str(job.get('result') or ''))[:2400],
              'error':redact(str(job.get('error') or ''))[:600]}
        assigned.setdefault(role,[]).append(item)
    staff=[]
    for role in company.get('roles',[]):
        records=sorted(assigned.get(role['id'],[]),key=lambda j:j['created'],reverse=True)
        active=next((j for j in records if j['status']=='running'),None)
        queued=next((j for j in records if j['status']=='queued'),None)
        online=nodes.get(role['node'],{}).get('online') is True
        current='offline' if not online else 'working' if active else 'queued' if queued else 'idle'
        staff.append({'id':role['id'],'name':role['name'],'role':role['role'],'node':role['node'],
                      'state':current,'current_task':active or queued,'last_task':records[0] if records else None})
    return {'name':company.get('settings',{}).get('name') or 'TIM WORKS','available':True,'stale':False,
            'as_of':now,'automatic_enabled':company.get('settings',{}).get('enabled') is True,
            'nodes':list(nodes.values()),'staff':staff,
            'counts':{key:sum(s['state']==key for s in staff) for key in ('working','queued','idle','offline')},
            'active_missions':[{'id':m['id'],'goal':redact(str(m.get('goal','')))[:500],'status':m['status']}
                               for m in company.get('missions',[]) if m.get('status') in ('planning','working','reviewing')],
            'source':'AIRI Studio company + M6 coordinator; no task execution from this widget'}

class SnapshotCache:
    def __init__(self):self.lock=threading.Lock();self.data=None;self.inflight=False;self.last_attempt=0;self.error=None
    def refresh(self):
        try:
            import airi_office_bridge as bridge
            with ThreadPoolExecutor(max_workers=2) as pool:
                company=pool.submit(bridge.company_call,'status',{});state=pool.submit(bridge.status)
                result=build_snapshot(company.result(),state.result(),time.time())
            with self.lock:self.data=result;self.error=None
        except Exception:
            with self.lock:self.error='AIRI Studio 연결을 확인하지 못했어.'
        finally:
            with self.lock:self.inflight=False
    def get(self):
        now=time.time()
        with self.lock:
            if not self.inflight and now-self.last_attempt>=5:
                self.inflight=True;self.last_attempt=now;threading.Thread(target=self.refresh,daemon=True).start()
            data=copy.deepcopy(self.data)
            error=self.error
        if data is None:return {'name':'TIM WORKS','available':False,'stale':True,'loading':not error,'error':error,'staff':[],'counts':{}}
        if error or now-data['as_of']>15:
            data.update(stale=True,error=error or '마지막 상태가 15초 이상 지났어.')
            for staff in data['staff']:staff['state']='unknown'
            data['counts']={key:None for key in ('working','queued','idle','offline')}
        return data

cache=SnapshotCache()
