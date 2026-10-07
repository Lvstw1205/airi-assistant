"""One durable daily economic-news subscription per paired Telegram owner."""
import datetime as dt
import re
import secrets
import threading
import news_sources

LOCK=threading.RLock()

def init(app):
    with app.db() as c:c.execute('CREATE TABLE IF NOT EXISTS telegram_news(id INTEGER PRIMARY KEY CHECK(id=1),generation TEXT,clock TEXT,enabled INTEGER,next_run TEXT,last_status TEXT,revision TEXT)')

def public(app):
    cfg=app.telegram_bridge.config(app)
    rows=app.rows('SELECT clock,enabled,next_run,last_status FROM telegram_news WHERE generation=?',(cfg.get('generation',''),))
    return rows[0] if rows else None

def next_run(app,clock,current=None):
    current=(current or dt.datetime.now(app.schedule_features.ZONE)).astimezone(app.schedule_features.ZONE)
    hour,minute=map(int,clock.split(':'))
    value=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if value<=current:value+=dt.timedelta(days=1)
    # Normalize nonexistent local times forward during the spring DST transition.
    return value.astimezone(dt.timezone.utc).astimezone(app.schedule_features.ZONE).isoformat()

def configure(app,body):
    clock=body.get('clock','06:00');enabled=body.get('enabled',True)
    if not isinstance(clock,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',clock) or type(enabled) is not bool:raise ValueError('알림 시간은 HH:MM 형식으로 입력하세요.')
    cfg=app.telegram_bridge.config(app)
    if not cfg.get('enabled') or not cfg.get('user_id'):raise ValueError('먼저 Telegram 본인 계정을 연결하세요.')
    with LOCK,app.db() as c:
        old=c.execute('SELECT * FROM telegram_news WHERE id=1').fetchone()
        if old and old['generation']==cfg['generation'] and old['clock']==clock and bool(old['enabled'])==enabled:return public(app)
        c.execute('INSERT OR REPLACE INTO telegram_news VALUES(1,?,?,?,?,?,?)',(cfg['generation'],clock,int(enabled),next_run(app,clock),'예약됨' if enabled else '중지됨',secrets.token_hex(8)))
    app.event('saved','Telegram 경제 뉴스 · 매일 '+clock+' · '+('켜짐' if enabled else '꺼짐'))
    return public(app)

def chat_request(app,text,destination="web"):
    import intelligence
    brief=intelligence.chat_request(app,text,destination)
    if brief:return brief
    if not re.search(r'뉴스|\bnews\b',text,re.I):return None
    recurring=bool(re.search(r'매일|마다|매\s*아침|daily|every\s+(?:day|morning)',text,re.I))
    if not recurring:return None
    if re.search(r'예를|예시|번역|어떻게|방법|\b(example|translate|how)\b|["“「]',text,re.I):return None
    if re.search(r'중지|취소|그만|보내지\s*마|\b(stop|cancel|disable)\b',text,re.I):
        old=public(app)
        if not old:return {'text':'등록된 매일 경제 뉴스 발송이 없어.'}
        configure(app,{'clock':old['clock'],'enabled':False});return {'text':'매일 경제 뉴스 발송을 중지했어.'}
    if not re.search(r'보내|전송|발송|알려|예약|등록|\b(send|schedule|deliver)\b',text,re.I):return None
    if not re.search(r'경제|금융|비즈니스|business|econom|financ',text,re.I):return {'text':'지금 매일 자동 발송은 캐나다·미국 경제 뉴스를 지원해. 원하는 시간을 알려줘.'}
    match=re.search(r'(오전|오후|아침|저녁|밤)?\s*(\d{1,2})\s*(?:시|:)(?:\s*(\d{1,2})\s*분?)?',text)
    english=re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',text,re.I)
    if english:hour=int(english[1])%12+(12 if english[3].lower()=='pm' else 0);minute=int(english[2] or 0)
    elif match:
        hour=int(match[2]);minute=int(match[3] or 0);period=match[1] or ('아침' if '아침' in text else '')
        if not period and hour<13:return {'text':'오전인지 오후인지 알려줘. 예: 매일 오전 6시 경제 뉴스 보내줘.'}
        if period in ('오후','저녁','밤') and hour<12:hour+=12
        if period in ('오전','아침') and hour==12:hour=0
    else:return {'text':'매일 보낼 시간을 알려줘. 예: 매일 오전 6시 경제 뉴스 보내줘.'}
    if hour>23 or minute>59:return {'text':'올바른 시간을 알려줘.'}
    value=configure(app,{'clock':f'{hour:02}:{minute:02}','enabled':True})
    return {'text':f"매일 {value['clock']}에 캐나다·미국 경제 뉴스를 Telegram으로 보내도록 저장했어. 설정한 지역 시간 기준이고 다음 발송은 {value['next_run'][:16].replace('T',' ')}이야. Mac이 켜져 있고 잠자기 상태가 아니어야 해."}

def run_due(app,cfg,current=None):
    if not cfg.get('enabled') or not cfg.get('user_id') or not cfg.get('notifications',True):return False
    current=current or dt.datetime.now(app.schedule_features.ZONE)
    with LOCK:
        rows=app.rows('SELECT * FROM telegram_news WHERE id=1 AND enabled=1 AND generation=?',(cfg['generation'],))
        if not rows or dt.datetime.fromisoformat(rows[0]['next_run'])>current:return False
        row=rows[0];key='daily-news:'+row['revision']+':'+row['next_run']
        # The outbox receipt and advancing the schedule commit together, so restart
        # never requeues a day that was already handed off for delivery.
        artifact=None
        try:
            import intelligence
            job=intelligence.request(app,'market',key=key)
            if job['state'] in ('queued','running'):return False
            if job['state']=='failed':raise ValueError(job.get('error'))
            result=intelligence.status(app,job['id']);text=result['text'];artifact=result.get('artifact');status='PDF 발송 대기' if artifact else '발송 대기'
        except Exception:text='User, 오늘 경제 뉴스는 데이터 조회에 실패해 보내지 못했어. 뉴스 화면에서 로컬 모델·본문 수집 상태를 확인해줘.';status='뉴스 조회 실패'
        with app.db() as c:
            c.execute('BEGIN IMMEDIATE')
            latest=app.telegram_bridge.config(app)
            active=c.execute('SELECT * FROM telegram_news WHERE id=1').fetchone()
            if latest.get('generation')!=cfg['generation'] or not latest.get('enabled') or not latest.get('notifications',True) or not active['enabled'] or active['revision']!=row['revision']:return False
            import json,time
            for index,part in enumerate(app.telegram_bridge.chunks(text)):
                payload=json.dumps({'chat_id':cfg['chat_id'],'text':part,**({'analysis_report_id':artifact['id']} if artifact and index==0 else {})})
                c.execute("INSERT OR IGNORE INTO telegram_outbox(generation,key,payload,state,created) VALUES(?,?,?,'pending',?)",(cfg['generation'],key+':'+str(index),payload,time.time()))
            c.execute('UPDATE telegram_news SET next_run=?,last_status=? WHERE id=1',(next_run(app,row['clock'],current),status))
        return True
