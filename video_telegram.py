"""Video commands invoked only after the existing Telegram private-owner check."""
import json,re,secrets,urllib.request,urllib.error
import video_production as vp


def get_job(app,jid=''):
 if jid:
  if not re.fullmatch('[a-f0-9]{24}',jid):raise ValueError('올바른 영상 작업 ID를 입력하세요.')
  job=vp.read(vp.root(app)/'jobs'/(jid+'.json'))
 else:job=next((j for j in vp.jobs(app) if j),None)
 if not job:raise ValueError('영상 작업이 없습니다.')
 return job

def video_path(app,jid):
 job=get_job(app,jid)
 if job['state'] not in ('awaiting_review','accepted','rejected'):raise ValueError('아직 생성된 영상이 없습니다.')
 base=vp.root(app)/'renders';path=base/jid/'review-32s.mp4'
 if path.is_symlink() or (base/jid).is_symlink() or not path.is_file() or base.resolve() not in path.resolve().parents:raise ValueError('검증된 로컬 영상 파일이 없습니다.')
 if path.stat().st_size>40*1024**2:raise ValueError('영상이 Telegram 전송 한도보다 큽니다. NAS에서 확인해 주세요.')
 return path

def command(app,cfg,text,key,bridge):
 if text=='/videos':
  s=vp.status(app)
  return ('제작팀 연결됨' if s['worker_online'] else '제작팀 최초 활성화 필요')+'\n'+('\n'.join(f"{j['id']} · {j['title']} · {j['state']} · 장면 {j.get('scene',0)}/6" for j in s['jobs'][:8]) or '영상 작업 없음')
 if text=='/video' or text.startswith('/video '):
  job=vp.submit(app,{'mode':'directed' if text[6:].strip() else 'autonomous','request_key':'telegram:'+cfg.get('generation','')+':'+key,'brief':text[6:].strip() or 'Create a vivid original 30-second story with a clear payoff. Do not copy the reference videos.'})
  return ('기존 작업 진행 중: ' if job.get('existing') else '30초 이상 영상 작업 등록: ')+job['id']+'\n/videos 로 진행 상태를 확인하세요.'
 if text=='/video_result' or text.startswith('/video_result '):
  job=get_job(app,text[len('/video_result'):].strip());video_path(app,job['id'])
  bridge.enqueue(app,cfg,key+':video',job['title']+' · '+job['state'],{'video_job_id':job['id']})
  return '영상 전송을 요청했어요. 검토 후 /video_review '+job['id']+' approve 또는 reject 뒤에 구체적인 피드백을 적어 주세요.'
 if text.startswith('/video_review '):
  parts=text.split(maxsplit=3)
  if len(parts)!=4 or parts[2] not in ('approve','reject'):raise ValueError('/video_review 작업ID approve 또는 reject 피드백')
  result=vp.review(app,{'id':parts[1],'accepted':parts[2]=='approve','feedback':parts[3]})
  return result['message']
 return None

def notifications(app,cfg,bridge):
 for job in vp.jobs(app):
  if not job or job['state'] not in ('awaiting_review','failed'):continue
  key='result:video:'+job['id']+':'+job['state']
  text=job['title']+' · '+job['state']+'\n'+job['id']
  extra=None
  if job['state']=='awaiting_review':
   text+='\n자동 생성 검토본입니다. 품질 승인 전이며 게시되지 않았습니다.'
   try:video_path(app,job['id']);extra={'video_job_id':job['id']}
   except ValueError as error:text+='\n'+str(error)
  else:text+='\n'+job.get('error','실행 실패')
  bridge.enqueue(app,cfg,key,text,extra)

def send_video(app,payload,bridge):
 path=video_path(app,payload['video_job_id']);boundary='AIRI'+secrets.token_hex(16)
 parts=[]
 for name,value in [('chat_id',payload['chat_id']),('caption',payload.get('text','')[:900]),('supports_streaming','true')]:
  parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
 parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="AIRI-video.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
 req=urllib.request.Request('https://api.telegram.org/bot'+bridge.token(app)+'/sendVideo',data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=120) as response:result=json.load(response)
 except urllib.error.HTTPError as error:
  if error.code==400:raise ValueError('Telegram이 영상을 받지 못했습니다. NAS 검토본을 확인하세요.') from None
  raise bridge.TelegramError(error.code) from None
 except OSError:raise bridge.TelegramError() from None
 if not result.get('ok'):raise bridge.TelegramError(result.get('error_code',0))
