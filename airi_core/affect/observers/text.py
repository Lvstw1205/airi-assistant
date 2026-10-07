import time

def from_reply(value,query,session='main'):
    observation=value.get('observation') or {};evidence=observation.get('evidence','')
    v=observation.get('valence');a=observation.get('arousal');confidence=observation.get('confidence',0)
    if not isinstance(evidence,str) or not evidence.strip() or evidence not in query:return None
    if type(v) not in (int,float) or type(a) not in (int,float) or type(confidence) not in (int,float):return None
    if not -1<=v<=1 or not 0<=a<=1 or not 0<=confidence<=1:return None
    return {'ts':time.time(),'source':'text','valence':v,'arousal':a,'confidence':confidence,'evidence':evidence[:160],'session_id':session,'owner':True}
