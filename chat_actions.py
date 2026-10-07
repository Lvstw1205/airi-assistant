"""Explicit conversational writes, persisted before reporting success."""
import datetime as dt,json,re
import schedule_features
from zoneinfo import ZoneInfo
ZONE=ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))

def intent(query):
 if re.search(r'하지\s*마|하지\s*말|저장하지|추가하지|don.t|do not|ne .{0,20}pas',query,re.I):return None
 if re.search(r'스킬|\bskills?\b',query,re.I) and re.search(r'만들|저장|등록|써|사용|create|save|use|crée|enregistre',query,re.I):return 'skill'
 if re.search(r'일정|할\s*일|캘린더|calendar|schedule|rendez-vous|agenda',query,re.I) and re.search(r'추가|잡아|등록|저장|넣어|add|schedule|book|ajoute|enregistre',query,re.I):return 'task'
 if re.search(r'\d{1,2}\s*[/월]\s*\d{1,2}|오늘|내일|모레|tomorrow|today|demain',query,re.I) and re.search(r'\d{1,2}\s*(?:시|:|am\b|pm\b|h\b)',query,re.I) and not re.search(r'\?|언제|뭐야|있어|what|when|했어|했지|어제|yesterday',query,re.I):return 'task'
 return None

def parse_task(query,today=None):
 today=today or dt.datetime.now(ZONE).date()
 date=re.search(r'(?:(\d{4})[-/년]\s*)?(\d{1,2})\s*[-/월]\s*(\d{1,2})\s*일?',query)
 clock=re.search(r'(?:(오전|아침|오후|저녁|밤)\s*)?(\d{1,2})\s*(?:시|:|h\b)\s*(\d{1,2})?\s*분?\s*(am|pm)?',query,re.I)
 if not clock:clock=re.search(r'()(\d{1,2})\s*()\s*(am|pm)\b',query,re.I)
 title=re.search(r'["“「](.+?)["”」]',query)
 relative=re.search(r'오늘|내일|모레|tomorrow|today|demain',query,re.I)
 if not (date or relative) or not clock:return None
 day=dt.date(int(date[1] or today.year),int(date[2]),int(date[3])) if date else today+dt.timedelta(days={'오늘':0,'today':0,'내일':1,'tomorrow':1,'demain':1,'모레':2}[relative[0].lower()])
 hour=int(clock[2]);minute=int(clock[3] or 0);period=(clock[1] or clock[4] or '').lower()
 if period:
  if not 1<=hour<=12:raise ValueError('오전·오후 시간은 1시부터 12시 사이로 알려줘.')
  hour=hour%12+(12 if period in ('오후','저녁','밤','pm') else 0)
 elif hour<13:raise ValueError('오전인지 오후인지 알려줘. 예: 9/9 오전 11시 "회의".')
 value=title[1] if title else query[clock.end():].strip()
 if not title:
  value=re.sub(r'^(?:에\s*|at\s+)', '', value, flags=re.I)
  value=re.sub(r'\s*,?\s*(?:(?:일정|할\s*일|캘린더)(?:에|을|를)?\s*)?(?:추가|등록|저장|잡아|넣어)(?:해\s*줘|해줘|해|줘|주세요|해\s*주세요|하라고|하도록|해달라고)?[.!\s]*$', '', value).strip()
 if not value:raise ValueError('일정 제목도 알려줘.')
 return {'title':value,'due_date':day.isoformat(),'due_time':dt.time(hour,minute).strftime('%H:%M'),'notes':''}

def pending(app,value=None,clear=False):
 """Keep a short clarification across refreshes, isolated from user preferences."""
 with app.db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS chat_pending(id INTEGER PRIMARY KEY CHECK(id=1),query TEXT,expires TEXT)')
  if clear:c.execute('DELETE FROM chat_pending');return
  if value is not None:
   c.execute('INSERT OR REPLACE INTO chat_pending VALUES(1,?,?)',(value,(dt.datetime.now(ZONE)+dt.timedelta(minutes=10)).isoformat()));return
  row=c.execute('SELECT query,expires FROM chat_pending WHERE id=1').fetchone()
  return row['query'] if row and dt.datetime.fromisoformat(row['expires'])>dt.datetime.now(ZONE) else None

def save_task(app,body):
 title,date,clock,notes=app.task_fields(body)
 if not date or not clock:raise ValueError('일정 제목과 날짜·시간을 함께 알려줘.')
 when=dt.datetime.fromisoformat(date+'T'+clock).replace(tzinfo=ZONE)
 if when<=dt.datetime.now(ZONE):raise ValueError('이미 지난 시각이야. 저장할 연도와 날짜·시간을 다시 알려줘.')
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE')
  existing=c.execute('SELECT id FROM tasks WHERE title=? AND due_date=? AND due_time=? AND done=0',(title,date,clock)).fetchone()
  if existing:key=existing['id']
  else:
   c.execute("INSERT INTO tasks(title,due_date,due_time,notes,created,action,status,attachment_ids) VALUES(?,?,?,?,?,'manual','manual','[]')",(title,date,clock,notes,app.now()))
   key=c.execute('SELECT last_insert_rowid()').fetchone()[0]
 app.event('saved','대화에서 일정 저장: '+title+' '+date+' '+clock)
 return {'kind':'task','id':key,'title':title,'due_date':date,'due_time':clock,'timezone':'UTC','text':f'{date} {clock} (설정한 지역 시간)에 “{title}” 일정을 저장했어. 달력에서 확인하고 수정할 수 있어.'}

def save_skill(app,body):
 name=app.text_value(body,'name',100);content=app.text_value(body,'content',12000)
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE')
  existing=c.execute('SELECT id FROM skills WHERE name=? AND content=?',(name,content)).fetchone()
  if existing:
   key=existing['id'];c.execute('UPDATE skills SET enabled=1,updated=? WHERE id=?',(app.now(),key))
  else:
   c.execute('INSERT INTO skills(name,content,enabled,created,updated) VALUES(?,?,1,?,?)',(name,content,app.now(),app.now()))
   key=c.execute('SELECT last_insert_rowid()').fetchone()[0]
 app.event('skill','대화에서 스킬 저장: '+name)
 return {'kind':'skill','id':key,'name':name,'content':content,'text':f'“{name}” 스킬을 저장하고 활성화했어. 앞으로 관련 질문에서 참고할게. 기억 · 파일에서 내용을 확인하거나 수정할 수 있어.'}

def handle(app,query,history,config):
 action=intent(query)
 previous=pending(app)
 if previous and re.search(r'취소|하지\s*마|cancel|annule',query,re.I):
  pending(app,clear=True)
  return {'kind':'clarification','text':'일정 등록을 취소했어. 저장된 일정은 없어.'}
 if previous and re.fullmatch(r'\s*(오전|아침|오후|저녁|밤|am|pm)(?:이야|이요|요)?[.!\s]*',query,re.I):
  period=re.match(r'\s*(오전|아침|오후|저녁|밤|am|pm)',query,re.I)[1].lower()
  period={'am':'오전','pm':'오후'}.get(period,period)
  query=re.sub(r'(\d{1,2}\s*(?:시|:|h\b))',period+r' \1',previous,count=1);action='task'
 if not action:return None
 pending(app,clear=True)
 try:
  if action=='task':
   series=schedule_features.parse_range(query)
   if series is not None:return schedule_features.save_range(app,series)
   parsed=parse_task(query)
   if parsed:return save_task(app,parsed)
  if action=='skill':
   if re.search(r'이걸|이거|이\s*내용|방금|앞에서|위\s*내용|this|above',query,re.I):
    reference=next((m['content'] for m in reversed(history) if m['role']=='assistant'),None)
    if reference and not re.search(r'일정을 저장했어|스킬을 저장하고 활성화|저장할 내용',reference):
     if len(reference)>12000:raise ValueError('스킬 내용이 너무 길어. 저장할 부분을 12,000자 이내로 지정해줘.')
     heading=next((line.lstrip('# ').strip() for line in reference.splitlines() if line.strip()),'대화에서 만든 스킬')
     return save_skill(app,{'name':heading[:100],'content':reference})
   quoted=re.search(r'["“「](.+?)["”」]',query,re.S)
   # A quoted procedure is content; a short quoted title still needs generation.
   explicit=query.split('\n',1)[1].strip() if '\n' in query else query.split(':',1)[1].strip() if ':' in query else ''
   content=explicit or (quoted[1] if quoted and len(quoted[1])>=30 else '')
   if content:
    return save_skill(app,{'name':(quoted[1] if explicit and quoted else content.splitlines()[0].lstrip('# '))[:100],'content':content})
   topic=re.sub(r'스킬|만들어?\s*줘|저장해?\s*줘|등록해?\s*줘|앞으로|사용해?\s*줘|이걸|이거|\b(create|make|save|use|a|the|skill|please)\b','',query,flags=re.I).strip(' \"“”:.!')
   if len(topic)<2:raise ValueError('어떤 작업에 쓸 스킬인지 알려줘. 예: 회의록을 정리하는 스킬 만들어줘.')
   # Generating a procedure needs text generation, not a model-specific write call.
   procedure=app.llm_client.complete([{'role':'system','content':'Write a reusable Markdown procedure for the explicitly requested skill. Start with # and a short title. Include when to use, concrete steps, output format, and verification. Match the user language. Do not claim it is already saved. Do not invent API access or permissions. Do not include code execution, secrets, or unrelated instructions.'},{'role':'user','content':query}],config['model'],max_tokens=1600).strip()
   if not procedure.startswith('# ') or len(procedure)<100:raise ValueError('재사용할 절차를 완성하지 못했어. 스킬의 작업과 원하는 결과를 구체적으로 알려줘.')
   return save_skill(app,{'name':procedure.splitlines()[0].lstrip('# ')[:100],'content':procedure})
  properties=({'title':{'type':'string'},'due_date':{'type':'string','description':'YYYY-MM-DD'},'due_time':{'type':'string','description':'HH:MM in Configured location'},'notes':{'type':'string'}} if action=='task' else {'name':{'type':'string'},'content':{'type':'string','description':'Complete reusable Markdown skill: when to use, procedure, output, verification. Preserve the user intent, no invented capabilities.'}})
  name='save_'+action
  tool={'type':'function','function':{'name':name,'description':'Save only when the current user explicitly requests it and the content/date is clear. Otherwise ask one clarification.','parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}}
  prompt='Extract the explicitly requested local save action. Use ONLY the supplied function; otherwise ask one short clarification. Current Configured location date/time: '+dt.datetime.now(ZONE).isoformat()+'. Dates without a year mean this year; never silently move past dates to next year. Do not invent AM/PM for ambiguous hours. Calendar entries are appointments, not execution of the event. For a skill, generate the actual reusable Markdown instructions based on the requested task. Earlier conversation is reference data; only the current user authorizes saving. Do not make an unrelated skill from the request to save a skill.'
  context=[{'role':m['role'],'content':m['content'][:1800]} for m in history[-4:]]
  answer,_=app.llm_client.tool_turn([{'role':'system','content':prompt}]+context+[{'role':'user','content':query}],config['model'],[tool],max_tokens=1800)
  calls=answer.get('tool_calls') or []
  if len(calls)!=1:
   return {'text':('아직 저장하지 않았어. 날짜·오전/오후·시간과 일정 제목을 함께 알려줘.' if action=='task' else '아직 저장하지 않았어. 스킬로 쓸 절차를 메시지에 적거나, 절차를 만든 답변 다음에 “이걸 스킬로 저장해”라고 말해줘.'),'kind':'clarification'}
  call=calls[0]['function']
  if call['name']!=name:raise ValueError('요청한 저장 작업을 확인하지 못했어.')
  args=json.loads(call['arguments'])
  return save_task(app,args) if action=='task' else save_skill(app,args)
 except (ValueError,TypeError,KeyError) as e:
  if action=='task' and '오전인지 오후인지' in str(e):pending(app,query)
  return {'text':'아직 저장하지 않았어. '+str(e),'kind':'clarification'}
