"""Matched-date cross-asset directional checks, never causal estimates."""
import hashlib
PAIRS=[('^GSPC','us10y',-1,'미국 주식과 장기 금리','금리 상승은 할인율 부담이 될 수 있지만 성장 기대 개선이 이를 상쇄할 수 있어.'),('^IXIC','us10y',-1,'나스닥과 장기 금리','성장 기대가 큰 기업의 가격은 할인율과 실적 전망을 함께 봐야 해.'),('^GSPTSE','CL=F',1,'캐나다 주식과 원유','원유 가격은 에너지 기업 매출과 관련될 수 있지만 전체 지수의 업종 비중과 비용 효과는 달라.'),('USD/CAD','CL=F',-1,'캐나다 달러와 원유','캐나다 달러 강세는 미국 달러 대비 환율 하락이야. 원유 외에 금리 차이·위험 선호도 영향을 줄 수 있어.'),('GC=F','us10y',-1,'금과 명목 장기 금리','금리 상승은 금 보유의 기회비용을 높일 수 있어. 실질금리·달러·위험 회피 자료가 추가로 필요해.'),('HG=F','^GSPC',1,'구리와 미국 주식','동반 움직임은 성장 기대와 일치할 수 있지만 구리 공급 차질이라는 대체 설명도 있어.'),('BTC-USD','^GSPC',1,'비트코인과 미국 주식','위험 선호가 공통으로 작용할 수 있지만 주말 거래와 암호자산 고유 위험 때문에 동일 자산처럼 다루지 않아.')]
def build(rows,evidence,snapshot_id):
 from .engine import claim
 by={r['symbol']:r for r in rows};out=[]
 for left,right,expected,title,mechanism in PAIRS:
  a,b=by.get(left),by.get(right)
  if not a or not b or any(x['quality_status'] not in ('fresh','delayed') for x in (a,b)):continue
  histories=[{x['date']:x['value'] for x in r['history']} for r in (a,b)];dates=sorted(set(histories[0])&set(histories[1]));windows=[];refs=[];signs=[]
  for n in (5,20):
   if len(dates)<=n:continue
   start,end=dates[-n-1],dates[-1];changes=[]
   for row,h in zip((a,b),histories):
    if h[start]<=0 and row['asset_class']!='rates':break
    change=(h[end]-h[start])*100 if row['asset_class']=='rates' else (h[end]/h[start]-1)*100;unit='bp' if row['asset_class']=='rates' else '%';changes.append(change)
    eid='cross'+hashlib.sha256((snapshot_id+row['instrument_id']+start+end).encode()).hexdigest()[:20]
    if not any(e['id']==eid for e in evidence):
     inputs=[e['id'] for e in evidence if e.get('instrument_id')==row['instrument_id'] and e.get('metric')=='value']
     evidence.append({'id':eid,'kind':'calculation','provider':row['provider'],'source_url':row['source_url'],'retrieved_at':row['retrieved_at'],'observed_at':row['observed_at'],'description':row['name']+f' matched {n} observation change','quality_status':row['quality_status'],'input_evidence_ids':inputs,'method':'Common-date intersection, no forward fill; start '+start+' end '+end,'value':change,'unit':unit,'start_value':h[start],'end_value':h[end],'snapshot_id':snapshot_id})
    refs.append(eid)
   if len(changes)==2:
    units=['bp' if x['asset_class']=='rates' else '%' for x in (a,b)];windows.append(f"{n}개 공통 관측 구간({start}~{end})에서 각각 {changes[0]:+.2f}{units[0]}, {changes[1]:+.2f}{units[1]}");signs.append(0 if changes[0]*changes[1]==0 else 1 if changes[0]*changes[1]*expected>0 else -1)
  if not windows:continue
  status='가정한 경로와 방향이 일치해' if all(x==1 for x in signs) else '가정한 경로와 방향이 반대야' if all(x==-1 for x in signs) else '관측 기간에 따라 방향이 엇갈려'
  out.append(claim(title+': '+'. '.join(windows)+'. '+status+'. '+mechanism+' 동행은 인과관계의 확인이 아니야.',list(dict.fromkeys(refs)),'calculation','low',counter=['변화 방향이 역전되거나 공식 발표가 가격 기반 가정과 충돌하면 이 해석을 다시 봐야 해.'],missing=['직접적인 인과 증거와 독립 출처 확인이 필요해.']))
 return out
