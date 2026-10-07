"""Owner commands and output boundaries independent of model cooperation."""
import re,unicodedata

def normalize(text):return unicodedata.normalize('NFKC',text).strip()

def command(text):
    s=normalize(text).rstrip('.!?。').strip().lower()
    if s in ('손님 왔어','손님 왔음','손님 모드 켜','애들 있어','아이들 있어','guest on','/guest on'):return 'guest_on'
    if s in ('손님 갔어','손님 모드 꺼','이제 혼자야','guest off','/guest off'):return 'guest_off'
    if re.fullmatch(r'(?:아이리[, ]*)?내\s*감정\s*(?:기록|데이터)\s*(?:전부\s*)?(?:지워|삭제해|삭제)|/affect delete',s):return 'purge'
    if s in ('내 감정 상태 보여줘','인간다움 상태','/mind','/mind status'):return 'status'
    return None

def profane(text,cfg):return bool(re.search(cfg['profanity_pattern'],normalize(text),re.I))

def external_draft(text):
    return bool(re.search(r'(메일|이메일|문자|메시지|메세지|대본|공지|보고서|지원서|캘린더\s*메모|email|script|announcement|cover letter).{0,45}(써|작성|초안|보내|만들|draft|write|send)|(?:write|draft|send).{0,45}(?:email|script|message|letter)',text,re.I|re.S))

def violations(text,query,recent,cfg,guest=False,external=False,tease_ok=True):
    issues=[];value=normalize(text)
    if (guest or external) and profane(value,cfg):issues.append('손님과 외부 결과물에는 욕 없이 말한다')
    if any(p in value for p in cfg['negative_cliches']) and not any(p in query for p in cfg['negative_cliches']):issues.append('요청과 관계없는 상투적 비관 대신 방금 말의 구체적 내용에 반응한다')
    compact=re.sub(r'\W+','',value).lower()
    if compact and any(compact==re.sub(r'\W+','',r['text']).lower() for r in recent):issues.append('직전 답을 반복하지 말고 지금 요청에 맞는 다른 답을 한다')
    if re.search(r'AIRI_RESULT_|\b(?:strategy|used_thought_id|safety_evidence)\s*["\']?\s*:',value):issues.append('내부 필드와 제어 문자열을 빼고 실제 대화만 쓴다')
    if re.search(r'\*(?:웃|미소|고개|한숨|윙크|smil|laugh)[^*]*\*|\((?:웃음|한숨|미소|윙크)\)',value,re.I):issues.append('행동 지문을 쓰지 않는다')
    if not tease_ok and re.search(r'(?:너|네가|니가|네\s*질문|오빠가).{0,20}(?:멍청|병신|못났|못생|한심|재미없|재미\s*없|잘못|탓)|네\s*탓|이\s*자식',value):issues.append('힘들다고 말하거나 편을 들어 달라는 사용자를 놀리거나 탓하지 않는다')
    return issues

def require_clean_external(value,cfg):
    # Fail closed before an outgoing payload, never silently change exact user data.
    if isinstance(value,dict):
        for v in value.values():require_clean_external(v,cfg)
    elif isinstance(value,list):
        for v in value:require_clean_external(v,cfg)
    elif isinstance(value,str) and profane(value,cfg):raise ValueError('외부로 보낼 글에 욕설이 있어 전송을 멈췄어. 전달할 문장을 수정해줘.')
