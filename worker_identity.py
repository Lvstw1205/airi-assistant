"""Answer identity and worker questions from measured state, never model guesses."""
import re,time
from datetime import datetime
from zoneinfo import ZoneInfo
import mac_cluster
IDENTITY='나는 User의 개인 비서 아이리(AIRI)야. 새 Mac의 AIRI가 대화·음성·카메라·무거운 영상 작업을 맡고, M1 작업자는 문서·기획·검수 같은 백그라운드 텍스트 작업을 맡아.'
WORKER=re.compile(r'(?<![a-z0-9])m1(?![a-z0-9])|작업자|분산|썬더볼트|선더볼트|thunderbolt|센서\s*(?:연결|설치)|\bworker\b',re.I)
QUESTION=re.compile(r'상태|연결|뭐|무슨|어떤|역할|역활|일하|하니|하는|하고|돌아|확인|작동|센서|알아|아니|몰라|정보|뭔|왜|인지|있어|status|connect|working|doing|role|sensor|what|how|who',re.I)
IDENTITY_QUERY=re.compile(r'^\s*(?:야\s*)?(?:(?:너|넌|너는|너의|네|아이리|airi)[, ]*)?(?:누구(?:야|니|여)?|정체(?:가|는)?\s*(?:뭐야|뭐여|뭔데)?|자기\s*소개(?:해줘|해|좀)?|who are you)[.!?\s]*$',re.I)

def relevant(query):return bool(WORKER.search(query) and QUESTION.search(query))
def when(epoch):return datetime.fromtimestamp(epoch,ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%m월 %d일 %H:%M') if epoch else '시각 미확인'

def describe(app,query=''):
 s=mac_cluster.status(app)
 if not s.get('checked_at') or s.get('stale'):mac_cluster.refresh(app);s=mac_cluster.status(app)
 parts=[IDENTITY]
 if not s.get('connected'):
  parts.append('지금은 M1 작업자 연결을 확인하지 못했어. 연결돼 있거나 일을 처리 중이라고 말할 수 없어.')
 else:
  parts.append('지금 M1은 '+(s.get('transport',{}).get('label') or '인증된 SSH')+'로 연결돼 있어. '+('모델 서비스는 응답하지 않아.' if s.get('state')=='ollama_offline' else '자동 배정은 '+('켜져 있어.' if s['routing']['enabled'] else '꺼져 있어.')))
  active=s.get('active_job') or next((j for j in (s.get('office') or {}).get('jobs',[]) if j.get('state')=='running'),None)
  if active:parts.append('현재 M1에서 '+(active.get('purpose') or active.get('title') or '텍스트 작업')+'을 처리 중이야.')
  else:parts.append('현재 확인된 M1 실행 작업은 없어. 연결돼 있다고 계속 일하는 건 아니고, 맡길 작업이 오면 처리해.')
  complete=next((j for j in s.get('recent_jobs',[]) if j.get('node')=='M1' and j.get('state')=='completed'),None)
  if complete:parts.append('최근 M1 완료 기록: '+when(complete.get('finished_at'))+' · '+complete['purpose']+' · '+str(complete['seconds'])+'초.')
 last=s.get('last_job') or {}
 if last.get('fallback'):
  parts.append('가장 최근 '+last.get('purpose','작업')+'은 새 Mac에서 대신 처리했어. '+(mac_cluster.REASONS.get(last.get('reason')) or '당시 넘어간 이유는 이전 버전이 기록하지 않아 확인할 수 없어.'))
 if re.search(r'센서|온도|ram|cpu|gpu',query,re.I):
  parts.append('M1 상태 측정 프로그램은 '+('설치돼 있어.' if 'hardware_metrics' in s.get('capabilities',[]) else '아직 설치되지 않았어. 별도 센서를 연결하라는 뜻은 아니고, CPU·RAM·온도를 읽는 소프트웨어가 필요하다는 뜻이야. 작업자 연결과는 별개야.'))
 parts.append('작업실의 AI 직원은 노아(기획), 루미(문서), 레오·이안(분석), 모아(초안 점검), 세라(M6 자동 보고서 검수)야. 자동 보고서만 M1 초안 다음에 M6 검수·보강을 거쳐.')
 parts.append('내 Mac 위젯의 작업실에서 부서별 작업을 맡기고 진행 상황과 결과를 볼 수 있어.')
 return '\n\n'.join(parts)

def reply(app,query):
 if IDENTITY_QUERY.fullmatch(query):return IDENTITY
 if relevant(query):
  # Actual task content must not be mistaken for a status question.
  if re.search(r'번역해|요약해|작성해|초안.*써|translate|summari[sz]e|write a',query,re.I):return None
  return describe(app,query)
 return None

def context(app,query):
 return IDENTITY+' 연결·실행 상태를 질문하면 측정 결과로 답하고, 조회하지 않은 작업이나 센서 값을 지어내지 않는다.'
