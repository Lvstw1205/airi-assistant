"""Small read-only dashboard snapshots; never start/stop trading on a poll."""
import copy,json,math,sqlite3,subprocess,threading,time
from contextlib import closing
from decimal import Decimal,InvalidOperation
from pathlib import Path
import mac_cluster,mac_dispatch

_lock=threading.RLock();_samples={};_running=set();_attempts={}

def number(value,low=None,high=None):
    if type(value) not in (int,float) or not math.isfinite(value):return None
    if low is not None and value<low or high is not None and value>high:return None
    return value

def validated_metrics(value):
    if not isinstance(value,dict) or value.get('version')!=1:raise ValueError('Unsupported metrics')
    out={'sampled_at':number(value.get('sampled_at'),1),'hardware':str(value.get('hardware','Mac'))[:80]}
    for k in ('cpu','gpu'):
        raw=value.get(k,{})
        if not isinstance(raw,dict):raw={}
        out[k]={'used_percent':number(raw.get('used_percent'),0,100)}
    raw=value.get('ram',{});raw=raw if isinstance(raw,dict) else {}
    used=number(raw.get('used_bytes'),0);total=number(raw.get('total_bytes'),1)
    if total is None or used is None or used>total:used=total=None
    out['ram']={'used_bytes':used,'total_bytes':total,'used_percent':100*used/total if total else None}
    raw=value.get('temperature',{});raw=raw if isinstance(raw,dict) else {}
    out['temperature']={k:number(raw.get(k),0.1,150) for k in ('cpu_c','gpu_c')}
    out['thermal_pressure']=value.get('thermal_pressure') if value.get('thermal_pressure') in ('nominal','fair','serious','critical') else 'unknown'
    return out

def _collect(app,node):
    key=(str(app.DATA),node);result=None;state='unavailable'
    try:
        if node=='M6':
            p=subprocess.run([str(app.ROOT/'scripts/mac-metrics')],capture_output=True,timeout=5,check=True)
            if len(p.stdout)>16000:raise ValueError('Oversized metrics')
            result=validated_metrics(json.loads(p.stdout))
        else:
            current=mac_cluster.status(app)
            if 'hardware_metrics' not in current.get('capabilities',[]):current=mac_cluster.refresh(app)
            if not current.get('connected'):state='offline'
            elif 'hardware_metrics' not in current.get('capabilities',[]):state='setup_required'
            else:
                r=mac_dispatch.exchange(mac_cluster.command(app),{'version':1,'action':'metrics'},8)
                result=validated_metrics(r.get('metrics'))
        if result:state='ready'
    except (ValueError,OSError,subprocess.SubprocessError):state='unavailable'
    finally:
        with _lock:
            previous=_samples.get(key,{})
            _samples[key]={**(result or previous),'node':node,'state':state,
                           'received_at':time.time() if result else previous.get('received_at'),
                           'checked_at':time.time()}
            _running.discard(key)

def mac_snapshot(app):
    now=time.time();nodes=[]
    for node in ('M6','M1'):
        key=(str(app.DATA),node)
        with _lock:
            previous=_samples.get(key,{})
            interval=30 if previous.get('state')=='setup_required' else 10
            if time.monotonic()-_attempts.get(key,0)>=interval and key not in _running:
                _attempts[key]=time.monotonic();_running.add(key)
                threading.Thread(target=_collect,args=(app,node),daemon=True,name='airi-metrics-'+node).start()
            item=copy.deepcopy(_samples.get(key,{'node':node,'state':'loading'}))
        item['age_seconds']=max(0,now-item['received_at']) if item.get('received_at') else None
        item['stale']=item['state']!='ready' or item['age_seconds'] is None or item['age_seconds']>30
        nodes.append(item)
    return {'nodes':nodes,'worker':mac_cluster.status(app),'refresh_seconds':10,'checked_at':now,
            'source_note':'CPU는 전체 코어 평균, RAM은 파일 캐시를 제외한 사용량. 온도는 AppleSMC CPU·GPU 계열 센서 평균이며 macmon의 센서 분류를 사용해.'}

def _settings(c):return {r['key']:json.loads(r['value']) for r in c.execute("SELECT key,value FROM settings WHERE key IN ('multi_running','paper_resume_requested','halted','halt_reason','live_running','live_reason','live_config','performance_bonus_realized_v2')")}

def _snapshot(c,live):
    fields=('equity_cad','cap_cad','pnl_cad','realized_cad') if live else ('equity','initial','realized','unrealized')
    columns=','.join("json_extract(payload,'$."+k+"') AS "+k for k in fields)
    where='' if live else "WHERE json_extract(payload,'$.currency')='CAD'"
    row=c.execute('SELECT created,'+columns+' FROM portfolio_snapshots '+where+' ORDER BY created DESC LIMIT 1').fetchone()
    return dict(row) if row else None

def _decimal(value):
    try:
        n=Decimal(str(value));return n if n.is_finite() else None
    except (InvalidOperation,ValueError):return None

def _money(snapshot,live):
    if not snapshot:return {'equity_cad':None,'pnl_cad':None,'realized_cad':None,'pnl_percent':None,'as_of':None}
    equity=_decimal(snapshot.get('equity_cad' if live else 'equity'))
    basis=_decimal(snapshot.get('cap_cad' if live else 'initial'))
    pnl=_decimal(snapshot.get('pnl_cad')) if live else equity-basis if equity is not None and basis is not None else None
    realized=_decimal(snapshot.get('realized_cad' if live else 'realized'))
    return {'equity_cad':str(equity) if equity is not None else None,'pnl_cad':str(pnl) if pnl is not None else None,
            'realized_cad':str(realized) if realized is not None else None,
            'pnl_percent':str(pnl/basis*100) if pnl is not None and basis and basis>0 else None,'as_of':snapshot['created']}

def trading_node(app,live=False):
    from stock101.crypto import service
    key=str(app.DATA);instance=(service._live_instances if live else service._instances).get(key)
    path=app.DATA/'stock101-coinbase'/('live.sqlite3' if live else 'cad-plan.sqlite3')
    result={'mode':'live' if live else 'paper','available':False,'running':False,'enabled':False,'state':'unavailable','money':_money(None,live),'reason':None,'last_product':None,'last_assessment_at':None,'configured':False}
    if not path.is_file():return {**result,'state':'not_configured'}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.3)) as c:
            c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');cfg=_settings(c)
            result['money']=_money(_snapshot(c,live),live)
            last=c.execute("SELECT created,json_extract(payload,'$.product') AS product FROM trade_decisions ORDER BY created DESC LIMIT 1").fetchone()
            if last:result.update(last_product=last['product'],last_assessment_at=last['created'])
            if live:
                running=bool(instance and cfg.get('live_running') and not instance.stop_event.is_set())
                result.update(running=running,enabled=running,reason=cfg.get('live_reason'),configured=bool(cfg.get('live_config')))
                result['risk_limits']=(cfg.get('live_config') or {}).get('risk_limits',{})
                result['quote']=(cfg.get('live_config') or {}).get('quote')
                result['fill_count']=c.execute('SELECT COUNT(*) FROM fills').fetchone()[0]
            else:
                running=bool(instance and cfg.get('multi_running') and not cfg.get('halted') and not instance._fatal and not instance._paper_stop.is_set())
                result.update(running=running,enabled=running or cfg.get('paper_resume_requested') is True,reason=cfg.get('halt_reason'),configured=True)
                result['recovery_state']=getattr(instance,'recovery',{}).get('status') if instance else None
            result.update(available=True,state='running' if result['running'] else 'recovering' if result['enabled'] else 'stopped')
            # Display recorded limits only; never call a valuation, readiness or trading cycle.
            if live:
                from stock101.crypto.budget_policy import INITIAL_CAD,BONUS_CAD
                result['budget_cap_cad']=str(INITIAL_CAD+(BONUS_CAD if cfg.get('performance_bonus_realized_v2') else Decimal(0)))
    except (sqlite3.Error,OSError,ValueError,KeyError,TypeError):return result
    return result

def stock_snapshot(app):
    return {'paper':trading_node(app),'live':trading_node(app,True),'checked_at':time.time(),
            'refresh_seconds':10,'source_note':'기존 장부의 최근 평가값. 실시간 재평가나 주문은 위젯 조회로 실행하지 않아.'}
