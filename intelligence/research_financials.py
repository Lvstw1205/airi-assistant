"""Period/currency-aware three-statement model; actuals never become forecasts."""
import datetime as dt,math,re,statistics
from .research_schema import finite,ident,source,claim
from .research_market import cached,json_get
FIELDS={
 'income':{'revenue':['Total Revenue','Operating Revenue'],'gross_profit':['Gross Profit'],'operating_income':['Operating Income'],'ebitda':['EBITDA'],'net_income':['Net Income'],'eps':['Diluted EPS'],'shares':['Diluted Average Shares'],'interest_expense':['Interest Expense'],'tax_expense':['Tax Provision'],'pretax_income':['Pretax Income'],'one_time_items':['Total Unusual Items']},
 'balance':{'cash':['Cash And Cash Equivalents'],'current_assets':['Current Assets'],'total_assets':['Total Assets'],'debt':['Total Debt'],'current_liabilities':['Current Liabilities'],'total_liabilities':['Total Liabilities Net Minority Interest'],'equity':['Stockholders Equity'],'receivables':['Accounts Receivable','Net Receivables'],'inventory':['Inventory']},
 'cashflow':{'ocf':['Operating Cash Flow'],'capex':['Capital Expenditure'],'investing_cf':['Investing Cash Flow'],'financing_cf':['Financing Cash Flow'],'dividends':['Cash Dividends Paid'],'buybacks':['Repurchase Of Capital Stock'],'debt_issuance':['Issuance Of Debt'],'debt_repayment':['Repayment Of Debt'],'fx_cash':['Effect Of Exchange Rate Changes'],'cash_change':['Changes In Cash']}}
LABELS={'revenue':'Revenue','gross_profit':'Gross Profit','operating_income':'Operating Income','ebitda':'EBITDA','net_income':'Net Income','eps':'Diluted EPS','shares':'Diluted Shares','cash':'Cash','current_assets':'Current Assets','total_assets':'Total Assets','debt':'Debt','current_liabilities':'Current Liabilities','total_liabilities':'Total Liabilities','equity':'Equity','ocf':'Operating Cash Flow','capex':'Capex','fcf':'Free Cash Flow','investing_cf':'Investing Cash Flow','financing_cf':'Financing Cash Flow','dividends':'Dividends','buybacks':'Share Buybacks','debt_issuance':'Debt Issuance','debt_repayment':'Debt Repayment','net_debt':'Net Debt','working_capital':'Working Capital','revenue_growth':'Revenue Growth','gross_margin':'Gross Margin','operating_margin':'Operating Margin','eps_growth':'EPS Growth','fcf_margin':'FCF Margin','net_debt_ebitda':'Net Debt / EBITDA','roe':'ROE','roic':'ROIC','current_ratio':'Current Ratio','dividend_growth':'Dividend Growth','share_count_change':'Share Count Change','nim':'NIM','cet1':'CET1','pcl':'Provision for Credit Losses','loan_growth':'Loan Growth','deposit_growth':'Deposit Growth','production':'Production','realized_price':'Realized Price','operating_cost':'Operating Cost','arr':'ARR','nrr':'NRR','rule40':'Rule of 40'}
LABELS.update({'interest_expense':'Interest Expense','tax_expense':'Tax Expense','pretax_income':'Pretax Income','one_time_items':'Unusual Items','receivables':'Accounts Receivable','inventory':'Inventory','fx_cash':'FX Effect on Cash','cash_change':'Change in Cash'})
TEMPLATES={'bank':['net_income','eps','roe','nim','cet1','pcl','loan_growth','deposit_growth'], 'energy':['production','realized_price','operating_cost','fcf','capex','net_debt','revenue_growth'], 'saas':['arr','revenue_growth','gross_margin','nrr','fcf_margin','rule40'], 'general':['revenue_growth','gross_margin','operating_margin','eps_growth','ocf','fcf','fcf_margin','net_debt','net_debt_ebitda','roe','roic','current_ratio','dividend_growth','share_count_change']}

def resolve_company(name):
 import yfinance as yf
 if not isinstance(name,str) or not name.strip():return None
 q=name.strip()
 if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}',q):
  info=yf.Ticker(q).get_info()
  if info.get('quoteType')=='EQUITY' and info.get('symbol')==q:return q
 matches=yf.Search(q,max_results=6,news_count=0).quotes
 matches=[r for r in matches if r.get('quoteType')=='EQUITY' and r.get('exchange') in ('TOR','NMS','NYQ','NGM','NCM','ASE')]
 exact=[r for r in matches if q.casefold() in [str(r.get(k,'')).casefold() for k in ('symbol','shortname','longname')]]
 selected=exact or [r for r in matches if q.casefold() in (r.get('longname') or r.get('shortname') or '').casefold()]
 canadian=[r for r in selected if r.get('exchange')=='TOR']
 candidates=canadian or selected
 return candidates[0]['symbol'] if len(candidates)==1 else None

def provider(symbol):
 import yfinance as yf
 t=yf.Ticker(symbol);info=t.get_info();currency=info.get('financialCurrency');collected=dt.datetime.now(dt.timezone.utc).isoformat();records=[];issues=[]
 if not currency:raise ValueError('Statement currency unavailable; quote currency is not a substitute')
 for frequency,prefix in [('annual',''),('quarterly','quarterly_')]:
  for group,attr in [('income','income_stmt'),('balance','balance_sheet'),('cashflow','cashflow')]:
   try:
    frame=getattr(t,prefix+attr)
    for stamp in frame.columns[:12]:
     for metric,aliases in FIELDS[group].items():
      for alias in aliases:
       if alias not in frame.index:continue
       value=float(frame.loc[alias,stamp])
       if finite(value):
        records.append({'metric':metric,'value':value,'period_end':stamp.date().isoformat(),'frequency':frequency,'currency':currency,'statement':group,'provider_label':alias,'kind':'Historical Actual'});break
   except Exception as error:issues.append(prefix+attr+': '+type(error).__name__)
 expectations=[]
 try:
  frame=t.earnings_history
  for period,row in frame.iterrows():
   actual=float(row.get('epsActual',float('nan')));estimate=float(row.get('epsEstimate',float('nan')))
   if finite(actual) and finite(estimate):expectations.append({'metric':'eps','period_end':period.date().isoformat(),'frequency':'quarterly','currency':currency,'value':estimate,'provider_actual':actual,'kind':'Analyst Consensus','source_url':'https://finance.yahoo.com/quote/'+symbol+'/analysis/'})
 except Exception:issues.append('Historical consensus unavailable')
 return {'symbol':symbol,'name':info.get('longName') or info.get('shortName') or symbol,'sector':info.get('sector'),'industry':info.get('industry'),'currency':currency,'collected_at':collected,'records':records,'expectations':expectations,'issues':issues}

def sec_confirmation(symbol,records,now,get_json=json_get):
 """Read-only primary check for matching US tickers; never coerce IFRS/custom tags."""
 if symbol.endswith(('.TO','.V')):return {'status':'unavailable','reason':'Canadian IFRS/SEDAR or issuer filing adapter required; secondary statement figures are not independently confirmed.'}
 try:
  index=get_json('https://www.sec.gov/files/company_tickers.json');matches=[v for v in index.values() if v.get('ticker')==symbol]
  if len(matches)!=1:return {'status':'unavailable','reason':'No exact SEC ticker mapping'}
  cik=str(matches[0]['cik_str']).zfill(10);url='https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json';data=get_json(url)
  tags={'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues'],'net_income':['NetIncomeLoss'],'operating_income':['OperatingIncomeLoss'],'cash':['CashAndCashEquivalentsAtCarryingValue'],'total_assets':['Assets'],'equity':['StockholdersEquity'],'ocf':['NetCashProvidedByUsedInOperatingActivities'],'eps':['EarningsPerShareDiluted']}
  matches=[];conflicts=[]
  for r in records:
   units='USD/shares' if r['metric']=='eps' else r['currency']
   for tag in tags.get(r['metric'],[]):
    rows=data.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).get(units,[])
    candidates=[]
    for row in rows:
     if row.get('end')!=r['period_end'] or row.get('filed','9999')>now.date().isoformat():continue
     days=(dt.date.fromisoformat(row['end'])-dt.date.fromisoformat(row['start'])).days if row.get('start') else None
     if r['statement']!='balance' and not ((r['frequency']=='annual' and days and 330<=days<=380) or (r['frequency']=='quarterly' and days and 65<=days<=105)):continue
     candidates.append(row)
    if not candidates:continue
    row=max(candidates,key=lambda x:x.get('filed',''));entry={'record_id':r['id'],'tag':tag,'filed':row['filed'],'accession':row.get('accn'),'value':row['val'],'period_end':row['end']}
    (matches if abs(row['val']-r['value'])<=max(.01,abs(r['value'])*1e-6) else conflicts).append(entry);break
  return {'status':'checked','source':source(url,'SEC companyfacts · '+symbol,1,now.isoformat()),'matches':matches,'conflicts':conflicts}
 except Exception as error:return {'status':'unavailable','reason':'SEC primary check unavailable: '+type(error).__name__}

def prepare(data,now=None):
 now=now or dt.datetime.now(dt.timezone.utc);symbol=data['symbol'];origin=source('https://finance.yahoo.com/quote/'+symbol+'/financials/','Yahoo Finance statements · '+symbol,3,data['collected_at'],currency=data['currency'])
 records=[];pool={}
 for raw in data['records']:
  if not finite(raw.get('value')) or raw['period_end']>now.date().isoformat() or raw.get('currency')!=data['currency'] or raw.get('kind')!='Historical Actual':continue
  r=dict(raw);r['id']=ident('f',symbol,r['metric'],r['period_end'],r['frequency']);r['source_ids']=[origin['id']];r['collected_at']=data['collected_at'];r['filing_time']=None
  records.append(r);text=f"{symbol} {r['frequency']} {r['period_end']} {r['metric']}: {r['value']:.10g} {r['currency']}"
  pool[r['id']]={**r,'text':text,'quote':text,'tag':'FACT','confirmed':False,'period_end':r['period_end'],'observation_time':r['period_end']}
 industry=(data.get('industry') or '').lower();sector=(data.get('sector') or '').lower()
 template='bank' if 'bank' in industry else 'energy' if sector=='energy' else 'saas' if 'software' in industry else 'general'
 issues=list(data.get('issues',[]));derived=[]
 by={}
 for r in records:by.setdefault((r['frequency'],r['period_end']),{})[r['metric']]=r
 def add(values,key,value,inputs,formula,unit='percent'):
  if not finite(value):return
  refs=[values[i]['id'] for i in inputs];base=values[inputs[0]]
  row={'id':ident('k',symbol,key,base['frequency'],base['period_end']),'metric':key,'value':value,'currency':base['currency'],'unit':unit,'frequency':base['frequency'],'period_end':base['period_end'],'kind':'Historical Actual','evidence_ids':refs,'source_ids':[origin['id']],'formula':formula}
  derived.append(row);values[key]=row;pool[row['id']]={**row,'text':f"{symbol} {row['period_end']} {key}: {value:.10g} {unit}; formula {formula}",'quote':'','tag':'FACT','confirmed':False,'observation_time':row['period_end']}
 for (freq,period),v in by.items():
  def valid(*keys):return all(k in v and finite(v[k]['value']) for k in keys)
  def x(k):return v[k]['value']
  for key,a,b in [('gross_margin','gross_profit','revenue'),('operating_margin','operating_income','revenue')]:
   if valid(a,b) and x(b)>0:add(v,key,100*x(a)/x(b),[a,b],a+' / '+b+' * 100')
  if valid('ocf','capex'):add(v,'fcf',x('ocf')-abs(x('capex')),['ocf','capex'],'OCF - abs(reported capex)',data['currency'])
  if valid('fcf','revenue') and x('revenue')>0:add(v,'fcf_margin',100*x('fcf')/x('revenue'),['fcf','revenue'],'FCF / revenue * 100')
  if valid('debt','cash'):add(v,'net_debt',x('debt')-x('cash'),['debt','cash'],'total debt - cash',data['currency'])
  if valid('current_assets','current_liabilities'):
   add(v,'working_capital',x('current_assets')-x('current_liabilities'),['current_assets','current_liabilities'],'current assets - current liabilities',data['currency'])
   if x('current_liabilities')>0 and template!='bank':add(v,'current_ratio',x('current_assets')/x('current_liabilities'),['current_assets','current_liabilities'],'current assets / current liabilities','x')
  if freq=='annual' and template!='bank' and valid('net_debt','ebitda') and x('ebitda')>0:add(v,'net_debt_ebitda',x('net_debt')/x('ebitda'),['net_debt','ebitda'],'net debt / annual EBITDA','x')
  if valid('total_assets','total_liabilities','equity') and abs(x('total_assets')-x('total_liabilities')-x('equity'))>max(1,abs(x('total_assets'))*.0001):issues.append('Balance-sheet identity mismatch: '+freq+' '+period+'; possible differing equity/minority-interest definitions')
 # Growth and ROE require matched fiscal frequency, currency and a genuine prior year.
 for (freq,period),v in by.items():
  previous=next((pv for (pf,pp),pv in by.items() if pf==freq and 330<=(dt.date.fromisoformat(period)-dt.date.fromisoformat(pp)).days<=400),None)
  if previous:
   for metric,key in [('revenue','revenue_growth'),('eps','eps_growth'),('dividends','dividend_growth'),('shares','share_count_change')]:
    if metric in v and metric in previous and (previous[metric]['value']>0 or (metric=='dividends' and previous[metric]['value']<0)):
     old=previous[metric];v['_previous_'+metric]=old;add(v,key,100*(v[metric]['value']/old['value']-1),[metric,'_previous_'+metric],'matched-period YoY change * 100')
   if freq=='annual' and all(k in v for k in ('net_income','equity')) and 'equity' in previous:
    avg=(v['equity']['value']+previous['equity']['value'])/2
    if avg>0:v['_prior_equity']=previous['equity'];add(v,'roe',100*v['net_income']['value']/avg,['net_income','equity','_prior_equity'],'annual net income / average beginning and ending equity * 100')
  if freq=='annual' and template!='bank' and previous and all(k in v and k in previous for k in ('debt','equity','cash')) and all(k in v for k in ('operating_income','tax_expense','pretax_income')):
   pretax=v['pretax_income']['value'];tax=v['tax_expense']['value']/pretax if pretax>0 else None
   capital=sum(v[k]['value']+previous[k]['value'] for k in ('debt','equity'))/2-(v['cash']['value']+previous['cash']['value'])/2
   if tax is not None and 0<=tax<=1 and capital>0:
    for key in ('debt','equity','cash'):v['_prior_'+key]=previous[key]
    add(v,'roic',100*v['operating_income']['value']*(1-tax)/capital,['operating_income','tax_expense','pretax_income','debt','equity','cash','_prior_debt','_prior_equity','_prior_cash'],'NOPAT using reported effective tax / average (debt + equity - cash); specified approximation')
  if template=='saas' and all(k in v for k in ('revenue_growth','fcf_margin')):add(v,'rule40',v['revenue_growth']['value']+v['fcf_margin']['value'],['revenue_growth','fcf_margin'],'YoY revenue growth + FCF margin (specified variant)')
 result={'enabled':True,'symbol':symbol,'name':data['name'],'currency':data['currency'],'sector':data.get('sector'),'industry':data.get('industry'),'template':template,'sources':[origin],'records':records,'derived':derived,'evidence':pool,'issues':issues,'expectations':[],'comparisons':[],'connections':[],'quality_flags':[],'guidance_status':'Not Available — no verified numeric company-guidance source ingested','consensus_status':'Not Available','forecast':{'enabled':False,'reason':'Requires matched historical statements and explicit supported assumptions; no automatic growth rates or probabilities.'}}
 for exp in data.get('expectations',[]):
  actual=next((r for r in records if all(r.get(k)==exp.get(k) for k in ('metric','period_end','frequency','currency'))),None)
  if not actual or not finite(exp.get('value')) or abs(actual['value']-exp.get('provider_actual',float('inf')))>max(.001,abs(actual['value'])*.001):continue
  es=source(exp['source_url'],'Yahoo historical analyst consensus',3,data['collected_at']);result['sources'].append(es)
  e={**exp,'id':ident('expectation',symbol,exp['metric'],exp['period_end']),'source_ids':[es['id']]};result['expectations'].append(e);pool[e['id']]={**e,'text':f"{exp['period_end']} analyst EPS consensus {exp['value']} {exp['currency']}",'quote':'','tag':'FACT','confirmed':False};result['consensus_status']='Matched historical EPS consensus only'
  result['comparisons'].append({'metric':exp['metric'],'period_end':exp['period_end'],'basis':'Analyst Consensus','actual':actual['value'],'comparison':exp['value'],'difference':actual['value']-exp['value'],'percent':100*(actual['value']/exp['value']-1) if exp['value']>0 else None,'evidence_ids':[actual['id'],e['id']]})
 for freq in ('quarterly','annual'):
  periods=sorted([p for f,p in by if f==freq],reverse=True)
  if not periods:continue
  current=by[(freq,periods[0])]
  for offset,label in [(1,'Previous Quarter' if freq=='quarterly' else 'Previous Year'),(4,'Previous Year')]:
   if offset>=len(periods) or (freq=='annual' and offset==4):continue
   gap=(dt.date.fromisoformat(periods[0])-dt.date.fromisoformat(periods[offset])).days
   if not ((offset==1 and freq=='quarterly' and 65<=gap<=105) or (label=='Previous Year' and 330<=gap<=400)):continue
   previous=by[(freq,periods[offset])]
   for metric in ('revenue','gross_margin','operating_margin','net_income','eps','ocf','capex','fcf','debt','receivables','inventory','shares'):
    if metric not in current or metric not in previous:continue
    a,b=current[metric],previous[metric];result['comparisons'].append({'metric':metric,'period_end':periods[0],'frequency':freq,'basis':label,'actual':a['value'],'comparison':b['value'],'difference':a['value']-b['value'],'percent':100*(a['value']/b['value']-1) if b['value']>0 else None,'evidence_ids':[a['id'],b['id']]})
  for inputs,text in [(['revenue','operating_income','ocf','cash'],'매출·영업이익·영업현금흐름·현금잔액을 같은 기간으로 연결했다. 현금 증가의 원인은 투자·조달·환율 항목까지 대조해야 한다.'),(['net_income','ocf','capex','fcf'],'순이익과 영업현금흐름은 다른 지표다. 여기의 잉여현금흐름은 영업현금흐름에서 설비투자 지출을 차감한 계산값이다.')]:
   if all(k in current for k in inputs):result['connections'].append(claim(text,[current[k]['id'] for k in inputs],period_end=periods[0],frequency=freq))
  comparisons={c['metric']:c for c in result['comparisons'] if c.get('frequency')==freq and c['basis']==('Previous Quarter' if freq=='quarterly' else 'Previous Year')}
  if all(k in current for k in ('ocf','investing_cf','financing_cf','fx_cash','cash_change')):
   total=sum(current[k]['value'] for k in ('ocf','investing_cf','financing_cf','fx_cash'));diff=total-current['cash_change']['value']
   refs=[current[k]['id'] for k in ('ocf','investing_cf','financing_cf','fx_cash','cash_change')]
   result['connections'].append(claim('영업·투자·조달·환율 현금흐름 합계와 보고된 현금 변동액을 대조했다. '+('일치한다.' if abs(diff)<=max(1,abs(total)*.0001) else '차이가 있어 분류·연결 범위 확인이 필요하다.'),refs,period_end=periods[0],frequency=freq))
  if template!='bank':
   for a,b,text in [('revenue','ocf','매출은 늘었지만 영업현금흐름은 줄었다. 운전자본·비현금 항목을 확인해야 하며, 이것만으로 원인을 확정하지 않는다.'),('net_income','fcf','순이익 증가와 잉여현금흐름 감소가 동시에 나타났다. 투자지출과 운전자본을 따로 점검해야 한다.'),('debt','fcf','부채 증가와 잉여현금흐름 감소가 함께 나타났다. 차입 목적은 공시로 확인해야 한다.')]:
    if a in comparisons and b in comparisons and comparisons[a]['difference']>0 and comparisons[b]['difference']<0:result['quality_flags'].append(claim(text,comparisons[a]['evidence_ids']+comparisons[b]['evidence_ids'],period_end=periods[0],frequency=freq))
   for a,text in [('receivables','매출채권 증가율이 매출 증가율보다 높다. 회수 기간과 계절성을 추가 확인해야 한다.'),('inventory','재고 증가율이 매출 증가율보다 높다. 수요·재고평가·계절성을 확인해야 한다.')]:
    if a in comparisons and 'revenue' in comparisons and comparisons[a]['percent'] is not None and comparisons['revenue']['percent'] is not None and comparisons[a]['percent']>comparisons['revenue']['percent']:result['quality_flags'].append(claim(text,comparisons[a]['evidence_ids']+comparisons['revenue']['evidence_ids'],period_end=periods[0],frequency=freq))
  if 'eps' in comparisons and 'shares' in comparisons and comparisons['eps']['difference']>0 and comparisons['shares']['difference']<0:result['quality_flags'].append(claim('EPS 상승과 희석 주식 수 감소가 함께 관측됐다. 자사주 매입이 주된 원인이었는지는 별도 검증이 필요하다.',comparisons['eps']['evidence_ids']+comparisons['shares']['evidence_ids'],period_end=periods[0],frequency=freq))
  if 'one_time_items' in current and current['one_time_items']['value']!=0:result['quality_flags'].append(claim('일회성 항목이 보고됐다. 조정 전후 이익을 확인하기 전에는 마진 개선의 지속성을 단정하지 않는다.',[current['one_time_items']['id']],period_end=periods[0],frequency=freq))
 if template=='bank':result['issues'].append('은행은 예금·대출의 현금흐름 특성이 다르다. 일반 기업의 OCF/FCF, 순부채/EBITDA 기준으로 이익의 질을 평가하지 않는다.')
 available={r['metric'] for r in records+derived};result['kpi_metrics']=TEMPLATES[template];result['missing_kpis']=[k for k in result['kpi_metrics'] if k not in available]
 result['sources']=list({s['id']:s for s in result['sources']}.values());result['forecast']=forecast_module(result);return result

def collect(company,root,now=None,loader=None,primary_check=True):
 now=now or dt.datetime.now(dt.timezone.utc)
 symbol=company if loader else resolve_company(company)
 if not symbol:return {'enabled':True,'available':False,'requested_company':company,'reason':'Company identity or exchange ambiguous; no guessed ticker or statements.'}
 try:
  data=cached(root,'statements-v2:'+symbol,3600,lambda:(loader or provider)(symbol));result=prepare(data,now);result['available']=bool(result['records'])
  check=sec_confirmation(symbol,result['records'],now) if primary_check else {'status':'not_run','reason':'Fixture / offline run'}
  result['primary_confirmation']=check
  if check.get('source'):result['sources'].append(check['source'])
  for verified in check.get('matches',[]):
   f=result['evidence'][verified['record_id']];f['source_ids'].append(check['source']['id']);f['confirmed']=True;f['filing_time']=verified['filed']
  if check.get('conflicts'):result['issues'].append('Primary filing conflicts detected; affected figures require review and are not confirmed.')
  return result
 except Exception as error:return {'enabled':True,'available':False,'requested_company':company,'reason':type(error).__name__+': '+str(error)[:160]}

def forecast_module(financials):
 """One illustrative annual bridge, only with a complete eight-quarter baseline.
 No price targets, probabilities, consensus labels, or free-form model arithmetic.
 """
 if financials['template']=='bank':return {'enabled':False,'reason':'Bank forecasts require NIM, earning assets, credit losses and capital data; no generic industrial-company forecast.'}
 records=financials['records'];quarter={}
 for r in records:
  if r['frequency']=='quarterly':quarter.setdefault(r['period_end'],{})[r['metric']]=r
 periods=sorted(quarter)[-8:];need=['revenue','operating_income','net_income','shares','ocf','capex','debt','cash']
 if len(periods)<8 or any(not all(k in quarter[p] for k in need) for p in periods):return {'enabled':False,'reason':'Eight complete comparable quarters for revenue, margins, shares, cash flow, capex and net debt are not available.'}
 if any(not 65<=(dt.date.fromisoformat(b)-dt.date.fromisoformat(a)).days<=105 for a,b in zip(periods,periods[1:])):return {'enabled':False,'reason':'Quarter sequence has gaps; forecast withheld.'}
 rows=[quarter[p] for p in periods];v=lambda row,k:row[k]['value']
 if any(v(r,'revenue')<=0 or v(r,'shares')<=0 or v(r,'operating_income')<=0 for r in rows):return {'enabled':False,'reason':'Nonpositive denominators prevent a defensible ratio bridge.'}
 growth=[v(rows[i],'revenue')/v(rows[i-4],'revenue')-1 for i in range(4,8)]
 opm=[v(r,'operating_income')/v(r,'revenue') for r in rows];conversion=[v(r,'ocf')/v(r,'revenue') for r in rows];capex=[abs(v(r,'capex'))/v(r,'revenue') for r in rows];netratio=[v(r,'net_income')/v(r,'operating_income') for r in rows]
 ttm=sum(v(r,'revenue') for r in rows[-4:]);latest=rows[-1];cases=[];ids=list(dict.fromkeys(r[k]['id'] for r in rows for k in need))
 for name,fn in [('Bear',min),('Base',statistics.median),('Bull',max)]:
  g=fn(growth);margin=fn(opm);rev=ttm*(1+g);oi=rev*margin;ni=oi*statistics.median(netratio);ocf=rev*fn(conversion);cx=rev*statistics.median(capex);fcf=ocf-cx
  cases.append({'name':name,'kind':'Illustrative Scenario','revenue':rev,'margin':margin*100,'operating_income':oi,'net_income':ni,'eps':ni/v(latest,'shares'),'ocf':ocf,'capex':cx,'fcf':fcf,'net_debt':v(latest,'debt')-v(latest,'cash')-fcf,'evidence_ids':ids,'growth_assumption':g*100})
 return {'enabled':True,'kind':'Illustrative Scenario','horizon':'Next 12 months, static historical-range sensitivity; not a prediction','assumptions':['Revenue growth, operating margin and OCF/revenue use historical minimum / median / maximum, without probabilities.','Net income / operating income and capex/revenue held at eight-quarter historical medians; diluted shares held at latest reported level.','No dividends, buybacks, acquisitions, debt FX or other financing assumed; all FCF reduces net debt. This assumption is explicit, not company guidance.'],'cases':cases,'evidence_ids':ids}

def executive_findings(f):
 """Calculated comparisons, with no invented operational cause."""
 if not f.get('available'):return []
 result=[];latest=max((x['period_end'] for x in f['records'] if x['frequency']=='quarterly'),default=None)
 def format_value(v):return (f'{v/1e9:.2f}B' if abs(v)>=1e9 else f'{v/1e6:.2f}M' if abs(v)>=1e6 else f'{v:.2f}')+' '+f['currency']
 rev=next((c for c in f['comparisons'] if c['metric']=='revenue' and c.get('frequency')=='quarterly' and c['period_end']==latest and c['basis']=='Previous Year'),None)
 if rev:
  growth=f" (YoY {(rev['actual']/rev['comparison']-1)*100:+.2f}%)" if rev['comparison']>0 else ''
  result.append(claim(f"{latest} 분기 매출은 {format_value(rev['actual'])}{growth}, 전년 같은 분기는 {format_value(rev['comparison'])}였다. 물량·가격·환율별 원인 분해는 별도 공시 근거가 필요하다.",rev['evidence_ids']))
 vals={x['metric']:x for x in f['records']+f['derived'] if x['period_end']==latest and x['frequency']=='quarterly'}
 if all(k in vals for k in ('net_income','eps')):result.append(claim(f"동일 분기 순이익은 {format_value(vals['net_income']['value'])}, 희석 EPS는 {format_value(vals['eps']['value'])}다. EPS 변화의 지속성은 이익과 주식 수를 함께 봐야 한다.",[vals[k]['id'] for k in ('net_income','eps')]))
 if f['template']=='bank':
  if 'roe' in f['missing_kpis']:text='은행의 핵심 건전성·수익성 지표가 미확보여서 일반 기업의 현금흐름 기준으로 평가하지 않는다.'
  else:text='은행의 NIM·CET1·대손충당금 자료가 미확보된 항목은 별도 공시 확인이 필요하다. 일반 기업의 FCF 기준으로 건전성을 단정하지 않는다.'
  result.append(claim(text,[],'UNCERTAINTY'))
 elif all(k in vals for k in ('ocf','capex','fcf')):result.append(claim(f"영업현금흐름 {format_value(vals['ocf']['value'])}에서 설비투자 지출 {format_value(abs(vals['capex']['value']))}를 차감한 잉여현금흐름은 {format_value(vals['fcf']['value'])}다. 회계상 이익과 구분해야 한다.",[vals[k]['id'] for k in ('ocf','capex','fcf')]))
 return result[:3]

def calculated_research(f):
 """Testable accounting comparisons, used when prose drafting is not reliable.
 These are calculations and explicitly conditional checks, not unreviewed model output.
 """
 result={k:[] for k in ('analysis','base','bull','bear','invalidation','watch')}
 q=[c for c in f['comparisons'] if c.get('frequency')=='quarterly' and c['basis']=='Previous Year']
 latest=max((c['period_end'] for c in q),default=None);values={c['metric']:c for c in q if c['period_end']==latest}
 if 'revenue' not in values or 'net_income' not in values:return result
 rev=values['revenue'];ni=values['net_income'];refs=rev['evidence_ids']+ni['evidence_ids'];up=rev['difference']>0 and ni['difference']>0
 rv='증가' if rev['difference']>0 else '감소' if rev['difference']<0 else '동일';nv='증가' if ni['difference']>0 else '감소' if ni['difference']<0 else '동일'
 result['analysis']=[claim(f"{latest}의 전년 동기 비교에서 매출은 {rv}, 순이익은 {nv}했다. 이는 관측된 회계 실적의 방향이며, 한 분기만으로 구조적 성장이나 향후 주가를 판단하지 않는다.",refs)]
 result['base']=[claim('현재 판단의 기준은 동일 통화·동일 분기 매출과 순이익의 실제 비교다. 시장 기대치와 경영진 가이던스가 없으면 실적 서프라이즈라고 부르지 않는다.',refs)]
 result['invalidation']=[claim(('실적 증가가 이어진다는 가설은 다음 비교 가능한 공시에서 매출 또는 순이익의 전년 동기 감소가 확인되거나, 기존 수치가 정정되면 재검토해야 한다.' if up else '현재 실적 방향이 이어진다는 가설은 다음 비교 가능한 공시에서 매출·순이익 방향이 반전되거나 기존 수치가 정정되면 재검토해야 한다.'),refs,'HYPOTHESIS')]
 result['watch']=[claim('다음 분기 공시의 동일 기준 매출·순이익, 전년 비교와 정정 여부를 확인한다. 실제 확보되지 않은 컨센서스·가이던스 수치를 대조값으로 쓰지 않는다.',refs)]
 if f['template']=='bank':
  result['analysis'].append(claim('은행의 영업현금흐름은 예금·대출 등 운전자금 이동에 크게 좌우될 수 있어 일반 기업의 현금전환율과 같은 기준을 적용하지 않는다. NIM·CET1·대손비용 미확보가 수익성·건전성 판단의 구체적인 제약이다.',[], 'UNCERTAINTY'))
  return result  # No bull/bear earnings narrative without bank-specific risk inputs.
 if len({r['period_end'] for r in f['records'] if r['frequency']=='quarterly'})>=4:
  result['bull']=[claim('긍정 시나리오의 조건은 매출 증가와 수익성 개선이 함께 확인되고, 영업현금흐름도 회계 이익을 뒷받침하는 것이다. 아직 관측되지 않은 미래 조건이며 확률이나 수익률을 부여하지 않는다.',refs,'HYPOTHESIS')]
  result['bear']=[claim('부정 시나리오의 조건은 매출과 순이익이 함께 감소하거나, 이익 증가에도 현금전환이 악화되는 것이다. 확인 전에는 실제 악화로 기록하지 않는다.',refs,'HYPOTHESIS')]
 return result
