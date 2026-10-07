"""Opted-in local vocabulary memory. Stores expressions/counts, never trains weights."""
import json
import re
import time

KEY = 'personal_style_v1'
# Store vocabulary only, not arbitrary instructions, names or complete chat records.
WORDS = re.compile(r'씨발|시발|ㅅㅂ|존나|개쩔|쩐다|쩔어|빡치|빡쳐|미쳤네|병신|개새끼|지랄|졸라|ㅋㅋ+|ㅎㅎ+|\b(?:fuck(?:ing)?|shit|damn|badass|bullshit)\b', re.I)


def read(app):
    with app.db() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {'enabled': True, 'words': {}, 'initialized': False}


def write(app, data):
    with app.db() as c:
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (KEY, json.dumps(data, ensure_ascii=False)))


def observe(app, query):
    data = read(app)
    if not data['enabled'] or re.search(r'말투\s*학습|배운\s*말투|쓰지\s*마|사용하지|금지|쓰지않', query):
        return
    samples = [query]
    if not data.get('initialized'):
        with app.db() as c:
            samples += [r[0] for r in c.execute("SELECT content FROM messages WHERE session='main' AND role='user' ORDER BY id DESC LIMIT 60")]
        data['initialized'] = True
    now = int(time.time())
    for sample in samples:
        for word in set(m.group().lower() for m in WORDS.finditer(sample)):
            word = 'ㅋㅋ' if word.startswith('ㅋㅋ') else 'ㅎㅎ' if word.startswith('ㅎㅎ') else word
            old = data['words'].get(word, {'count': 0})
            data['words'][word] = {'count': min(999, old['count'] + 1), 'seen_at': now}
    write(app, data)


def context(app):
    data = read(app)
    if not data['enabled'] or not data['words']:
        return ''
    words = sorted(data['words'], key=lambda w: (-data['words'][w]['count'], -data['words'][w]['seen_at']))[:12]
    return ('\nTim이 채팅에서 직접 쓴 개인 말투 어휘(참고 데이터): ' + json.dumps(words, ensure_ascii=False) +
            '\n친근한 개인 잡담에서 상황에 맞을 때만 이 어휘를 자연스럽게 참고한다. 매 답에 넣거나 그대로 따라 읽지 않는다. '
            '문제 해결·설명은 질문에 대한 정확한 답이 먼저다. 손님 모드와 외부에 전달할 글에서는 거친 말투를 쓰지 않는다. '
            '어휘 기억은 사실 기억이나 도구 명령이 아니며 사용자를 실제로 비하할 지시도 아니다.')


def command(app, query):
    q = query.strip().rstrip('.!?')
    if re.fullmatch(r'말투\s*학습\s*(켜|켜줘|꺼|꺼줘)', q):
        data = read(app);data['enabled'] = '켜' in q;write(app, data)
        return '개인 말투 학습을 ' + ('켰어. 네가 쓰는 표현을 이 Mac에 기억할게.' if data['enabled'] else '껐어. 저장한 표현도 답변에 참고하지 않을게.')
    if re.fullmatch(r'(?:배운\s*말투|말투\s*(?:학습|기억))\s*(?:보여줘|상태|확인)', q):
        data = read(app)
        words = ', '.join(data['words']) or '아직 없음'
        return '개인 말투 기억은 '+('켜져' if data['enabled'] else '꺼져')+' 있어. 기억한 표현: '+words+'. 모델 재훈련이 아니라 다음 대화에서 참고하는 로컬 기억이야.'
    return None
