"""Keep current intent separate from previous visual observations and tool planning."""
import re
from pathlib import Path

VISUAL = re.compile(r'카메라|홈캠|바코드|라벨|들고\s*있|보여주|뭐가\s*보여|뭐가\s*보이|주변.{0,8}(?:봐|사람)|이(?:거|게|것).{0,10}(?:뭐야|뭔지)|\b(?:camera|webcam|barcode|holding|surroundings)\b|what (?:do|can) you see', re.I)
TOOLS = re.compile(r'카메라|홈캠|바코드|들고|보여주|일정|할\s*일|캘린더|메모|기억|스킬|파일|첨부|자료|문서|NAS|뉴스|날씨|기온|우산|시세|주가|환율|금리|금액|조회|검색|찾아|실행|저장|등록|예약|오늘|현재|최신|영상|비디오|이미지|그림|만들어|\b(?:api|mcp|tasks?|calendar|schedule|memory|notes?|skills?|files?|documents?|weather|news|stocks?|price|rate|search|find|lookup|execute|save|latest|current|today|video|image|picture|camera)\b', re.I)


def focused_history(messages, query):
    """Preserve the transcript on disk; exclude irrelevant camera turns from inference."""
    visual = bool(VISUAL.search(query))
    result = []
    prior_user = ''
    for message in messages:
        if message.get('role') == 'user':
            prior_user = message.get('content', '')
        content = message.get('content') or ''
        if not visual and (VISUAL.search(content) or VISUAL.search(prior_user)):
            continue
        if message.get('role') == 'assistant' and ('도구 조회 단계 제한' in content or '모델이 답변을 반환하지' in content):
            continue
        # A previous failed answer repeated verbatim is not a demonstration.
        if message.get('role') == 'assistant' and any(m.get('role') == 'assistant' and m.get('content') == content for m in result):
            continue
        result.append(dict(message))
    return result


def needs_tools(query):
    return bool(TOOLS.search(query) or VISUAL.search(query))


def plain_messages(app, messages, config, query):
    from personal_style import context
    persona = app.ROOT / 'config' / ('persona-chat.txt' if config.get('persona', 'free') == 'free' else 'persona.txt')
    prompt = '너는 User의 개인 AI 비서 아이리다. 한국어는 자연스러운 반말로 답한다. 끝맺음은 이야·해·지처럼 쓰고 입니다·합니다·해요는 쓰지 않는다. 영어·프랑스어 질문은 그 언어로 답한다. 계산·설명·번역·글쓰기에서는 요청한 결과가 먼저다. 질문을 비웃거나 사용자를 평가하는 말을 덧붙이지 않는다. 이전 욕이나 농담을 새 정보 질문에 이어 붙이지 않는다. 사실 질문은 정확한 답으로 끝낸다.\n현재 사용자의 질문에 직접 답한다. 사용자가 다시 물어볼 문장을 대신 쓰지 않는다. 이전 답변이 엉뚱했어도 그 내용을 이어 말하지 않는다. 일반 설명, 계산, 번역과 글쓰기는 요청한 내용을 바로 제공한다. 카메라 관측이나 도구 실행이 필요한 경우에만 해당 기능을 언급한다. 확인하지 않은 현재 데이터는 만들지 않는다.'
    import worker_identity
    prompt += "\n"+worker_identity.context(app,query)
    import political_values
    prompt += political_values.context(app.ROOT, query, messages[1:-1])
    result = [{'role': 'system', 'content': prompt}] + focused_history(messages[1:-1], query)[-6:] + [{'role': 'user', 'content': query}]
    return political_values.anchor(result, query)


def capability_reply(query):
    if re.fullmatch(r'\s*(?:(?:너|너는|너의|네|아이리|AIRI)[, ]*)?(?:할\s*수\s*있는\s*(?:일|게|것|기능)(?:이|은)?\s*(?:뭐여|뭐야|뭔데|뭐니|뭔지\s*알려줘)|기능(?:을|은)?\s*(?:알려줘|설명해줘|뭐야|뭐여)|what can you do)[.!?\s]*', query, re.I):
        return ('대화·번역·글쓰기·학습을 도와주고, 일정과 메모를 관리할 수 있어. '
                '날씨·뉴스·시장 자료를 조회하고, NAS 문서를 찾아 분석하거나 보고서로 만드는 기능도 있어. '
                '카메라 사물 인식, 홈캠 제어, 이미지·영상 작업, 티모에게 작업 전달도 연결돼 있고, 실제 사용 가능 여부는 각 연결 상태를 확인해. '
                '필요한 기능은 위의 위젯 추가에서 꺼내 쓸 수 있어.')
    return None
