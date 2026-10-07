"""Explicit, reproducible scenario maths; never used by an order executor."""
import math
import re
from .contracts import number_tokens

PARAMS = {'eps_multiple': ('eps', 'multiple'), 'book_multiple': ('bvps', 'multiple'),
          'ev_ebitda': ('ebitda', 'multiple', 'net_debt', 'shares'),
          'dcf': ('fcf', 'growth', 'wacc', 'terminal_growth', 'net_debt', 'shares'),
          'yield_build': ('expected_policy_rate', 'term_premium')}
FORMULAS = {'eps_multiple': 'EPS × P/E multiple', 'book_multiple': 'Book value per share × P/B multiple',
            'ev_ebitda': '(EBITDA × EV/EBITDA multiple − net debt) / shares',
            'dcf': 'Σ(t=1..5) FCF×(1+g)^t/(1+WACC)^t + [FCF×(1+g)^5×(1+terminal g)/(WACC−terminal g)]/(1+WACC)^5; subtract net debt, divide by shares',
            'yield_build': 'Expected policy rate + estimated term premium; percent inputs, not observed decomposition'}

def calculate(method, p):
    if not all(type(v) in (int, float) and math.isfinite(v) for v in p.values()):
        raise ValueError('Non-finite valuation input')
    if 'multiple' in p and p['multiple']<=0: raise ValueError('Valuation multiple must be positive')
    if method=='eps_multiple' and p['eps']<=0: raise ValueError('P/E is not meaningful for non-positive EPS')
    if method=='book_multiple' and p['bvps']<=0: raise ValueError('P/B is not meaningful for non-positive book value')
    if method == 'eps_multiple': value = p['eps'] * p['multiple']
    elif method == 'book_multiple': value = p['bvps'] * p['multiple']
    elif method == 'ev_ebitda':
        if p['shares'] <= 0: raise ValueError('Share denominator must be positive')
        value = (p['ebitda'] * p['multiple'] - p['net_debt']) / p['shares']
    elif method == 'dcf':
        if p['shares'] <= 0 or not 0 < p['wacc'] < 1 or not -1 < p['growth'] < 1 or not -1 < p['terminal_growth'] < p['wacc']:
            raise ValueError('Invalid DCF growth, discount rate or shares')
        cash = sum(p['fcf']*(1+p['growth'])**t/(1+p['wacc'])**t for t in range(1,6))
        terminal = p['fcf']*(1+p['growth'])**5*(1+p['terminal_growth'])/(p['wacc']-p['terminal_growth'])/(1+p['wacc'])**5
        value = (cash + terminal - p['net_debt']) / p['shares']
    elif method == 'yield_build': value = p['expected_policy_rate'] + p['term_premium']
    else: raise ValueError('Unsupported valuation method')
    if not math.isfinite(value): raise ValueError('Invalid valuation output')
    return round(value, 4)

def build(proposal, evidence):
    method = proposal.get('method') if isinstance(proposal,dict) else None
    if method not in PARAMS: return {'available':False,'reason':'Data not available: valuation requires supported inputs and explicit assumptions.'}
    assumptions = proposal.get('assumptions', []); by = {a.get('name'):a for a in assumptions if isinstance(a,dict)}
    for name in PARAMS[method]:
        a = by.get(name,{})
        if type(a.get('value')) not in (int,float) or not math.isfinite(a['value']) or not a.get('unit') or not a.get('method') or a.get('basis') not in ('Verified','Estimate'):
            raise ValueError('Incomplete valuation assumption: '+name)
        refs = a.get('evidence_ids',[])
        if not refs or any(x not in evidence for x in refs): raise ValueError('Unknown valuation source: '+name)
        if a['basis']=='Verified' and not number_tokens(str(a['value'])) <= number_tokens(' '.join(evidence[r]['text'] for r in refs)):
            raise ValueError('Valuation assumption is not a sourced number: '+name)
    if len(by)!=len(assumptions) or set(by)!=set(PARAMS[method]):raise ValueError('Use each required parameter exactly once')
    if 'multiple' in by and by['multiple']['unit']!='x':raise ValueError('Multiple unit must be x')
    money=('eps',) if method=='eps_multiple' else ('bvps',) if method=='book_multiple' else ('ebitda','net_debt') if method=='ev_ebitda' else ('fcf','net_debt') if method=='dcf' else ()
    if money:
        expected=r'(CAD|USD|KRW)/share' if method in ('eps_multiple','book_multiple') else r'(CAD|USD|KRW)'
        if any(not re.fullmatch(expected,by[k]['unit']) for k in money) or len({by[k]['unit'] for k in money})!=1:raise ValueError('Normalize monetary inputs to the same unscaled currency and per-share basis')
    if 'shares' in by and by['shares']['unit']!='count':raise ValueError('Normalize shares to count, monetary totals to unscaled currency')
    if method=='dcf' and any(by[k]['unit']!='fraction' for k in ('growth','wacc','terminal_growth')):raise ValueError('DCF rates must be decimal fraction units')
    if method=='yield_build' and any(by[k]['unit']!='%' for k in PARAMS[method]):raise ValueError('Yield components must use percent units')
    params = {k:by[k]['value'] for k in PARAMS[method]}
    axes = ('wacc','terminal_growth') if method=='dcf' else PARAMS[method][:2]
    xs,ys=proposal.get('axis_x',[]),proposal.get('axis_y',[])
    if any(not isinstance(a,list) or len(a)!=3 or len(set(a))!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in a) for a in (xs,ys)):
        raise ValueError('Sensitivity needs three distinct numeric values on each axis')
    rows=[]
    for y in ys:
        row=[y]
        for x in xs:
            try: row.append(calculate(method,{**params,axes[0]:x,axes[1]:y}))
            except ValueError: row.append(None)
        rows.append(row)
    base=calculate(method,params)
    refs=list(dict.fromkeys(r for a in assumptions for r in a.get('evidence_ids',[])))
    result={'available':True,'method':method,'formula':FORMULAS[method],'base':base,'assumptions':assumptions,
            'axis_names':axes,'x':xs,'rows':rows,'evidence_ids':refs,'basis':'Estimate',
            'output_unit': '%' if method=='yield_build' else by[money[0]]['unit'].split('/')[0]+'/share',
            'sensitivity_method':'House sensitivity assumptions, not observed outcomes. Each cell recomputes the stated model; other inputs fixed.'}
    evidence['Q_VALUATION']={'id':'Q_VALUATION','text':str(result),'quote':'','basis':'Estimate','method':FORMULAS[method],'source_ids':list(dict.fromkeys(s for r in refs for s in evidence[r].get('source_ids',[]))),'input_ids':refs}
    return result

def build_risks(items,evidence):
    from .contracts import valid_unit
    result=[]
    for x in items or []:
        if not isinstance(x,dict):continue
        p=x.get('probability');impact=x.get('impact_score')
        unit=valid_unit(x.get('risk'),evidence,forecast=True);falsifier=valid_unit(x.get('falsifier'),evidence,forecast=True)
        if not unit or not falsifier or type(p) not in (int,float) or not 0<=p<=100 or type(impact) is not int or not 1<=impact<=5 or len(str(x.get('method','')))<25:continue
        result.append({**x,'risk':unit,'falsifier':falsifier,'score':round(p/100*impact,3),'basis':'Estimate'})
    if not 3<=len(result)<=5:return []
    if len({x['risk']['text'].lower() for x in result})!=len(result):return []
    result.sort(key=lambda x:x['score'],reverse=True)
    refs=list(dict.fromkeys(r for x in result for r in x['risk']['evidence_ids']+x['falsifier']['evidence_ids']))
    evidence['Q_RISKS']={'id':'Q_RISKS','text':str(result),'basis':'Estimate','method':'Score = estimated probability / 100 × impact score. Impact is ordinal: 1 minor, 2 modest, 3 material, 4 large, 5 thesis invalidation; not a portfolio loss forecast.','input_ids':refs,'source_ids':list(dict.fromkeys(s for r in refs for s in evidence[r].get('source_ids',[])))}
    return result

def build_earnings(value,evidence,as_of):
    if not isinstance(value,dict) or not value.get('years'):return {'available':False,'reason':'Data not available: current and next-two-year revenue/net-margin assumptions with source evidence.'}
    rows=value['years'];year=int(as_of[:4]);currency=value.get('currency');refs=value.get('evidence_ids',[])
    if len(rows)!=3 or [x.get('year') for x in rows]!=[year,year+1,year+2] or currency not in ('USD','CAD','KRW') or not refs or any(r not in evidence for r in refs) or len(str(value.get('method','')))<25:raise ValueError('Invalid earnings bridge: three consecutive years, unscaled currency, sources and estimation method required')
    for x in rows:
        if any(type(x.get(k)) not in (int,float) or not math.isfinite(x[k]) for k in ('revenue','net_margin_pct')) or x['revenue']<=0 or not -100<=x['net_margin_pct']<=100:raise ValueError('Invalid earnings bridge inputs')
        x['net_profit']=round(x['revenue']*x['net_margin_pct']/100,4)
    for i,x in enumerate(rows):x['revenue_yoy_pct']=None if not i else round((x['revenue']/rows[i-1]['revenue']-1)*100,4)
    result={**value,'available':True,'years':rows,'basis':'Estimate','formula':'Net profit = revenue × net margin / 100; revenue YoY = (current / previous − 1) × 100. All years are house estimates; current year is not presented as a filed full-year result.'}
    evidence['Q_EARNINGS']={'id':'Q_EARNINGS','text':str(result),'basis':'Estimate','method':result['formula']+' '+value['method'],'input_ids':refs,'source_ids':list(dict.fromkeys(s for r in refs for s in evidence[r].get('source_ids',[])))}
    return result
