"""Reproducible descriptive synthesis, independent of PDF and local prose models.

All thresholds are disclosed heuristics, never p-values or calibrated probabilities.
Prices support observations/mechanism consistency, never a causal CONFIRMED claim.
"""
import datetime as dt,math,statistics,re,copy
from zoneinfo import ZoneInfo
from .research_schema import finite,ident,claim
VERSION='market-synthesis/1'
FLAGS={'VERIFIED','STALE','DATE_MISMATCH','SINGLE_SOURCE','PROXY','MISSING','PARTIAL','UNVERIFIED','ESTIMATED'}
SNAPSHOT=('tsx','sp500','nasdaq','cadusd','wti','gold','ca2y','ca10y','us2y','us10y','vix')

def normalize(m):
 sources={s['id']:s for s in m['sources']}
 for key,a in m['assets'].items():
  if a.get('symbol','').endswith('=F') and a.get('observed_at'):
   clock=dt.datetime.fromisoformat(m['as_of']).astimezone(ZoneInfo('America/New_York'))
   if a['observed_at']==clock.date().isoformat() and clock.hour<17:a['partial_session']=True
  flags=[]
  if not a.get('available'):flags=['MISSING']
  else:
   flags.append('SINGLE_SOURCE')
   tier=sources.get(a.get('source_id'),{}).get('tier',4)
   flags.append('VERIFIED' if tier<=2 else 'UNVERIFIED')
   if a.get('stale'):flags.append('STALE')
   if a.get('partial_session'):flags.append('PARTIAL')
   if a.get('proxy'):flags.append('PROXY')
   a['source_tier']=tier
  a['quality_flags']=flags
  future=a.get('symbol','').endswith('=F')
  a['instrument_type']=a.get('instrument_type') or ('Futures continuous front-month series' if future else 'Sector ETF price-return proxy' if a.get('proxy') else 'Government yield' if a.get('kind')=='yield' else 'FX reference' if a.get('kind')=='fx' else 'Index / price series')
  if future:
   a['contract']=None;a['roll_status']='UNVERIFIED';a['roll_warning']='Contract identity and roll calendar unavailable; price changes may include rollover effects.'
   if finite(a.get('daily_change')) and finite(a.get('realized_daily_volatility_20d')) and abs(a['daily_change'])>2*max(a['realized_daily_volatility_20d'],.01):a['roll_warning']+=' Large move: inspect contract transition before interpreting an economic shock.'
 return m

def completed_market(m,pool):
 """Keep live snapshot intact; broader comparisons use last completed observations."""
 from .research_market import describe,evidence
 result=copy.deepcopy(m);basis=[];sources={s['id']:s for s in m['sources']}
 for key,a in m['assets'].items():
  if not a.get('available') or not a.get('partial_session'):continue
  history=[v for v in a.get('history',[]) if v['date']<a['observed_at']]
  origin=sources.get(a.get('source_id'))
  if not origin or not history:continue
  value=describe(key,a['label'],a['unit'],history,origin,dt.datetime.fromisoformat(m['as_of']),a.get('kind','price'),a.get('region'))
  value.update({k:a[k] for k in ('symbol','proxy','instrument_type','source_ids','contract','roll_status','roll_warning') if k in a})
  result['assets'][key]=value;basis.append({'key':key,'live_observation':a['observed_at'],'analysis_observation':value.get('observed_at'),'reason':'Incomplete latest session excluded from broader comparisons; live snapshot retained.'})
 normalize(result);pool.update(evidence(result));return result,basis

def refs(pool,keys,metrics=('current','daily_change','change_5d','change_20d')):
 return [k for k,v in pool.items() if v.get('asset') in keys and v.get('metric') in metrics]

def usable(a):return bool(a.get('available') and not set(a.get('quality_flags',[]))&{'STALE','PARTIAL','MISSING'} and not a.get('stale') and not a.get('partial_session'))

def confidence_for(m,keys,refs_,agreement=True,causal=False):
 items=[m['assets'][k] for k in keys if k in m['assets']];valid=[a for a in items if usable(a)]
 dates={a.get('observed_at') for a in valid};primary=any(a.get('source_tier',4)==1 for a in valid)
 flags=set(f for a in items for f in a.get('quality_flags',[]))
 breakdown={'Source Quality':'Primary/infrastructure available' if primary else 'Secondary provider observations','Source Agreement':'Independent confirmation not established','Data Completeness':f'{len(valid)}/{len(keys)} usable required series','Timing Match':'Matched latest dates' if len(dates)==1 else 'Observation dates differ or unavailable','Cross-Asset Confirmation':'Directional agreement' if agreement else 'Conflicting directions / limited confirmation','Causal Evidence':'Direct causal evidence' if causal else 'No direct causal evidence','Primary Source Availability':primary}
 level='Medium' if len(valid)==len(keys) and refs_ and len(dates)==1 and agreement and not flags&{'PROXY','STALE','PARTIAL'} else 'Low'
 return {'level':level,'dimensions':breakdown,'reason':'관측값의 일관성에 대한 신뢰도다. 단일 공급자 관측만으로 인과관계의 신뢰도가 높아지지는 않는다.'}

def aligned(m,keys,n=5):
 """Common-date intersection, not subtraction of differently dated endpoints."""
 items=[m['assets'].get(k,{}) for k in keys];flags=[]
 if not all(usable(a) for a in items):return {'available':False,'reason':'Missing, stale or partial input','quality_flags':['MISSING']}
 maps=[{r['date']:r['value'] for r in a.get('history',[]) if finite(r.get('value'))} for a in items]
 dates=sorted(set.intersection(*(set(d) for d in maps))) if maps else []
 if len(dates)<=n:return {'available':False,'reason':'Insufficient common dated observations','quality_flags':['MISSING']}
 if len({a['observed_at'] for a in items})>1:flags.append('DATE_MISMATCH')
 changes=[]
 for a,d in zip(items,maps):
  start,end=d[dates[-n-1]],d[dates[-1]]
  if a.get('kind')=='yield':changes.append((end-start)*100)
  elif a.get('kind')=='spread':changes.append(end-start)
  elif start>0:changes.append((end/start-1)*100)
  else:return {'available':False,'reason':'Invalid price denominator','quality_flags':['UNVERIFIED']}
 return {'available':True,'start':dates[-n-1],'end':dates[-1],'common_observations':n+1,'changes':changes,'quality_flags':flags,'warning':'Observation dates differ; computed on common dates only.' if flags else None}

def spreads(m,pool):
 output={}
 for key,left,right,label in [('ca_us_2y','ca2y','us2y','Canada 2Y - US 2Y'),('ca_us_10y','ca10y','us10y','Canada 10Y - US 10Y'),('ca_curve','ca10y','ca2y','Canada 10Y - 2Y'),('ca_curve_3m','ca10y','ca3m','Canada 10Y - 3M'),('us_curve','us10y','us2y','US 10Y - 2Y'),('us_curve_3m','us10y','us3m','US 10Y - 3M'),('us_breakeven10y','us10y','us_real10y','US nominal - real 10Y approximation')]:
  aa=m['assets'].get(left,{});bb=m['assets'].get(right,{})
  if not all(usable(a) for a in (aa,bb)):output[key]={'available':False,'label':label,'reason':'Missing, stale or partial matched yields'};continue
  a={r['date']:r['value'] for r in aa['history']};b={r['date']:r['value'] for r in bb['history']};dates=sorted(set(a)&set(b))
  if not dates:output[key]={'available':False,'label':label,'reason':'No matched dates'};continue
  history=[{'date':d,'value':(a[d]-b[d])*100} for d in dates];current=history[-1]['value']
  row={'available':True,'key':key,'label':label,'current':current,'unit':'bps','kind':'spread','observed_at':dates[-1],'source_ids':list(dict.fromkeys(aa.get('source_ids',[aa['source_id']])+bb.get('source_ids',[bb['source_id']]))),'history':history,'source_tier':max(aa.get('source_tier',4),bb.get('source_tier',4)),'quality_flags':['ESTIMATED'],'formula':f'({left} - {right}) × 100; input yields in percent','evidence_ids':[]}
  if aa['observed_at']!=bb['observed_at']:row['quality_flags'].append('DATE_MISMATCH');row['warning']='Observation dates differ; common-date curve only.'
  if key=='us_breakeven10y':row['warning']='Nominal par minus real par yield is an approximation, not a pure inflation forecast; includes liquidity/risk and construction differences.'
  for n in (5,20):row[f'change_{n}d']=current-history[-n-1]['value'] if len(history)>n else None
  row['curve_shape']='Inverted' if current< -10 else 'Normal' if current>10 else 'Flat'
  delta=row['change_20d'];row['curve_change']='Not Available' if delta is None else 'Steepening' if delta>5 else 'Flattening' if delta< -5 else 'Stable'
  for metric in ('current','change_5d','change_20d'):
   if row.get(metric) is None:continue
   fid=ident('spread',key,metric,dates[-1]);text=f'{label} {metric} {row[metric]:.2f} bp at {dates[-1]}; matched-date yield difference'
   pool[fid]={'id':fid,'text':text,'quote':text,'source_ids':row['source_ids'],'tag':'FACT','confirmed':False,'asset':key,'metric':metric,'value':row[metric],'observation_time':dates[-1],'quality_flags':row['quality_flags'],'formula':row['formula']};row['evidence_ids'].append(fid)
  output[key]=row;m['assets'][key]=row
 return output

def daily_move(m,pool,breadth):
 a=m['assets'].get('tsx',{});need=('daily_change','change_5d','change_20d','average_absolute_move_20d','realized_daily_volatility_20d')
 missing=[k for k in need if not finite(a.get(k))];r={'classification':'Unable to Classify','method':'Descriptive market-move heuristic','missing':missing,'inputs':{k:a.get(k) for k in need+('volume_ratio',)},'evidence_ids':refs(pool,['tsx','vix']),'rules':'Magnitude vs 20-session mean absolute return AND standard deviation; volume/VIX/breadth confirmation; 5D/20D persistence recorded separately. Not a statistical test.'}
 if not usable(a) or missing or min(a.get('average_absolute_move_20d',0),a.get('realized_daily_volatility_20d',0))<=0:
  r['reason']='장중 데이터: 당일 거래량과 변동이 확정되지 않아 종가 기준 분류를 보류한다.' if a.get('partial_session') else '오래되었거나 누락된 관측치 또는 불충분한 변동 기준으로 분류를 보류한다.'
  return r
 size=abs(a['daily_change']);ratio=min(size/a['average_absolute_move_20d'],size/a['realized_daily_volatility_20d']);volume=a.get('volume_ratio');v=m['assets'].get('vix',{})
 confirmation=int(finite(volume) and volume>=1.25)+int(usable(v) and v.get('daily_change',0)>=10)+int(breadth.get('interpretation') in ('Broad Participation','Broad Weakness'))
 r['classification']='Extreme Move' if ratio>=3 and confirmation>=2 else 'Significant Move' if ratio>=2 and confirmation>=1 else 'Normal Noise' if ratio<=1 and finite(volume) and volume<=1.25 else 'Moderate Move'
 if volume is None:r['missing'].append('volume_ratio');r['classification']='Unable to Classify' if ratio<=1 else 'Moderate Move'
 r['confirmation_count']=confirmation;r['persistence']={'5D':a['change_5d'],'20D':a['change_20d'],'same_sign':a['daily_change']*a['change_5d']>0 and a['change_5d']*a['change_20d']>0}
 return r

def constituents(m,pool):
 """Optional verified snapshot adapter; never substitute ETF holdings for index weights.
 Snapshot: universe, membership_source{...}, membership_date, session, rows[{symbol,
 sector, weight_pct, weight_date, return_pct, return_date, history}], complete_universe.
 """
 missing={'available':False,'interpretation':'Data Unavailable','reason':'No complete, dated official TSX Composite constituent snapshot is connected. ETF holdings are not substituted.','rows':[]}
 snap=m.get('constituent_snapshot')
 if not snap:return dict(missing),dict(missing)
 src=snap.get('membership_source',{});date=m['assets'].get('tsx',{}).get('observed_at');rows=snap.get('rows',[])
 if snap.get('universe')!='S&P/TSX Composite' or src.get('tier',4)>2 or not src.get('url') or snap.get('session')!=date or snap.get('membership_date')!=date:return dict(missing),dict(missing)
 if not src.get('id') or any(not x.get('symbol') for x in rows) or len({x['symbol'] for x in rows})!=len(rows):return dict(missing),dict(missing)
 good=[x for x in rows if x.get('return_date')==date and finite(x.get('return_pct'))]
 def evidence(text):
  fid=ident('constituents',text,date);pool[fid]={'id':fid,'text':text,'quote':text,'tag':'FACT','source_ids':[src['id']],'confirmed':False,'observation_time':date,'quality_flags':['ESTIMATED']};return fid
 m['sources'].append(src)
 breadth=dict(missing);contribution=dict(missing)
 if good and len(good)==len(rows) and snap.get('complete_universe'):
  up=sum(x['return_pct']>0 for x in good);down=sum(x['return_pct']<0 for x in good);pct=up/len(good);strength='Broad Participation' if pct>=.7 else 'Broad Weakness' if down/len(good)>=.7 else 'Moderate Participation';tsx=m['assets']['tsx'].get('daily_change')
  if finite(tsx) and (tsx>0 and down>up or tsx<0 and up>down):strength='Divergence'
  breadth={'available':True,'interpretation':strength,'advancers':up,'decliners':down,'unchanged':len(good)-up-down,'ad_ratio':up/down if down else None,'count':len(good),'observed_at':date,'method':'Computed from full verified membership; directional participation threshold 70%, a descriptive heuristic.','evidence_ids':[]}
  for n in (20,50,200):
   histories=[x.get('history',[]) for x in good];eligible=[h for h in histories if len(h)>=n and h[-1].get('date')==date and all(finite(r.get('value')) for r in h[-n:])]
   breadth[f'above_{n}dma']=100*sum(h[-1]['value']>statistics.mean(r['value'] for r in h[-n:]) for h in eligible)/len(good) if len(eligible)==len(good) else None
  # Closing-price highs/lows are distinct from intraday 52-week extremes.
  histories=[x.get('history',[]) for x in good]
  complete=all(len(h)>=253 and h[-1].get('date')==date and all(finite(r.get('value')) for r in h[-253:]) for h in histories)
  breadth['new_highs']=sum(h[-1]['value']>max(r['value'] for r in h[-253:-1]) for h in histories) if complete else None
  breadth['new_lows']=sum(h[-1]['value']<min(r['value'] for r in h[-253:-1]) for h in histories) if complete else None
  breadth['high_low_basis']='252-session closing-price extremes, not intraday official counts'
  breadth['evidence_ids']=[evidence(f'TSX full-snapshot breadth {date}: advancers {up}, decliners {down}, unchanged {breadth["unchanged"]}, above 50DMA {breadth["above_50dma"]}')]
 previous=snap.get('previous_session');expected_previous=next((x['date'] for x in reversed(m['assets']['tsx'].get('history',[])) if x['date']<date),None)
 contrib=[x for x in good if previous and previous==expected_previous and finite(x.get('weight_pct')) and 0<=x['weight_pct']<=100 and x.get('weight_date')==snap.get('previous_session')]
 if contrib and sum(x['weight_pct'] for x in contrib)<=100.1:
  calculated=[{**{k:x.get(k) for k in ('symbol','sector','weight_pct','return_pct','weight_date')},'contribution_pp':x['weight_pct']/100*x['return_pct']} for x in contrib]
  for x in calculated:x['evidence_ids']=[evidence(f'{date} {x["symbol"]}: prior-session weight {x["weight_pct"]}% × return {x["return_pct"]}% = {x["contribution_pp"]:.6f} percentage-point estimated contribution')]
  contribution={'available':True,'method':'Estimated contribution based on available constituent weights and matched-session returns. Not official TMX contribution.','coverage_weight_pct':sum(x['weight_pct'] for x in contrib),'positive':sorted([x for x in calculated if x['contribution_pp']>0],key=lambda x:-x['contribution_pp'])[:5],'negative':sorted([x for x in calculated if x['contribution_pp']<0],key=lambda x:x['contribution_pp'])[:5],'quality_flags':['ESTIMATED'],'rows':calculated}
 return breadth,contribution

def regime(m,pool):
 result={}
 def put(name,label,keys,reason):
  evidence=refs(pool,keys);result[name]={'classification':label,'reason':reason,'evidence_ids':evidence,'confidence':confidence_for(m,keys,evidence)}
 def asset(k):return m['assets'].get(k,{})
 equity=[asset(k) for k in ('tsx','sp500','nasdaq')];good=[a for a in equity if usable(a) and all(finite(a.get(f)) for f in ('change_5d','change_20d','average_absolute_move_20d'))]
 if len(good)==3:
  direction=lambda a:1 if a['change_5d']>a['average_absolute_move_20d'] and a['change_20d']>2*a['average_absolute_move_20d'] else -1 if a['change_5d']< -a['average_absolute_move_20d'] and a['change_20d']< -2*a['average_absolute_move_20d'] else 0
  dirs=[direction(a) for a in good];label='Risk-On' if all(d==1 for d in dirs) else 'Risk-Off' if all(d==-1 for d in dirs) else 'Neutral' if all(d==0 for d in dirs) else 'Mixed'
 else:label='Unable to Classify'
 put('equity',label,['tsx','sp500','nasdaq'],'5D와 20D가 최근 일일 변동폭을 함께 넘어서는지 3개 지수에서 비교한 가격 기반 국면이다. 구성 종목 전반의 위험 선호를 확정하지 않는다.')
 v=asset('vix');hist=[r['value'] for r in v.get('history',[])[:-1]];label='Unable to Classify'
 if usable(v) and len(hist)>=60:
  percentile=sum(x<=v['current'] for x in hist)/len(hist);median=statistics.median(hist);ratio=v['current']/median if median else 0
  label='Stressed' if percentile>=.95 and ratio>=1.5 else 'Elevated' if percentile>=.8 and ratio>=1.15 else 'Compressed' if percentile<=.2 and ratio<=.85 else 'Normal'
 put('volatility',label,['vix'],'VIX 수준을 가용 과거 분포 및 중앙값과 함께 비교한 기술적 구분이다. 통계 검정이나 손실 확률은 아니다.')
 yields=[asset(k) for k in ('ca2y','ca10y','us2y','us10y')];valid=[a for a in yields if usable(a) and all(finite(a.get(k)) for k in ('change_5d','change_20d'))];label='Unable to Classify'
 if len(valid)>=3:
  five=statistics.median(a['change_5d'] for a in valid);twenty=statistics.median(a['change_20d'] for a in valid);votes=sum(a['change_20d']>0 for a in valid)
  label='Rapidly Rising' if five>15 and twenty>30 and votes>=3 else 'Rising' if five>0 and twenty>10 and votes>=3 else 'Falling' if five<0 and twenty< -10 and votes<=1 else 'Stable'
 put('rates',label,['ca2y','ca10y','us2y','us10y'],'캐나다·미국 2Y/10Y의 5D·20D 방향과 중앙값을 함께 본다. Stable은 상반된 움직임도 포함할 수 있어 만기별 표를 확인한다.')
 fx=asset('cadusd');label='Unable to Classify'
 if usable(fx) and all(finite(fx.get(k)) for k in ('change_5d','change_20d')):label='Strengthening' if fx['change_5d']>.2 and fx['change_20d']>.5 else 'Weakening' if fx['change_5d']< -.2 and fx['change_20d']< -.5 else 'Neutral'
 put('cad',label,['cadusd'],'USD per CAD 기준의 5D·20D 방향이다. 금리차나 원유가 원인이라는 뜻은 아니다.')
 keys=['wti','brent','copper','natural_gas'];commod=[asset(k) for k in keys];valid=[a for a in commod if usable(a) and all(finite(a.get(k)) for k in ('change_5d','change_20d'))];label='Unable to Classify'
 if len(valid)>=3:
  ups=sum(a['change_5d']>0 and a['change_20d']>0 for a in valid);downs=sum(a['change_5d']<0 and a['change_20d']<0 for a in valid)
  label='Inflationary Pressure' if ups>=3 else 'Disinflationary Pressure' if downs>=3 else 'Neutral' if all(abs(a['change_20d'])<2 for a in valid) else 'Mixed'
 put('commodity',label,keys,'선물 가격의 투입비용 방향을 비교한다. 실제 CPI·기업 마진 효과는 환율·계약·헤지에 따라 다르며 롤오버도 미검증이다.')
 return result

RELATIONS=[
 ('equities_yields','tsx','ca10y',-1,'주가 ↔ 금리','금리 상승은 다른 조건이 같을 때 할인율 부담을 높일 수 있다.','금리가 하락 전환하거나 실적 전망 개선이 할인율 부담을 상쇄하는지 확인한다.'),
 ('equities_volatility','sp500','vix',-1,'주가 ↔ 변동성','주가 약세와 변동성 상승이 동반되면 위험 부담 확대와 일치한다.','주가 회복과 VIX 하락이 함께 지속되는지 확인한다.'),
 ('cad_oil','cadusd','wti',1,'CAD ↔ 원유','원유 가격 상승은 교역조건을 통해 CAD를 지지할 수 있지만 다른 경로도 작용한다.','원유 추세와 CAD 방향이 지속적으로 어긋나면 원유 중심 해석을 약화한다.'),
 ('cad_rates','cadusd','ca_us_2y',1,'CAD ↔ 캐나다·미국 금리차','캐나다 상대금리 상승은 CAD 보유의 상대수익을 높일 수 있다.','금리차 개선에도 CAD 약세가 이어지는지 확인한다.'),
 ('tsx_oil','tsx','wti',1,'TSX ↔ 원유','원유는 에너지 기업 매출·투자 여력에 연결될 수 있지만 TSX 전체 영향은 업종 비중에 달렸다.','원유 상승에도 에너지 실적·TSX 반응이 뒷받침되지 않으면 재검토한다.'),
 ('tsx_financials','tsx','sector_Financials',1,'TSX ↔ 금융 ETF','금융 업종과 지수의 동행을 점검한다. ETF 수익률은 공식 지수 기여도가 아니다.','금융 ETF와 TSX 방향의 괴리 또는 실제 구성 종목 기여도 공개로 재평가한다.'),
 ('tsx_materials','tsx','sector_Materials',1,'TSX ↔ 소재 ETF','소재 업종과 지수의 동행을 점검한다. 기업별 원자재·환율·비용 노출은 별도 검증한다.','소재 ETF 상대 강도가 역전되거나 실제 손익 근거가 다르면 재평가한다.'),
 ('gold_yields','gold','us_real10y',-1,'금 ↔ 실질금리','실질금리 상승은 무이자 금 보유의 기회비용을 높일 수 있다.','실질금리와 금의 같은 방향 움직임이 지속되면 이 경로만으로 설명하지 않는다.'),
 ('growth_yields','nasdaq','us10y',-1,'NASDAQ ↔ 금리','성장 기대가 큰 주식은 할인율에 민감할 수 있다. NASDAQ은 순수 성장주 포트폴리오가 아니다.','금리 방향이 바뀌거나 실적 전망이 주가 방향을 설명하는지 확인한다.'),
 ('copper_growth','copper','sp500',1,'구리 ↔ 경기 민감 가격','구리와 주가의 동행은 성장 기대와 일치할 수 있지만 공급 충격도 구리를 움직인다.','주가와 구리의 괴리 또는 공급 차질 자료가 나오면 성장 기대 해석을 재검토한다.')]

def cross_asset(m,pool):
 output=[]
 for key,a,b,expected,title,mechanism,invalidation in RELATIONS:
  if key=='gold_yields' and not usable(m['assets'].get(b,{})):b='us10y';title='금 ↔ 명목금리';mechanism+=' 실질금리가 없어 명목금리를 비교하며 기대인플레이션 경로는 분리하지 못했다.'
  windows={str(n):aligned(m,[a,b],n) for n in (5,20)};available=[x for x in windows.values() if x['available']];evidence=refs(pool,[a,b]);statuses=[]
  for win in available:
   x,y=win['changes'];statuses.append('POSSIBLE' if abs(x)<.01 or abs(y)<.01 else 'CONSISTENT WITH' if x*y*expected>0 else 'CONTRADICTED')
  status='UNVERIFIED' if not statuses else statuses[0] if len(set(statuses))==1 else 'POSSIBLE'
  facts=[]
  for n,w in windows.items():
   if w['available']:
    units=['bp' if m['assets'][k].get('kind') in ('yield','spread') else '%' for k in (a,b)]
    facts.append(f"{n} common sessions ({w['start']}–{w['end']}): {m['assets'][a]['label']} {w['changes'][0]:+.2f}{units[0]}, {m['assets'][b]['label']} {w['changes'][1]:+.2f}{units[1]}")
    sid=list(dict.fromkeys(s for k in (a,b) for s in m['assets'][k].get('source_ids',[m['assets'][k].get('source_id')]) if s))
    fid=ident('aligned',key,n,w['start'],w['end']);pool[fid]={'id':fid,'text':facts[-1],'quote':facts[-1],'tag':'FACT','confirmed':False,'source_ids':sid,'basis':'common-date history calculation','observation_time':w['end'],'start':w['start'],'values':w['changes'],'quality_flags':w['quality_flags']};evidence.append(fid)
  output.append({'id':key,'title':title,'status':status,'tag':'ANALYSIS' if available else 'UNCERTAINTY','text':(' / '.join(facts) if facts else '비교 가능한 최신 공통 관측치가 부족하다.')+' '+('관측 방향이 제시한 경로와 일치한다. 인과관계는 확인되지 않았다.' if status=='CONSISTENT WITH' else '관측 방향이 제시한 경로의 단순 예상과 충돌한다. 경로 자체가 불가능하다는 뜻은 아니다.' if status=='CONTRADICTED' else '관측 기간·방향이 섞여 있어 단일 경로로 설명할 수 없다.' if status=='POSSIBLE' else ''),'mechanism':mechanism,'windows':windows,'assets':[a,b],'evidence_ids':evidence if available else [],'invalidation':invalidation,'confidence':confidence_for(m,[a,b],evidence,status=='CONSISTENT WITH'),'causal_evidence':[],'quality_flags':sorted(set(f for w in windows.values() for f in w.get('quality_flags',[])))})
 return output

def sectors(m,pool):
 rows=[]
 for k,a in sorted(m['assets'].items()):
  if not k.startswith('sector_'):continue
  row={'sector':a['label'],'evidence_type':'ETF PROXY','key':k,'daily':a.get('daily_change'),'5d':a.get('change_5d'),'20d':a.get('change_20d'),'relative_vs_tsx':None,'evidence_ids':refs(pool,[k]),'quality_flags':a.get('quality_flags',[])}
  pair=aligned(m,[k,'tsx'],20)
  if pair['available']:
   row['relative_vs_tsx']=pair['changes'][0]-pair['changes'][1];row['relative_window']=pair['start']+' / '+pair['end'];row['quality_flags']=list(set(row['quality_flags']+pair['quality_flags']))
   fid=ident('relative',k,pair['start'],pair['end']);text=f"{a['label']} minus TSX common-date 20-observation return: {row['relative_vs_tsx']:+.4f} percentage points, {pair['start']} to {pair['end']}"
   pool[fid]={'id':fid,'text':text,'quote':text,'tag':'FACT','source_ids':[a['source_id'],m['assets']['tsx']['source_id']],'confirmed':False,'observation_time':pair['end'],'quality_flags':row['quality_flags']};row['evidence_ids'].append(fid)
  rows.append(row)
 leadership=sorted([r for r in rows if r['relative_vs_tsx'] is not None],key=lambda r:r['relative_vs_tsx'],reverse=True)
 interpretations=[]
 if len(leadership)>=2:
  high,low=leadership[0],leadership[-1]
  interpretations.append(claim(f"20개 공통 관측 구간에서 {high['sector']}의 TSX 대비 상대 가격 수익률은 {high['relative_vs_tsx']:+.2f}%p, {low['sector']}는 {low['relative_vs_tsx']:+.2f}%p다. 공식 업종 기여도나 자금 유입량을 뜻하지 않는다.",high['evidence_ids']+low['evidence_ids']))
 groups={'defensive':['sector_Utilities','sector_Consumer staples'],'cyclical':['sector_Energy','sector_Materials','sector_Industrials'],'rate_sensitive':['sector_Utilities','sector_Real Estate'],'commodity_sensitive':['sector_Energy','sector_Materials']}
 for name,keys in groups.items():
  group=[r for r in rows if r['key'] in keys and r['relative_vs_tsx'] is not None]
  if len(group)==len(keys):interpretations.append(claim(f"{name}: TSX 대비 20D 상대 수익률 범위 {min(r['relative_vs_tsx'] for r in group):+.2f}~{max(r['relative_vs_tsx'] for r in group):+.2f}%p. ETF 대체지표의 상대 강도이며 구조적 회전·실적 원인을 확정하지 않는다.",[f for r in group for f in r['evidence_ids']]))
 return {'rows':rows,'analysis':interpretations}

def event_enrichment(r):
 sources={s['id']:s for s in r['sources']};groups={'confirmed':[],'developing':[]}
 for e in r['events']:
  selected=[sources[s] for s in e['source_ids'] if s in sources];primary=[s['id'] for s in selected if s['tier']==1];families={s.get('quality',{}).get('family',s['url'].split('/')[2]) for s in selected if s['tier']<=3 or s.get('quality',{}).get('trusted_journalism')}
  timing=bool(e.get('event_time') and e.get('event_time_basis')=='explicit');confirmed=bool(e.get('facts') and all(f.get('confirmed') for f in e['facts']) and (primary or len(families)>=2) and timing)
  e['verification']={'status':'Confirmed' if confirmed else 'Developing / Unverified','primary_source_ids':primary,'independent_sources':len(families),'independent_confirmation':len(families)>=2,'publication_times':[s.get('published_at') for s in selected],'event_time':e.get('event_time'),'timing_verified':timing,'primary_search_reason':None if primary else 'Primary source not verified in retrieved evidence; discovery/search failure remains in article ledger.','confidence':e['confidence'] if confirmed else 'Low'}
  if not confirmed:e['confidence']='Low'
  groups['confirmed' if confirmed else 'developing'].append(e['id'])
  stages=[('EVENT','facts'),('FIRST-ORDER EFFECT','why_it_matters'),('SECOND-ORDER EFFECT','transmission'),('SECTOR EXPOSURE','transmission'),('COMPANY EXPOSURE','stocks'),('POSSIBLE EARNINGS IMPACT','fundamentals'),('VALUATION / MARKET IMPACT','transmission')]
  path=[]
  for label,field in stages:
   choices=e.get(field,[])
   if field=='transmission':
    allowed={'SECOND-ORDER EFFECT':['Macro variable','Business impact'],'SECTOR EXPOSURE':['Sector'],'VALUATION / MARKET IMPACT':['Potential market impact']}[label]
    choices=[u for u in choices if u.get('stage') in allowed]
   if choices:
    u=choices[0];status='Confirmed' if u['tag']=='FACT' and confirmed else 'Supported Analysis' if u['tag']=='ANALYSIS' and confirmed else 'Hypothesis' if u['tag']=='HYPOTHESIS' else 'Plausible Mechanism'
    path.append({**u,'stage':label,'support_status':status})
   else:path.append({'stage':label,'text':'검증된 연결 근거가 아직 없다.','tag':'UNCERTAINTY','evidence_ids':[],'support_status':'Unsupported'})
  e['transmission_map']=path;e['transmission_scenarios']=[]
  # Reuse only reviewed components; no new model assertions are smuggled into a scenario.
  if confirmed and e.get('invalidation') and e.get('transmission') and e.get('stocks'):
   for field,label in [('base','BASE'),('bull','UPSIDE'),('bear','DOWNSIDE')]:
    if not e.get(field):continue
    u=e[field][0]
    e['transmission_scenarios'].append({'name':label,'trigger':u,'transmission':e['transmission'],'assets':[x['ticker'] for x in e.get('stocks',[])],'evidence_ids':list(dict.fromkeys(u['evidence_ids']+[f for x in e['transmission'] for f in x['evidence_ids']])),'invalidation':e['invalidation']})
 return groups

def build(r,calendar=None):
 raw=normalize(r['market']);pool=r['evidence'];m,basis=completed_market(raw,pool);breadth,contributors=constituents(m,pool);curves=spreads(m,pool)
 r['sources']=list({s['id']:s for s in r['sources']+m['sources']}.values())
 regimes=regime(m,pool);cross=cross_asset(m,pool);sector=sectors(m,pool);groups=event_enrichment(r)
 calendar=calendar or m.get('calendar') or {'items':[],'sources':[],'ledger':[],'missing':['Date Not Verified — no official calendar collected']}
 r['sources']=list({s['id']:s for s in r['sources']+calendar['sources']}.values())
 for item in calendar['items']:
  fid=ident('calendar',item['id']);text=item['event']+' scheduled '+str(item['date'])+' '+str(item.get('time') or 'time not verified')
  pool[fid]={'id':fid,'text':text,'quote':text,'tag':'FACT','confirmed':True,'source_ids':[item['source_id']],'kind':'scheduled_event','observation_time':item['collected_at']};item['evidence_ids']=[fid]
 candidates=[]
 for c in cross:
  if c['status']=='UNVERIFIED' or not c['evidence_ids']:continue
  horizon='20' if c['windows']['20'].get('available') else '5';w=c['windows'][horizon];scaled=[]
  for key,value in zip(c['assets'],w.get('changes',[])):
   a=m['assets'][key];vol=a.get('realized_daily_volatility_20d')
   if not finite(vol) and a.get('kind')=='spread':
    diffs=[b['value']-a['value'] for a,b in zip(a['history'][-22:-1],a['history'][-21:])];vol=statistics.stdev(diffs) if len(diffs)>1 else None
   if finite(vol) and vol>0:scaled.append(abs(value)/(vol*math.sqrt(int(horizon))))
  movement=max(scaled,default=0)
  if movement<.1:continue
  rate_related=any(m['assets'][k].get('kind') in ('yield','spread') for k in c['assets'])
  dimensions={'market_impact':min(3,int(movement>1)+int(movement>2)+int(movement>3)),'breadth_of_impact':2,'persistence':int(all(x['available'] for x in c['windows'].values())),'evidence_quality':2 if c['confidence']['level']=='Medium' else 1,'canadian_relevance':2 if any(k.startswith(('ca','tsx')) for k in c['assets']) else 1,'macro_significance':2 if rate_related else 1,'earnings_implications':int('oil' in c['id'] or 'materials' in c['id']),'policy_implications':int(rate_related),'cross_asset_confirmation':2 if c['status']=='CONSISTENT WITH' else 1}
  observation=horizon+'D '+w['start']+' → '+w['end']+': '+' / '.join(m['assets'][key]['label']+' '+f'{value:+.2f}'+('bp' if m['assets'][key].get('kind') in ('yield','spread') else '%') for key,value in zip(c['assets'],w['changes']))
  candidates.append({'id':c['id'],'title':c['title'],'tag':'ANALYSIS','text':c['text'],'evidence_summary':observation,'why_it_matters':c['mechanism'],'evidence_ids':c['evidence_ids'],'assets':c['assets'],'confidence':c['confidence'],'invalidation':c['invalidation'],'status':c['status'],'priority_dimensions':dimensions,'priority_score':sum(dimensions.values()),'group':'rates_fx' if rate_related else 'commodities' if any(k in ('wti','gold','copper') for k in c['assets']) else 'equities'})
 for e in r['events']:
  if e['id'] not in groups['confirmed'] or not e.get('why_it_matters') or not e.get('invalidation'):continue
  u=e['why_it_matters'][0];d={'market_impact':{'High':3,'Medium':2,'Low':1}[e['impact']],'breadth_of_impact':int(e['relevance'] in 'AB')+1,'persistence':1,'evidence_quality':3 if e['verification']['primary_source_ids'] else 2,'canadian_relevance':2,'macro_significance':int(e['relevance'] in 'AD')+1,'earnings_implications':bool(e.get('fundamentals')),'policy_implications':int(e.get('category')=='Macro'),'cross_asset_confirmation':int(bool(e.get('supporting_market_data')))}
  candidates.append({'id':e['id'],'title':e['title'],'tag':'ANALYSIS','text':u['text'],'why_it_matters':u['text'],'evidence_ids':u['evidence_ids'],'assets':[x['ticker'] for x in e.get('stocks',[])],'confidence':{'level':e['confidence'],'dimensions':e['verification']},'invalidation':e['invalidation'][0]['text'],'status':'Confirmed development; interpretation separately tagged','priority_dimensions':d,'priority_score':sum(d.values()),'group':'event:'+e['id']})
 top=[];seen=set()
 for c in sorted(candidates,key=lambda c:(-c['priority_score'],c['id'])):
  if c['group'] in seen:continue
  top.append(c);seen.add(c['group'])
  if len(top)==3:break
 overview=[]
 for name in ('equity','rates','cad','volatility','commodity'):
  value=regimes[name]
  if value['evidence_ids'] and value['classification']!='Unable to Classify':overview.append(claim(f"{name}: {value['classification']}. {value['reason']}",value['evidence_ids']))
 primary=next((c for c in cross if c['id']=='equities_yields' and c['status']!='UNVERIFIED'),None)
 if primary and regimes['rates']['classification'] in ('Rising','Rapidly Rising'):risk=claim('금리 상승이 지속되면 할인율과 차입 비용 부담이 커질 수 있다. 주가·금리 관측은 '+primary['status']+'이며, 실적 전망·위험 프리미엄이 이를 상쇄하는지 확인한다.',primary['evidence_ids'],'HYPOTHESIS')
 elif regimes['volatility']['classification'] in ('Elevated','Stressed'):risk=claim('변동성이 과거 분포보다 높은 상태다. 이 상태가 지속되면 가격 변동과 헤지 비용 부담이 이어질 수 있으나 손실 확률을 추정하지 않는다.',regimes['volatility']['evidence_ids'],'HYPOTHESIS')
 elif regimes['cad']['classification']=='Weakening' and regimes['commodity']['classification']=='Inflationary Pressure':risk=claim('CAD 약세와 원자재 가격 상승이 함께 지속되면 수입 원가 부담이 커질 수 있다. 실제 마진은 헤지·계약·가격 전가 능력을 추가 확인해야 한다.',regimes['cad']['evidence_ids']+regimes['commodity']['evidence_ids'],'HYPOTHESIS')
 else:risk=claim('주가·금리·원자재의 현재 관계가 반전될 경우 기존 가격 해석을 재검토해야 한다. 구체적인 관점 변경 조건은 관계별로 제시했다.',list(dict.fromkeys(f for c in top for f in c['evidence_ids'])),'HYPOTHESIS') if top else claim('할인율·실적·시장 참여도를 함께 검증할 정보가 부족하다. 누락된 입력을 보완한 뒤 위험 판단을 갱신한다.',[],'UNCERTAINTY')
 supportive=next((c for c in cross if c['id'] in ('tsx_oil','cad_oil','equities_volatility') and c['status']=='CONSISTENT WITH' and c['windows'].get('20',{}).get('available') and c['windows']['20']['changes'][0]>0),None)
 support=claim(supportive['title']+' 관측은 해당 지지 경로와 일치한다. '+supportive['mechanism'],supportive['evidence_ids']) if supportive else claim('검증된 지지 요인은 특정하지 못했다. 방향이 섞인 관측과 미확보 자료는 상세 관계 표에 남겼다.',[],'UNCERTAINTY')
 synthesis={'version':VERSION,'created_from':m['as_of'],'analysis_basis':basis,'analysis_assets':{k:{f:a.get(f) for f in ('kind','label','observed_at')} for k,a in m['assets'].items()},'daily_move':daily_move(raw,pool,breadth),'market_regime':regimes,'cross_asset_read':cross,'overall_read':overview[:5],'top_developments':top,'primary_risk':risk,'primary_opportunity_or_supportive_factor':support,'next_catalysts':calendar['items'],'calendar':calendar,'rates':curves,'sector_dispersion':sector,'breadth':breadth,'contributors':contributors,'event_groups':groups,'event':[e['id'] for e in r['events']],'confidence':confidence_for(m,['tsx','ca10y','us10y','cadusd'],refs(pool,['tsx','ca10y','us10y','cadusd'])),'methodology':{'version':VERSION,'daily':'Move/mean-absolute and move/std require corroboration. Normal ≤1 with volume ≤1.25; significant ≥2 plus one confirmation; extreme ≥3 plus two.','equity':'All three equity indices must clear 1× daily mean-absolute at 5D and 2× at 20D with the same sign. Price-based, not breadth-confirmed risk appetite.','rates':'Median 5D>15bp and 20D>30bp plus ≥3 rising yields = rapidly rising; 20D>10bp with positive 5D and ≥3 yields = rising; inverse = falling.','cad':'5D ±0.2% and 20D ±0.5% with same sign.','commodity':'At least three of WTI/Brent/copper/gas agree across 5D and 20D. Energy series are not independent confirmations.','curves':'Shape flat within ±10bp; steepening/flattening beyond ±5bp 20D. No recession probability.','confidence':'Descriptive evidence assessment, not a calibrated prediction probability. Single-source data cannot establish causation.'},'data_quality':[{'key':k,'observation_date':a.get('observed_at'),'flags':a.get('quality_flags',[]),'instrument':a.get('instrument_type'),'roll_warning':a.get('roll_warning')} for k,a in raw['assets'].items()]}
 r['synthesis']=synthesis
 if not r['company'].get('enabled'):
  r['executive']['top3']=[claim(c['why_it_matters'],c['evidence_ids']) for c in top];r['executive']['key_risk']=risk;r['executive']['confidence']=synthesis['confidence']['level']
 return synthesis
