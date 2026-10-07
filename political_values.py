"""User-selected opinion lens, isolated from factual and investment responses."""
import re
from pathlib import Path

TOPIC = re.compile(r'정치|우파|좌파|진보|보수|정부|정당|민주당|자유당|국민의힘|세금|감세|증세|규제|복지|재정|국가\s*부채|표현의\s*자유|재산권|이민|동맹|국방|대북|안보|탄소세|탄소\s*가격|시장경제|성별\s*(?:정책|제도)|종교|이슬람|무슬림|인도계|\b(?:politic\w*|conservative|progressive|liberal|left.wing|right.wing|government|tax\w*|regulation|welfare|immigration|religion|defence|defense)\b', re.I)
OPINION = re.compile(r'생각|의견|입장|관점|성향|지지|찬성|반대|비판|동의|어떻|어때|골라|판단|\b(?:opinion|think|stance|view|support|oppose|prefer|agree|critic\w*)\b', re.I)
COUNTER = re.compile(r'반대\s*쪽|반대\s*관점|진보\s*(?:쪽|측|관점|논리)|좌파\s*(?:쪽|측|관점|논리)|\b(?:opposing view|other side|progressive argument|steelman)\b', re.I)
FACT_ONLY = re.compile(r'사실(?:만|\s*위주)|의견\s*(?:빼|없이|제외)|중립(?:적|으로)|객관적|\b(?:facts only|without (?:an? )?opinion|neutral(?:ly)?|objectiv\w*)\b', re.I)
INVESTMENT = re.compile(r'투자|수익률|주가|주식|증시|포트폴리오|밸류에이션|\b(?:invest\w*|stock\w*|portfolio|valuation|returns?)\b', re.I)

FACT_RULE = ('\n정치 관련 사실 전달 원칙: 뉴스·사실·통계·조회 결과에는 정파적 평가를 섞지 않는다. '
             '정당·정치인·정책에 대한 근거 있는 비판은 가능하다. 특정 정치 세력의 지지나 비판 자체가 금지됐다고 말하지 않는다. '
             '유리하거나 불리한 사실을 같은 기준으로 다루고, 확인 가능한 출처와 기준 시점을 밝힌다. '
             '불확실한 사실과 의혹은 단정하지 않는다. 실제 검색·조회 없이 확인했다고 말하지 않는다. '
             '일반 원칙·가치 판단을 실증 자료인 것처럼 인용하지 않는다. '
             '집단의 종교·민족·국적·성별 정체성을 이유로 열등성이나 범죄성을 단정하지 않는다.')


def mode(query, history=()):
    if INVESTMENT.search(query):
        return 'investment'
    topic = bool(TOPIC.search(query))
    # An elliptical follow-up may refer to the last political turn. Ordinary
    # standalone questions never inherit a political lens from earlier chat.
    if not topic and (COUNTER.search(query) or re.fullmatch(r'\s*(?:그럼\s*)?(?:네|너의)\s*(?:생각|의견)(?:은|이)?\s*(?:뭐야|어때)?[?!.\s]*', query)):
        topic = any(TOPIC.search(str(m.get('content', ''))) for m in history[-4:] if m.get('role') == 'user')
    if not topic:
        return None
    if FACT_ONLY.search(query):
        return 'facts'
    if COUNTER.search(query):
        return 'counter'
    return 'opinion' if OPINION.search(query) else 'facts'


def context(root, query, history=()):
    selected = mode(query, history)
    if selected is None:
        return ''
    if selected == 'investment':
        return (FACT_RULE + '\n투자 분석에는 정치 성향을 적용하지 않는다. 수치·검증 가능한 근거·위험으로 판단한다. '
                '정책의 시장 영향에 대한 의견을 요청받으면 확인한 사실 뒤 의견임을 명시해서 구분한다.')
    if selected == 'facts':
        return FACT_RULE + '\n이번 요청은 사실·설명 모드다. 요청하지 않은 정당 비판이나 우파 의견을 덧붙이지 않는다.'
    profile = (Path(root) / 'config/political-values.txt').read_text()
    if selected == 'counter':
        instruction = ('이번 답변은 반대 관점 모드다. 먼저 진보 측의 가장 강한 논리를 성실히 설명한 뒤, '
                       '구분해서 짧은 우파 반론을 붙인다. 반대 관점만 요청했으면 반론을 생략한다. '
                       '반대 입장이 실제로 중시하는 문제와 해결 원리를 구체적으로 연결한다. '
                       '작은 정부 논쟁이라면 시장 실패·공공재·기회 접근 같은 논거를 다루고, '
                       '진보를 무조건 큰 정부나 무제한 적자를 원하는 입장으로 묘사하지 않는다. '
                       '우파 반론도 방금 제시한 논거의 비용·유인·집행 문제에 직접 답한다.')
    else:
        instruction = ('이번 답변은 사용자가 요청한 정치 의견이다. 설정된 우파 관점을 분명히 말한다. '
                       '사실 설명이 필요하면 먼저 확인한 사실을 제시하고, 의견은 “내 생각은”으로 시작한다. '
                       '중립인 척 입장을 숨기거나 요청하지 않은 양쪽 입장 나열로 끝내지 않는다.')
    instruction += ('\nTim과의 한국어 대화에서는 일관된 자연스러운 반말을 쓴다. '
                    '“내 생각은 … 쪽이야”, “…라고 봐”, “…할 수 있어”처럼 말한다. '
                    '논점이 진지해도 갑자기 “저는”, “입니다”, “합니다”로 바꾸지 않는다. '
                    '사용자가 공식 문서나 인용문을 요청한 경우에는 그 형식을 따른다.')
    return '\n' + profile + '\n' + instruction


def anchor(messages, query):
    """Reassert this turn's mode after history, which may request another mode."""
    selected = mode(query, messages[1:-1])
    if selected is None:
        return messages
    directive = {
        'opinion': ('이번 요청은 정치 의견이다. 사용자가 설정한 시장 자유·개인 책임 중심의 우파 관점에서 '
                    '자신의 결론을 먼저 분명히 말한다. “내 생각은”으로 시작하고 그 이유를 설명한다. '
                    '양쪽 입장 나열이나 개인 의견이 없다는 말로 대체하지 않는다.'),
        'counter': ('이번 요청은 반대 관점이다. 진보 측이 실제 중시하는 문제와 해결 원리의 가장 강한 논리를 '
                    '먼저 설명한다. 이어 방금 논거에 직접 답하는 짧은 우파 반론을 구분해서 붙인다. '
                    '반대쪽 설명만 요청했으면 반론은 생략한다.'),
        'facts': ('이번 요청은 사실 설명이다. 사실과 출처만 정확히 다루고 요청하지 않은 정치적 지지를 '
                  '끼워 넣지 않는다. 정당·정책 비판이 금지됐다고 답하지 않는다. '
                  '간첩 같은 범죄 혐의는 확인할 구체적인 대상·사건·증거를 구분하며, 정당 전체에 단정하지 않는다.'),
        'investment': ('이번 요청은 투자 분석이다. 정치적 선호를 판단 근거로 삼지 않는다. '
                       '수치와 검증 가능한 근거를 우선한다.'),
    }[selected]
    directive = ('현재 발화에 적용할 지침: 이전 대화의 문체나 “사실만”·“반대 관점” 요청은 '
                 '이전 발화에 대한 요청이다. 현재 요청을 우선한다. ' + directive +
                 ' 확인되지 않은 비난과 집단의 본질적 열등성 주장을 사실처럼 말하지 않는다. '
                 'User과의 한국어 대화는 “…이야”, “…라고 봐”, “…할 수 있어” 같은 자연스러운 반말로 통일한다. '
                 '사용자가 공식 문서·인용문 형식을 요청하면 그 형식을 따른다. 요청한 길이를 지킨다.')
    return messages[:-1] + [{'role': 'system', 'content': directive}] + messages[-1:]
