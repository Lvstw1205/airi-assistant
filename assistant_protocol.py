"""Persistent handoffs and explicit user preferences, not model weight training."""
import datetime as dt,json,re
from zoneinfo import ZoneInfo

def init(app):
 with app.db() as c:c.execute('CREATE TABLE IF NOT EXISTS work_journals(id INTEGER PRIMARY KEY,content TEXT NOT NULL,created TEXT NOT NULL)')

def context(app):
 rows=app.rows('SELECT content FROM work_journals ORDER BY id DESC LIMIT 1')
 return rows[0]['content'][:2200] if rows else '저장된 업무일지 없음. 이전 작업을 기억한다고 말하지 않는다.'

def build_journal(app):
 day=dt.datetime.now(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).date().isoformat()
 events=app.rows("SELECT detail FROM events WHERE kind IN ('saved','skill') ORDER BY id DESC LIMIT 3")
 tasks=app.rows("SELECT title,due_date,due_time FROM tasks WHERE done=0 AND archived_at='' ORDER BY CASE WHEN due_date='' THEN 1 ELSE 0 END,due_date,due_time LIMIT 5")
 errors=app.rows("SELECT detail FROM events WHERE kind IN ('error','blocked') ORDER BY id DESC LIMIT 2")
 preferences=app.rows("SELECT content FROM memories WHERE content LIKE '확인한 선호:%' ORDER BY id DESC LIMIT 3")
 def join(items):return '; '.join(items) or '확인된 기록 없음'
 return f'## {day} | AIRI 업무 인수인계\n- 결정: '+join([e['detail'][:140] for e in events])+ '\n- 미결: '+join([f"{t['due_date']} {t['due_time']} {t['title']}" for t in tasks])+ '\n- 실수/막힌 곳: '+join([e['detail'][:140] for e in errors])+ '\n- 선호 확인: '+join([m['content'][7:][:180] for m in preferences])+ '\n- 다음 액션: '+('달력의 미완료 일정을 확인하고 다음 작업을 진행한다.' if tasks else 'User의 다음 목적과 결과물을 확인한다.')

def save_journal(app):
 content=build_journal(app)
 with app.db() as c:
  row=c.execute('SELECT id,content FROM work_journals ORDER BY id DESC LIMIT 1').fetchone()
  if row and row['content']==content:return content
  c.execute('INSERT INTO work_journals(content,created) VALUES(?,?)',(content,app.now()))
 return content

def handle(app,query):
 if re.fullmatch(r'\s*(?:업무\s*)?일지(?:\s*(?:작성|저장|보여줘|써줘|정리해줘|작성해줘|저장해줘))?[.!?\s]*',query):return save_journal(app)
 match=re.fullmatch(r'\s*(?:선호\s*저장|답변\s*규칙\s*저장|기억해)\s*[:：]\s*(.{1,1200})',query,re.S)
 if match:
  content='확인한 선호: '+match[1].strip()
  with app.db() as c:
   if not c.execute('SELECT 1 FROM memories WHERE content=?',(content,)).fetchone():c.execute('INSERT INTO memories(content,created) VALUES(?,?)',(content,app.now()))
  return '그 내용을 선호로 저장했어. 다음 대화부터 참고할게.'
 return None

def route(app,query,config):
 accuracy=bool(re.search(r'금액|환율|시세|전망|법률|자격|계산|투자|전략|디버깅|오류|코드|날짜|금리|\b(financ|legal|debug|strateg|invest|forecast|code)',query,re.I))
 routine=bool(re.search(r'번역|요약|포맷|분류|태깅|\b(translat|summari|format|classify)',query,re.I))
 tier='고급' if accuracy else '간단' if routine or len(query)<80 else '일반'
 if not accuracy and app.agent_runtime.is_social(query):tier='일반'
 selected=config['model'];reason='직접 선택한 모델'
 if config.get('model')=='airi:auto':
  selected='openai:auto'
  cloud=app.llm_client.registered_openai('openai:auto')
  if cloud:
   target={'간단':'gpt-4.1-mini','일반':'gpt-5.6-terra','고급':'gpt-6-astra'}[tier]
   selected='openai:auto@'+target;reason='작업 복잡도에 따른 자동 선택'
  else:reason='OpenAI 연결 없음 · 임의 로컬 전환 중단'
 return {**config,'model':selected},{'tier':tier,'accuracy':'정확도 우선' if accuracy else '속도 우선','reason':reason}
