"""Keep tool observations separate from the department model's interpretation."""
import json,math
from datetime import datetime,timezone

def iso(value):
    return datetime.fromtimestamp(value,timezone.utc).isoformat() if isinstance(value,(int,float)) else value

def result(agent,data,task_id,fetched):
    sources=[];claims=[]
    def add(text,label,as_of=None,url=None,stale=False):
        sid=task_id+':'+str(len(claims))
        sources.append({'id':sid,'url_or_path':url or 'tool:'+task_id,'retrieved_at':iso(fetched)})
        claims.append({'text':text,'label':label,'source_ids':[sid],'as_of':iso(as_of),'stale':stale})
    if agent=='finance':
        price=data.get('price');stamp=data.get('as_of');stale=data.get('stale') is True
        if type(price) in (int,float) and math.isfinite(price) and stamp:
            text=f"[관측] {data.get('symbol','종목')}의 기록된 가격은 {price:,.2f} {data.get('currency','')}이야. 시세 시각은 {stamp}야."
            change=data.get('regularMarketChangePercent')
            if type(change) in (int,float) and math.isfinite(change):text+=f' 전 거래일 대비 변화는 {change:+.2f}%야.'
            text+=' 오래된 지연 시세여서 현재 체결 가격으로 사용할 수 없어.' if stale else '지연될 수 있는 시세이며 실시간 체결 가격은 보장되지 않아.'
            add(text,'OBSERVED',stamp,data.get('source_url'),stale)
        else:add('[미확인] 시각이 있는 시세를 받지 못했어.','UNKNOWN')
    elif agent=='news':
        for item in data.get('results',[])[:5]:
            title=str(item.get('title',''))[:300]
            if not title:continue
            add('[검색 결과 · 본문 미확인] '+title+' — 발행일과 사건 발생 시점은 확인하지 못했어.','RETRIEVED',data.get('fetched_at') or fetched,item.get('url'))
        add('[한계] 검색 제목·요약만 수집했어. 이를 오늘 발생한 사건이나 주가 변동 원인으로 확정하지 않아.','UNKNOWN')
    elif agent=='stock101':
        stamp=data.get('as_of');source=data.get('source_url')
        change=data.get('daily_change')
        if type(change) in (int,float) and math.isfinite(change):
            add(f"[계산] Stock101의 완료된 일봉 간 종가 변화는 {change:+.2f}%야. 자료 기준일은 {stamp or '미확인'}이야.",'CALCULATED',stamp,source)
        add('[한계] 과거 일봉 지표는 최신 뉴스의 원인이나 이후 수익을 검증하지 않아.','UNKNOWN')
    elif agent=='memory_manager':
        count=len(data.get('memories',[]));add(f'[조회] 현재 종목과 관련된 저장 기억 {count}건을 찾았어.','RETRIEVED',fetched)
    elif agent=='secretary':
        add('[조회] 저장 일정: '+json.dumps(data,ensure_ascii=False)[:3000],'RETRIEVED',fetched)
    else:return None
    return {'summary':'\n\n'.join(c['text'] for c in claims),'claims':claims,'sources':sources,
            'evidence':data,'agent_id':agent,'node_actual':'prime','verified_facts':False}
