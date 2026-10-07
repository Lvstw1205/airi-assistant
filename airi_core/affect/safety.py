"""Immediate deterministic safety route plus same-turn local model classification.

This is not a clinical assessment or a guarantee of crisis detection.
"""
import re

def rule_signal(text):
    s=text.lower()
    # Quoted documentation and ordinary figurative phrases are not declarations.
    if re.search(r'테스트\s*문장|테스트\s*케이스|예시\s*문장|논문|예방\s*(?:교육|정책)|translate|번역|소설\s*(?:속|대사)',s):return None
    if re.search(r'죽고\s*싶지\s*않|자살할\s*생각\s*없|자해할\s*생각\s*없|don.t want to (?:die|kill)',s):return None
    if re.search(r'나.{0,10}(?:죽고\s*싶|목숨.{0,4}끊|자살|자해)|(?:죽고\s*싶어|자살할래|자살하려|자해하고\s*싶)|(?:i (?:want to|will|am going to)|i.m going to).{0,18}(?:kill myself|end my life|hurt myself|die)|i can.t keep myself safe',s):return 'self_harm'
    if re.search(r'(?:누구|그\s*사람|사람|걔|그놈).{0,10}(?:죽일\s*거|해칠\s*거|죽이러)|(?:i will|i.m going to).{0,15}(?:kill|hurt) (?:him|her|them|someone)',s):return 'harm_others'
    return None

def model_signal(value,query):
    label=value.get('safety');evidence=value.get('safety_evidence','')
    return label if label in ('self_harm','harm_others') and isinstance(evidence,str) and evidence.strip() and evidence in query else None

def response(signal,country='CA',korean=True):
    if signal=='harm_others':
        return ('지금 많이 격해진 것 같아. 그 사람과 거리를 두고 다칠 수 있는 물건에서 떨어져 있어 줘. 바로 위험한 상황이면 '+('112' if country=='KR' else '911')+'에 연락하고, 곁에 올 수 있는 믿을 만한 사람에게 지금 도움을 요청해 줘.') if korean else 'Please put distance between you and that person, and move away from anything that could hurt someone. If anyone is in immediate danger, call emergency services now and contact someone you trust who can stay with you.'
    if korean:
        contact='한국에 있다면 자살예방 상담전화 109, 당장 위험하면 119나 112' if country=='KR' else '캐나다에서는 988에 전화하거나 문자를 보낼 수 있어. 당장 위험하면 911'
        return '그 말은 가볍게 넘기지 않을게. 지금 혼자 감당하지 말고, 다칠 수 있는 물건에서 떨어져서 믿을 만한 사람에게 함께 있어 달라고 해 줘. '+contact+'에 연락해 줘. 지금 바로 다칠 위험이 있어?'
    return 'I’m taking that seriously. Please move away from anything you could use to hurt yourself and ask someone you trust to stay with you. In Canada, call or text 988; call 911 if you are in immediate danger. Are you in immediate danger right now?'
