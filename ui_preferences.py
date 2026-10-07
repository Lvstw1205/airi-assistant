"""Authenticated UI preferences in AIRI's existing SQLite database."""
import json

KEY = 'desktop_widgets_v1'
WIDGETS = {'clock', 'weather', 'study', 'news', 'calendar', 'markets', 'music',
           'chat', 'work', 'files', 'activity', 'settings', 'camera', 'stock101','mac-status','airi-office','studio'}
DEFAULT = {'widgets': ['clock', 'weather', 'study', 'news', 'calendar', 'markets', 'music'],
           'collapsed': [], 'study_goal': '', 'study_language': '프랑스어'}


def validate(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT):
        raise ValueError('지원하지 않는 화면 설정입니다.')
    result = {**DEFAULT, **value}
    for key in ('widgets', 'collapsed'):
        items = result[key]
        if (not isinstance(items, list) or len(items) > len(WIDGETS)
                or any(not isinstance(x, str) or x not in WIDGETS for x in items)
                or len(set(items)) != len(items)):
            raise ValueError('위젯 목록을 확인해 주세요.')
    if not isinstance(result['study_goal'], str) or len(result['study_goal']) > 1000:
        raise ValueError('학습 목표는 1,000자 이내로 입력해 주세요.')
    if result['study_language'] not in ('한국어', '영어', '프랑스어'):
        raise ValueError('학습 언어를 확인해 주세요.')
    return result


def read(app):
    with app.db() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
    try:
        return validate(json.loads(row['value'])) if row else validate({})
    except (ValueError, TypeError, KeyError):
        return validate({})


def save(app, body):
    if not isinstance(body, dict) or set(body) - set(DEFAULT):
        raise ValueError('지원하지 않는 화면 설정입니다.')
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
        previous = validate(json.loads(row['value'])) if row else validate({})
        value = validate({**previous, **body})
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',
                  (KEY, json.dumps(value, ensure_ascii=False)))
    return value
