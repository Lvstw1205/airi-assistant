"""Structured local-model output contracts; no free-form plan strings."""
import copy
S={'type':'string'};N={'type':'number'};B={'type':'boolean'}
def arr(item,maximum=30):return {'type':'array','items':item,'maxItems':maximum}
def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
U=obj({'text':S,'kind':{'type':'string','enum':['Fact','Interpretation','Estimate','Forecast']},'evidence_ids':arr(S,8),'method':S})
NULL_U={'anyOf':[U,{'type':'null'}]}
A=obj({'name':S,'value':N,'unit':S,'method':S,'basis':{'type':'string','enum':['Verified','Estimate']},'evidence_ids':arr(S,8)})
V=obj({'method':{'type':'string','enum':['eps_multiple','book_multiple','ev_ebitda','dcf','yield_build','unavailable']},'assumptions':arr(A,6),'axis_x':arr(N,3),'axis_y':arr(N,3)})
SC=obj({'name':{'type':'string','enum':['Bull','Base','Bear']},'probability':{'type':'number','minimum':0,'maximum':100,'description':'Percentage points; three weights total 100. Example 20, 60, 20.'},'method':S,'trigger':U,'outcome':U})
RISK=obj({'risk':U,'probability':N,'impact_score':{'type':'integer','minimum':1,'maximum':5},'method':S,'falsifier':U})
BRIDGE=obj({'currency':S,'years':arr(obj({'year':{'type':'integer'},'revenue':N,'net_margin_pct':N}),3),'evidence_ids':arr(S,8),'method':S})
NOTES=obj({'notes':arr(U,15),'missing_data':arr(S,15)})
SELECT_NOTES=obj({'evidence_ids':arr(S,15)})
NOTE_DECISION=obj({'action':{'type':'string','enum':['keep','remove']},'reason':S})
NOTES_AUDIT=obj({'decisions':obj({}),'missing_data':arr(S,15)})
PLAN=obj({'thesis':U,'consensus':NULL_U,'variant':U,'outline':arr(obj({'title':S,'question':S}),4),'takeaways':{**arr(U,5),'minItems':3},'valuation':V,'scenarios':arr(SC,3),'risks':arr(RISK,5),'earnings_bridge':{'anyOf':[BRIDGE,{'type':'null'}]},'missing_data':arr(S,20)})
TABLE=obj({'title':S,'columns':arr(S,6),'rows':arr(arr(S,6),15),'evidence_ids':arr(S,8),'note':S,'basis':{'type':'string','enum':['Interpretation','Estimate']},'method':S})
DRAFT=obj({'sections':arr(obj({'key':S,'title':S,'conclusion':U,'paragraphs':arr(U,12),'tables':arr(TABLE,2),'missing_data':arr(S,10)}),3)})
REVIEW=obj({'decisions':arr(obj({'id':S,'decision':{'type':'string','enum':['keep','remove']},'reason':S}),10),'weakest_arguments':arr(obj({'id':S,'problem':S,'replacement':NULL_U}),3),'counterargument':NULL_U,'addressed':B,'contradictions':arr(S,10),'pm_readable':B})
CONSISTENCY=obj({'consistent':B,'contradictions':arr(S,10),'pm_readable':B,'counterargument':NULL_U,'addressed':B,'explanation':S})
PLAN_REVIEW=obj({'decisions':arr(obj({'id':S,'decision':{'type':'string','enum':['keep','remove']},'reason':S}),40),'missing_data':arr(S,20)})
PLAN_REPAIR=obj({'corrections':obj({})})

def for_stage(stage,data=None):
    schema={'desk_topic':obj({'queries':arr(S,2)}),'desk_extract':obj({'facts':arr(obj({'text':S,'passage_id':S,'period':{'type':['string','null']}}),6)}),'desk_notes':SELECT_NOTES,'desk_notes_review':NOTES_AUDIT,'desk_plan':PLAN,'desk_plan_review':PLAN_REVIEW,'desk_plan_repair':PLAN_REPAIR,'desk_draft':DRAFT,'desk_review':REVIEW,'desk_consistency':CONSISTENCY}.get(stage)
    if schema is None:return 'json'
    schema=copy.deepcopy(schema)
    if stage=='desk_extract':
        ids=[p['id'] for p in (data or {}).get('passages',[]) if isinstance(p,dict) and p.get('id')]
        if ids:schema['properties']['facts']['items']['properties']['passage_id']={'type':'string','enum':ids}
    if stage=='desk_notes_review':
        ids=[n['id'] for n in (data or {}).get('draft_notes',[]) if isinstance(n,dict) and n.get('id')]
        schema['properties']['decisions']=obj({key:copy.deepcopy(NOTE_DECISION) for key in ids})
    if stage=='desk_plan_repair':
        ids=(data or {}).get('repair_ids',[])
        schema['properties']['corrections']=obj({key:copy.deepcopy(U) for key in ids})
    refs=[x['id'] for x in (data or {}).get('evidence',[]) if isinstance(x,dict) and x.get('id')]
    if refs:
        def walk(node):
            if isinstance(node,dict):
                if 'evidence_ids' in node.get('properties',{}):node['properties']['evidence_ids']['items']={'type':'string','enum':refs}
                for value in node.values():walk(value)
            elif isinstance(node,list):
                for value in node:walk(value)
        walk(schema)
    return schema
