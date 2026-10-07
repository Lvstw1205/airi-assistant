"""Small deterministic strategy constraints, not a diagnostic classifier."""
import re

STRATEGIES=['question','restatement','reflection','affirmation','suggestion','information','self_disclosure','chat']
EMOTIONS=['HAPPY','EXCITED','CONFUSED','CONCERNED']
HUMOR=['none','callback','yes_and','tease','reaction']

def intent(text):
    if re.search(r'방법|해결|어떻게|조언|도와|\b(how|solve|advice|help me)\b',text,re.I):return 'solve'
    if re.search(r'들어\s*줘|그냥\s*들어|\bjust listen\b',text,re.I):return 'listen'
    if re.search(r'알려|설명|무엇|왜|\b(what|why|explain)\b',text,re.I):return 'inform'
    return 'chat'

def plan(text,recent,cfg):
    want=intent(text)
    distressed=bool(re.search(r'힘들|속상|지쳤|지친|괴로|불안|걱정|상처|짜증|우울|슬프|\b(exhausted|upset|worried|distressed|struggling)\b',text,re.I))
    preferred='suggestion' if want=='solve' else 'information' if want=='inform' else 'reflection' if distressed or want=='listen' else 'chat'
    banned=[]
    n=cfg['strategy_repeat_limit']
    if len(recent)>=n and len({t['strategy'] for t in recent[:n]})==1:
        banned=[recent[0]['strategy']]
    if preferred in banned and want not in ('solve','inform'):preferred='affirmation' if distressed else 'chat'
    if preferred in banned:preferred=next(s for s in ('reflection','affirmation','chat','information') if s not in banned)
    wants_support=bool(re.search(r'내\s*편|편.{0,5}들어|같이\s*욕|on my side',text,re.I))
    return {'want':want,'preferred_strategy':preferred,'avoid_strategies':banned,'tease_ok':not distressed and not wants_support,'distress_explicit':distressed,'check_in':False}

def reply_schema(avoid_strategies=()):
    props={
      'strategy':{'type':'string','enum':[s for s in STRATEGIES if s not in avoid_strategies]},
      'check_in':{'type':'boolean'},
      'emotion':{'type':['string','null'],'enum':EMOTIONS+[None]},
      'intensity':{'type':'number','minimum':0,'maximum':1},
      'humor':{'type':'string','enum':HUMOR},
      'safety':{'type':'string','enum':['none','self_harm','harm_others']},
      'safety_evidence':{'type':'string'},
      'observation':{'type':'object','additionalProperties':False,'properties':{
          'valence':{'type':['number','null'],'minimum':-1,'maximum':1},
          'arousal':{'type':['number','null'],'minimum':0,'maximum':1},
          'confidence':{'type':'number','minimum':0,'maximum':1},
          'evidence':{'type':'string'}},'required':['valence','arousal','confidence','evidence']},
      'text':{'type':'string'}}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}

def validate_reply(value,cfg):
    if not isinstance(value,dict) or value.get('strategy') not in STRATEGIES or value.get('emotion') not in EMOTIONS+[None] or value.get('humor') not in HUMOR:raise ValueError('대화 결과 형식을 확인하지 못했어. 다시 한 번 말해줘.')
    if type(value.get('check_in')) is not bool or not isinstance(value.get('text'),str) or not value['text'].strip():raise ValueError('대화 응답이 비어 있어.')
    if value.get('safety') not in ('none','self_harm','harm_others'):raise ValueError('응답 분류를 확인하지 못했어.')
    if type(value.get('intensity')) not in (float,int) or not 0<=value['intensity']<=1:raise ValueError('표현 강도를 확인하지 못했어.')
    if len(value['text'])>cfg['reply_chars']:raise ValueError('대화 응답이 너무 길어. 짧게 나눠서 다시 말해줘.')
    return value
