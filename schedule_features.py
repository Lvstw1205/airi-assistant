"""Local calendar ranges, durable reminder receipts, and read-result cleanup."""
import datetime as dt
import json,re,secrets,math
from zoneinfo import ZoneInfo
ZONE=ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))

def init(app):
 with app.db() as c:
  columns={r['name'] for r in c.execute('PRAGMA table_info(tasks)')}
  for name in ('end_time','group_id','read_at','archived_at'):
   if name not in columns:c.execute('ALTER TABLE tasks ADD COLUMN '+name+" TEXT NOT NULL DEFAULT ''")
  if 'reminder_minutes' not in columns:c.execute("ALTER TABLE tasks ADD COLUMN reminder_minutes TEXT NOT NULL DEFAULT '[30,10080]'")
  c.execute('CREATE TABLE IF NOT EXISTS reminder_receipts(task_id INTEGER,due TEXT,minutes INTEGER,delivered TEXT,PRIMARY KEY(task_id,due,minutes))')

def end_time(body,start):
 value=body.get('end_time','')
 if not isinstance(value,str):raise ValueError('종료 시간을 확인해 주세요.')
 if value:
  if not start or not re.fullmatch(r'\d{2}:\d{2}',value):raise ValueError('시작·종료 시간을 함께 지정하세요.')
  dt.time.fromisoformat(value)
  if value<=start:raise ValueError('종료 시간은 같은 날 시작 시간보다 뒤로 지정하세요.')
 return value

def reminder_settings(value):
 if not isinstance(value,list) or len(value)>12 or any(type(v) is not int or not 0<=v<=43200 for v in value):raise ValueError('알림은 시작 시각부터 30일 전까지, 최대 12개로 지정하세요.')
 return json.dumps(sorted(set(value)))

def duration_label(minutes):
 if minutes==0:return '지금'
 if minutes%10080==0:return str(minutes//10080)+'주일'
 parts=[]
 for size,unit in ((1440,'일'),(60,'시간'),(1,'분')):
  count,minutes=divmod(minutes,size)
  if count:parts.append(str(count)+unit)
 return ' '.join(parts)

def parse_range(query,today=None):
 today=today or dt.datetime.now(ZONE).date()
 dates=re.search(r'(?:(\d{4})\s*년\s*)?(\d{1,2})\s*[/월]\s*(\d{1,2})\s*일?\s*(?:부터|~|～|–)\s*(?:(\d{1,2})\s*[/월]\s*)?(\d{1,2})\s*일?(?:까지)?',query)
 if not dates:return None
 first=dt.date(int(dates[1] or today.year),int(dates[2]),int(dates[3]));last=dt.date(first.year,int(dates[4] or first.month),int(dates[5]))
 if not 0<=(last-first).days<366:raise ValueError('종료일은 시작일 이후, 1년 이내로 알려줘.')
 clock=re.search(r'(?:(오전|아침|오후|저녁|밤)\s*)?(\d{1,2})\s*(?:시|:)\s*(\d{1,2})?\s*분?\s*(?:부터|~|～|–)\s*(?:(오전|아침|오후|저녁|밤)\s*)?(\d{1,2})\s*(?:시|:)\s*(\d{1,2})?\s*분?\s*(?:까지)?',query[dates.end():])
 if not clock:raise ValueError('기간 일정의 시작·종료 시간을 알려줘. 예: 저녁 6시15분부터 8시15분까지 수업.')
 def clock_value(period,hour,minute):
  hour=int(hour)
  if period:
   if not 1<=hour<=12:raise ValueError('오전·오후 시간은 1~12시로 알려줘.')
   hour=hour%12+(12 if period in ('오후','저녁','밤') else 0)
  elif hour<13:raise ValueError('오전인지 오후인지 함께 알려줘.')
  return dt.time(hour,int(minute or 0)).strftime('%H:%M')
 start=clock_value(clock[1],clock[2],clock[3]);end=clock_value(clock[4] or clock[1],clock[5],clock[6]);end_time({'end_time':end},start)
 quoted=re.search(r'["“「](.+?)["”」]',query)
 title=quoted[1] if quoted else query[dates.end()+clock.end():].strip()
 title=re.sub(r'\s*,?\s*(?:매일\s*)?(?:일정(?:에|을|를)?\s*)?(?:등록|추가|저장)(?:해\s*줘|해줘|해|줘|해주세요|하라고|하도록|해달라고)?[.!\s]*$','',title).strip()
 if not title:raise ValueError('반복할 일정 제목을 알려줘.')
 days=[first+dt.timedelta(days=i) for i in range((last-first).days+1)]
 if re.search(r'평일|주말\s*제외',query):days=[d for d in days if d.weekday()<5]
 return [{'title':title,'due_date':d.isoformat(),'due_time':start,'end_time':end,'notes':''} for d in days]

def save_range(app,items):
 if not items:raise ValueError('등록할 날짜가 없습니다.')
 values=[];current=dt.datetime.now(ZONE)
 for item in items:
  title,date,start,notes=app.task_fields(item);end=end_time(item,start)
  if dt.datetime.fromisoformat(date+'T'+start).replace(tzinfo=ZONE)<=current:raise ValueError('기간에 이미 지난 시각이 있어. 앞으로 등록할 시작 날짜를 다시 알려줘.')
  values.append((title,date,start,end,notes))
 ids=[];group=secrets.token_hex(12)
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE')
  for title,date,start,end,notes in values:
   existing=c.execute('SELECT id FROM tasks WHERE title=? AND due_date=? AND due_time=? AND end_time=? AND done=0 AND archived_at=\'\'',(title,date,start,end)).fetchone()
   if existing:ids.append(existing['id']);continue
   c.execute("INSERT INTO tasks(title,due_date,due_time,end_time,notes,created,action,status,attachment_ids,group_id) VALUES(?,?,?,?,?,?,'manual','manual','[]',?)",(title,date,start,end,notes,app.now(),group))
   ids.append(c.execute('SELECT last_insert_rowid()').fetchone()[0])
 title,first,start,end,_=values[0];last=values[-1][1]
 app.event('saved',f'기간 일정 저장: {title} · {first} ~ {last} · {len(ids)}개')
 return {'kind':'task','id':ids[0],'ids':ids,'count':len(ids),'title':title,'due_date':first,'last_date':last,'due_time':start,'end_time':end,'text':f'{first}부터 {last}까지 {start}~{end}, “{title}” 일정 {len(ids)}개를 달력에 저장했어. 설정한 지역 시간 기준이야.'}

def mark_read(app,key):
 with app.db() as c:
  c.execute("UPDATE tasks SET read_at=? WHERE id=? AND read_at='' AND status IN ('completed','partial','failed','unknown')",(app.now(),key))
 return {'ok':True}

def cleanup(app):
 cutoff=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=3)).isoformat()
 with app.db() as c:
  c.execute("UPDATE tasks SET archived_at=? WHERE read_at<>'' AND read_at<=? AND archived_at='' AND status IN ('completed','partial','failed','unknown')",(app.now(),cutoff))

def claim_reminder(app,current=None):
 current=current or dt.datetime.now(dt.timezone.utc)
 with app.db() as c:
  c.execute('BEGIN IMMEDIATE')
  tasks=c.execute("SELECT id,title,due_date,due_time,reminder_minutes FROM tasks WHERE done=0 AND archived_at='' AND due_date<>'' AND status IN ('manual','scheduled','awaiting_approval') ORDER BY due_date,due_time").fetchall()
  for task in tasks:
   try:due=dt.datetime.fromisoformat(task['due_date']+'T'+(task['due_time'] or '09:00')).replace(tzinfo=ZONE)
   except ValueError:continue
   stamp=due.isoformat()
   offsets=sorted(json.loads(task['reminder_minutes']))
   for minutes in offsets:
    if not task['due_time'] and minutes<1440:continue
    lag=(current-(due-dt.timedelta(minutes=minutes))).total_seconds()
    if not 0<=lag<(900 if minutes==0 else min(900,minutes*60)):continue
    receipt=c.execute('INSERT OR IGNORE INTO reminder_receipts VALUES(?,?,?,?)',(task['id'],stamp,minutes,app.now()))
    if receipt.rowcount:
     # After a pause, deliver the nearest alert once rather than replaying a
     # backlog of earlier offsets for the same appointment.
     for earlier in offsets:
      if earlier>minutes and 0<=(current-(due-dt.timedelta(minutes=earlier))).total_seconds()<900:
       c.execute('INSERT OR IGNORE INTO reminder_receipts VALUES(?,?,?,?)',(task['id'],stamp,earlier,app.now()))
     remaining=max(0,math.ceil((due-current).total_seconds()/60))
     text=(f'User, 지금 {task["title"]} 할 시간이야.' if minutes==0 and lag<60 else f'User, {task["title"]} 시작 시각이 {math.ceil(lag/60)}분 지났어.' if minutes==0 else f'User, {task["title"]}까지 {duration_label(remaining)} 남았어.')
     return {'id':task['id'],'title':task['title'],'text':text,'minutes':minutes,'due_date':task['due_date']}
 return None
