"""Constrained local JSON output; semantic validation still runs afterwards."""
def obj(properties,required=None):return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
def arr(items,n=2):return {'type':'array','items':items,'maxItems':n}
S={'type':'string'}
REFS=arr(S,6)
U=obj({'text':S,'tag':{'type':'string','enum':['FACT','ANALYSIS','HYPOTHESIS','UNCERTAINTY']},'evidence_ids':REFS})
def extended(**fields):return obj({**U['properties'],**fields})
def format_for(stage):
 if stage.startswith('desk_'):
  from research_desk.schemas import for_stage
  return for_stage(stage)
 if stage=='investment_v2':return obj({'claims':arr(obj({'text':S,'evidence_ids':REFS,'counter_evidence':arr(S,2),'missing_data':arr(S,2)}),2)})
 if stage=='investment_relevance':return obj({'events':arr(obj({'id':S,'relevance':{'type':'string','enum':list('ABCDEF')},'impact':{'type':'string','enum':['High','Medium','Low']},'category':S,'reason':obj({'text':S,'evidence_ids':REFS}),'canadian_link':obj({'text':S,'evidence_ids':REFS})}),12)})
 if stage=='research_editorial':return obj({'decisions':arr(obj({'id':S,'decision':{'type':'string','enum':['keep','reject']},'reason':S}),7)})
 if stage=='financial_research':
  fields={k:arr(U,2 if k=='analysis' else 1) for k in ('why_it_matters','analysis','beneficiaries','risks','base','bull','bear','invalidation')}
  fields.update(transmission=arr(extended(stage=S),6),stocks=arr(extended(ticker=S,exposure=S),3),fundamentals=arr(extended(metric=S,direction=S),3),watch=arr(extended(date={'type':['string','null']}),2),missing=arr(S,5),signal={'type':'string','enum':['Positive Evidence','Negative Evidence','Mixed','Neutral','Insufficient Evidence']})
  return obj(fields)
 return 'json'
