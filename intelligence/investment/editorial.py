"""CAD-reader editorial contract. Price evidence supports calculations, never causes."""
import datetime as dt,hashlib,json,math,re,statistics
from zoneinfo import ZoneInfo
VERSION='cad-reader/1.0'
TITLES=['오늘의 핵심 3가지','원인 귀속','CAD 기준 관점','자산 간 관계','다음 30일 체크포인트','지난 보고서 대비 변화','데이터 품질과 원자료']
LABELS={'관측','원인','해석','시나리오'}
COUNTERS={
 ('^GSPC','us10y'):'[해석] 일반 원칙: 국채금리가 올라도 기업 이익 전망이 더 개선되면 미국 주식의 할인율 부담을 상쇄할 수 있다.',
 ('^IXIC','us10y'):'[해석] 일반 원칙: 나스닥에서는 소수 대형 기술기업의 실적 충격이 금리 민감도를 압도할 수 있다.',
 ('^GSPTSE','CL=F'):'[해석] 일반 원칙: TSX의 금융·소재 업종 비중과 에너지 기업의 비용·헤지 때문에 유가 변화가 지수 전체로 그대로 전달되지는 않는다.',
 ('USD/CAD','CL=F'):'[해석] 일반 원칙: 원유와 CAD의 관계는 캐나다·미국 금리 차이와 미국 달러 수요가 반대로 움직이면 약해질 수 있다.',
 ('GC=F','us10y'):'[해석] 일반 원칙: 금의 기회비용은 명목금리보다 실질금리에 가까우며 안전자산 수요가 금리 효과를 압도할 수 있다.',
 ('HG=F','^GSPC'):'[해석] 일반 원칙: 구리 광산 공급 차질과 중국 재고 변화는 미국 기업 이익과 별개로 구리 가격을 움직일 수 있다.',
 ('BTC-USD','^GSPC'):'[해석] 일반 원칙: 비트코인의 주말 거래·청산·규제 충격은 미국 주식의 거래 시간과 기업 실적에 없는 위험이다.',
 ('CL=F','BZ=F'):'[해석] 일반 원칙: WTI와 Brent의 괴리는 생산 지역·운송 제약·계약 월물 차이로 벌어질 수 있다.'}

def statement(label,text,refs=(),**extra):
 return {'label':label,'text':text,'evidence_ids':list(dict.fromkeys(refs)),**extra}
def obs(text,refs=(),**extra):return statement('관측',text,refs,**extra)
def principle(text):return statement('해석','일반 원칙: '+text,general_principle=True)
def history(row):return {x['date']:float(x['value']) for x in row.get('history',[]) if isinstance(x.get('value'),(int,float)) and math.isfinite(x['value'])}
def daily_stats(row):
 h=history(row);days=sorted(h);v=[h[d] for d in days]
 changes=[(b-a)*100 if row['asset_class']=='rates' else (b/a-1)*100 for a,b in zip(v,v[1:]) if a>0 or row['asset_class']=='rates']
 if len(changes)<21:return {'sigma':None,'move':changes[-1] if changes else None,'large':False,'reason':'현재 변동을 제외한 이전 20개 일간 변화가 부족하다'}
 sigma=statistics.stdev(changes[-21:-1]);move=changes[-1]
 return {'sigma':sigma,'move':move,'large':abs(move)>1.5*sigma,'ratio':abs(move)/sigma if sigma else None,'baseline_start':days[-22],'baseline_end':days[-2],'date':days[-1],'n':20}
def eligible(row):return row.get('quality_status') in ('fresh','delayed') and (row['asset_class']!='commodity' or row.get('contract_gate',{}).get('status')=='verified')

def cad_result(row,fx):
 a,b=history(row),history(fx);dates=sorted(set(a)&set(b))
 if len(dates)<2:return None
 start,end=dates[-2:]
 # Never quietly substitute an older overlapping period for today's asset move.
 if end!=max(a) or end!=max(b) or start!=sorted(a)[-2]:return None
 if min(a[start],b[start],a[end],b[end])<=0:return None
 usd=(a[end]/a[start]-1)*100;cad=(a[end]*b[end]/(a[start]*b[start])-1)*100
 return {'start':start,'end':end,'usd_pct':usd,'cad_pct':cad,'fx_pct':(b[end]/b[start]-1)*100,'fx_start':b[start],'fx_end':b[end],'asset_start':a[start],'asset_end':a[end],'method':'(asset_end*USDCAD_end)/(asset_start*USDCAD_start)-1; unhedged, before fees/tax, non-synchronous daily fix'}

def add_evidence(report,prefix,description,inputs,value=None,unit=None,**metadata):
 eid=prefix+hashlib.sha256(json.dumps([description,inputs,metadata],sort_keys=True,default=str).encode()).hexdigest()[:20]
 if not any(e['id']==eid for e in report['evidence']):report['evidence'].append({'id':eid,'kind':'calculation','provider':'AIRI deterministic calculation','source_url':None,'retrieved_at':report['generated_at'],'description':description,'quality_status':'delayed','input_evidence_ids':inputs,**({'value':value,'unit':unit} if value is not None else {}),**metadata})
 return eid

def annotate(report,snapshot,search,fetch,previous=None,now=None):
 from .cause_search import investigate
 now=now or dt.datetime.now(dt.timezone.utc);rows=snapshot['rows'];by={x['symbol']:x for x in rows};market={x['instrument_id']:x for x in report['market_rows']};refs={x['instrument_id']:x['evidence_ids'][:1] for x in report['market_rows']}
 sections=[{'title':x,'items':[]} for x in TITLES];audit={'searches':[],'cross_checks':[],'contract_gates':[]};stats={};cad={}
 # No interpretation of unidentified continuous futures. No guessed expiry calendar.
 for row in rows:
  if row['asset_class']=='commodity':
   gate={'instrument_id':row['instrument_id'],'status':'excluded','contract_month':None,'expiry':None,'reason':'연속선물 피드의 실제 월물·만기·차월물 관측이 검증되지 않아 해석에서 제외한다'}
   row['contract_gate']=gate;audit['contract_gates'].append(gate)
   sections[6]['items'].append(obs(row['name']+': '+gate['reason']+'.',refs[row['instrument_id']]))
  stats[row['instrument_id']]=daily_stats(row)
 fx=by.get('USD/CAD')
 for row in rows:
  if row['currency']=='USD' and row['asset_class'] in ('equity','index','crypto') and eligible(row):
   c=cad_result(row,fx) if fx and eligible(fx) else None
   if c:
    eid=add_evidence(report,'cad',row['name']+' CAD 환산',refs[row['instrument_id']]+refs[fx['instrument_id']],c['cad_pct'],'%',**c);cad[row['instrument_id']]=(c,eid)
    sections[2]['items'].append(obs(f"{row['name']}의 {c['start']}~{c['end']} 변화는 USD 기준 {c['usd_pct']:+.2f}%, CAD 환산 기준 {c['cad_pct']:+.2f}%이고 환율 효과를 포함한 차이는 {c['cad_pct']-c['usd_pct']:+.2f}%포인트다.",[eid]))
   else:sections[2]['items'].append(obs(row['name']+'의 최신 자산 관측일과 USD/CAD 관측일이 일치하지 않아 CAD 수익률을 계산하지 않는다.'))
 sections[2]['items'].append(principle('USD/CAD가 상승하면 CAD가 약해지며(USD/CAD 상승 = CAD 약세), CAD 투자자가 보유한 환노출 미국 자산의 CAD 환산액을 높이는 방향으로 작용한다.'))
 sections[2]['items'].append(obs('CAD 환산은 자산 종가와 캐나다은행 일별 환율의 날짜를 맞춘 근사치이며, 동일 시각 체결·환헤지·수수료·세금은 반영하지 않는다.'))
 cause_by={}
 for row in rows:
  st=stats[row['instrument_id']]
  if st['large']:
   result=investigate(row,st,search,fetch,now);audit['searches'].append(result);cause_by[row['instrument_id']]=result
   for source in result['sources']:
    if not any(e['id']==source['id'] for e in report['evidence']):report['evidence'].append(source)
   unit='bp' if row['asset_class']=='rates' else '%';sid=add_evidence(report,'sig',row['name']+' 20관측 변동성 검정',refs[row['instrument_id']],st['sigma'],unit,**st)
   sections[1]['items'].append(obs(f"{row['name']}의 {st['date']} 일간 변화 {st['move']:+.2f}{unit}는 직전 20개 일간 변화의 표본 표준편차 {st['sigma']:.3f}{unit}의 1.5배 기준을 넘는다.",[sid]))
   sections[1]['items'].append(statement('원인' if result['status']=='confirmed' else '해석',result['text'],result['evidence_ids'],confidence='low' if result['status']!='confirmed' else 'moderate',cause_status=result['status']))
 if not sections[1]['items']:sections[1]['items'].append(obs('확보한 자료에서 직전 20개 일간 변화의 표준편차 1.5배를 넘는 항목은 없다.'))
 candidates=[x for x in rows if eligible(x) and stats[x['instrument_id']]['move'] is not None]
 candidates.sort(key=lambda x:(100 if stats[x['instrument_id']]['large'] else 0)+(10 if x['symbol'] in ('^IXIC','^GSPTSE','USD/CAD') else 0)+(stats[x['instrument_id']].get('ratio') or 0),reverse=True)
 for row in candidates[:3]:
  st=stats[row['instrument_id']];unit='bp' if row['asset_class']=='rates' else '%';items=[obs(f"{row['name']}는 최신 완료 관측에서 {st['move']:+.2f}{unit} 변했고 직전 20개 일간 변화 표준편차는 {st['sigma']:.3f}{unit}다." if st['sigma'] is not None else row['name']+'의 일간 변화는 확인했지만 20개 일간 변화 표준편차는 자료 부족이다.',refs[row['instrument_id']])]
  if row['instrument_id'] in cause_by:
   cause=cause_by[row['instrument_id']];items.append(statement('원인' if cause['status']=='confirmed' else '해석',cause['text'],cause['evidence_ids'],confidence='low' if cause['status']!='confirmed' else 'moderate',cause_status=cause['status']))
  if row['instrument_id'] in cad:
   c,eid=cad[row['instrument_id']];items.append(obs(f"환노출 CAD 보유 기준 변화는 {c['cad_pct']:+.2f}%로 USD 기준과 {c['cad_pct']-c['usd_pct']:+.2f}%포인트 차이가 난다.",[eid]))
  elif row['symbol']=='USD/CAD' and cad:
   c,eid=next(iter(cad.values()));items.append(obs(f"이 관측 구간에서 환노출 미국 자산의 CAD 환산 변화는 USD 변화보다 {c['cad_pct']-c['usd_pct']:+.2f}%포인트 달라졌다(USD/CAD 상승 = CAD 약세).",[eid]))
  elif row['symbol']=='^GSPTSE' and cad:
   c,eid=next(iter(cad.values()));h=history(row)
   if c['start'] in h and c['end'] in h:
    change=(h[c['end']]/h[c['start']]-1)*100;relative=change-c['cad_pct'];rid=add_evidence(report,'relative','TSX versus US CAD common-date relative change',refs[row['instrument_id']]+[eid],relative,'%포인트',start=c['start'],end=c['end'])
    items.append(obs(f"같은 날짜 구간에서 TSX의 CAD 변화는 비교 미국 자산의 CAD 환산 변화보다 {relative:+.2f}%포인트 달라 통화 효과를 분리한 뒤에도 성과 차이가 남는다.",[rid]))
  else:
   items.append(principle('이 자산의 현지 통화 위험과 CAD 환산 위험을 구분해야 하며 보유 비중이 없으므로 개인 손익은 계산하지 않는다.'))
  sections[0]['items'].append({'heading':row['name'],'sentences':items[:3]})
 for (left,right),counter in COUNTERS.items():
  a,b=by.get(left),by.get(right)
  if not a or not b or not eligible(a) or not eligible(b):continue
  ah,bh=history(a),history(b);days=sorted(set(ah)&set(bh))
  if len(days)<21:continue
  start,end=days[-21],days[-1];ca=(ah[end]-ah[start])*100 if a['asset_class']=='rates' else (ah[end]/ah[start]-1)*100;cb=(bh[end]-bh[start])*100 if b['asset_class']=='rates' else (bh[end]/bh[start]-1)*100
  eid=add_evidence(report,'pair',a['name']+' / '+b['name']+' 단기 20공통관측',refs[a['instrument_id']]+refs[b['instrument_id']],ca,'bp' if a['asset_class']=='rates' else '%',start=start,end=end,second_value=cb)
  sections[3]['items'] += [obs(f"{a['name']}와 {b['name']}의 단기 20개 공통 관측 구간({start}~{end}) 변화는 각각 {ca:+.2f}{'bp' if a['asset_class']=='rates' else '%'}, {cb:+.2f}{'bp' if b['asset_class']=='rates' else '%'}다.",[eid]),principle(counter.removeprefix('[해석] 일반 원칙: '))]
 if not sections[3]['items']:sections[3]['items'].append(obs('공통 관측 구간과 자료 품질을 충족한 자산 쌍이 없어 관계 해석을 유보한다.'))
 for event in report['watch_items']:
  day=dt.date.fromisoformat(event['date']);delta=(day-now.astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).date()).days
  if not 0<=delta<=30:continue
  time=dt.datetime.fromisoformat(event['scheduled_at']).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M PT') if event.get('scheduled_at') else event['date']+' 시간 미확인'
  sections[4]['items'].append(obs(event['event']+'는 '+time+' 일정이다.',event['evidence_ids']))
  consensus=event.get('consensus')
  sections[4]['items'].append(obs('검증된 컨센서스가 없어 예상 대비 차이를 수치화하지 않는다.' if not consensus else str(consensus)))
  sections[4]['items'].append(statement('시나리오','일반 원칙: 발표가 시장 예상과 다르면 '+('캐나다 단기 국채금리와 USD/CAD가 먼저 반응할 수 있고 TSX 업종별 영향은 뒤이어 확인한다.' if 'Bank of Canada' in str([e['provider'] for e in report['evidence'] if e['id'] in event['evidence_ids']]) or 'Interest Rate' in event['event'] else '미국 단기 국채금리와 USD/CAD가 먼저 반응할 수 있으며 미국 주식은 이익 기대와 할인율의 상대 변화를 확인한다.'),general_principle=True))
 if not sections[4]['items']:sections[4]['items'].append(obs('다음 30일 안에 검증된 공식 일정이 없다.'))
 for name in ('맞은 것','틀린 것','판단 보류 유지'):
  # Never grade descriptive prices or unfalsifiable prose as forecasts.
  previous_date=previous.get('generated_at') if previous else None
  sections[5]['items'].append(obs(name+': '+('직전 보고서에 평가 기한·수치 조건이 있는 검증 가능한 판단이 없어 판정을 만들지 않는다.' if name!='판단 보류 유지' else ('직전 보고서의 판단 유보를 결과 검증 없이 성공·실패로 바꾸지 않는다.' if previous else '직전 보고서가 없어 비교하지 않는다.')),previous_report_id=previous.get('report_id') if previous else None,previous_generated_at=previous_date))
 for row in rows:
  sections[6]['items'].append(obs(row['name']+'의 자료 상태는 '+row['quality_status']+'이며 관측 시각은 '+str(row.get('observed_at'))+'다.',refs[row['instrument_id']]))
 report['editorial']={'version':VERSION,'sections':sections,'audit':audit,'checks':{},'comparison_basis':previous.get('report_id') if previous else None}
 check(report)
 return report

def check(report):
 ed=report['editorial'];errors=[];sentences=[]
 for sec in ed['sections']:
  for x in sec['items']:sentences.extend(x.get('sentences',[x]))
 evidence={x['id']:x for x in report['evidence']}
 for c in sentences:
  if c.get('label') not in LABELS:errors.append('label')
  text=c['text']
  if re.search(r'습니다|입니다|하세요|해요|있어요|없어요',text):errors.append('register')
  if re.search(r'매수하|매도하|목표가',text):errors.append('investment instruction')
  if ('추세' in text or '장기' in text) and not re.search(r'\d+.*(?:%|bp)',text):errors.append('unquantified trend')
  if c.get('general_principle') and c['evidence_ids']:errors.append('principle cited')
  if any(id not in evidence for id in c['evidence_ids']):errors.append('missing evidence')
  if c['label']=='원인' and (c.get('cause_status')!='confirmed' or len(c['evidence_ids'])<2):errors.append('unsupported cause')
 counters=[c['text'] for sec in ed['sections'][3:4] for c in sec['items'] if c.get('general_principle')]
 if len(counters)!=len(set(counters)):errors.append('duplicate counter')
 ed['checks']={'core_three_reader_context':all(any('CAD' in c['text'] or '포트폴리오' in c['text'] for c in x.get('sentences',[])) for x in ed['sections'][0]['items']),'sentence_citation_scope':not errors,'consistent_informal_register':not any(x=='register' for x in errors),'iana_timezones':True,'labels_register_and_evidence':not errors,'large_move_search_attempts':all(x.get('attempted') for x in ed['audit']['searches']),'large_move_search_completed':all(x.get('status')!='search_failed' for x in ed['audit']['searches']),'unique_relationship_counters':len(counters)==len(set(counters)),'errors':errors}
 if not ed['checks']['core_three_reader_context']:errors.append('missing CAD reader context')
 if not ed['checks']['large_move_search_completed']:errors.append('cause search unavailable; publication withheld')
 if errors:raise ValueError('Editorial validation failed: '+','.join(sorted(set(errors))))
 return True
