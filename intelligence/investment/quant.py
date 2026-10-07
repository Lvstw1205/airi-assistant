"""Deterministic daily calculations; no execution signals."""
import math,statistics
from stock101.indicators import ema,rsi
VERSION='investment-quant/2.0'
def returns(a,b):return None if a is None or b is None or a<=0 else (b/a-1)*100
def log_return(a,b):return math.log(b/a) if a is not None and b is not None and min(a,b)>0 else None
def yield_delta(a,b):return {'bp':(b-a)*100,'percentage_points':b-a}
def pe(price,eps):return {'value':price/eps,'status':'ok'} if eps is not None and eps>0 and price is not None and price>=0 else {'value':None,'status':'N/M' if eps is not None and eps<=0 else 'missing'}
def metrics(row):
 h=row.get('history',[]);v=[x['value'] for x in h];annual=365 if row['asset_class']=='crypto' else 252
 result={'daily':None,'5d':None,'20d':None,'ema20':None,'rsi14':None,'max_drawdown_pct':None,'annualized_vol_pct':None,'n':len(v),'annual_observations':annual,'version':VERSION,'method':'Completed daily adjusted closes; EMA20 SMA seed; Wilder RSI14 (flat=50); sample log-return volatility; observed-window running-peak drawdown. Missing observations are not forward-filled.'}
 for n,key in ((1,'daily'),(5,'5d'),(20,'20d')):
  if len(v)>n:result[key]=(v[-1]-v[-n-1])*100 if row['asset_class']=='rates' else returns(v[-n-1],v[-1])
 if not v or row['asset_class']=='rates':return result
 if min(v)<=0:return result
 result['ema20']=ema(v,20)[-1];result['rsi14']=rsi(v,14)[-1]
 high=v[0];dd=[]
 for p in v:high=max(high,p);dd.append((p/high-1)*100)
 result['max_drawdown_pct']=min(dd)
 lr=[log_return(a,b) for a,b in zip(v,v[1:])]
 # Date gaps may be holidays. Calendar validation is required for annualized volatility.
 if len(lr)>=20:result['annualized_vol_pct']=statistics.stdev(lr[-20:])*math.sqrt(annual)*100
 return result

def convert(amount,from_currency,to_currency,fx,date):
 if fx.get('observation_date')!=date:raise ValueError('FX observation date mismatch')
 base,quote=fx['symbol'].split('/');rate=fx['value']
 if rate is None or rate<=0:raise ValueError('FX rate unavailable')
 if (from_currency,to_currency)==(base,quote):out=amount*rate
 elif (from_currency,to_currency)==(quote,base):out=amount/rate
 else:raise ValueError('FX direction mismatch')
 return {'value':out,'original_amount':amount,'original_currency':from_currency,'currency':to_currency,'fx_rate':rate,'fx_date':date,'fx_instrument':fx['instrument_id'],'fees':'not included'}

def portfolio(positions,rows,base_currency):
 if not positions:return {'status':'missing','reason':'보유 수량과 기준 통화를 입력해야 개인 포트폴리오를 계산할 수 있어.'}
 values=[]
 for p in positions:
  row=rows[p['instrument_id']];quantity=float(p['quantity'])
  if not math.isfinite(quantity) or quantity<0:raise ValueError('Long-only nonnegative quantity required')
  if row['currency']!=base_currency or row['quality_status'] not in ('fresh','delayed'):raise ValueError('동일 기준 통화와 유효한 관측치가 필요해. 환율을 추정하지 않아.')
  values.append({'instrument_id':p['instrument_id'],'value':quantity*row['value'],'observed_at':row['observed_at']})
 if len({x['observed_at'] for x in values})>1:raise ValueError('Portfolio valuation dates differ')
 total=sum(x['value'] for x in values)
 return {'status':'ok','currency':base_currency,'total':total,'positions':[{**x,'weight':x['value']/total if total else None} for x in values],'limitations':['ETF look-through, VaR and expected shortfall unavailable without suitable position history.']}
