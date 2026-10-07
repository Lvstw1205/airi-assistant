"""Owner-only Stock101 inspection. Every local request is an authenticated GET."""
import re

HELP='\n모의매매 또는 /stock: Stock101 상태·손익·보유·체결·전략 조회'
PAGES={'status','positions','fills','strategies'}
MODES={'paper','live'}

def show(app,cfg,key,mode,view,bridge):
    if mode not in MODES or view not in PAGES:raise ValueError('Stock101 조회 버튼을 다시 확인해 주세요.')
    try:result=bridge.local(app,f'stock101/crypto/telegram?mode={mode}&view={view}',timeout=12)
    except (OSError,ValueError):raise ValueError('Stock101 상태 조회를 완료하지 못했습니다. Mac의 AIRI 실행 상태를 확인하고 /stock으로 다시 조회하세요.') from None
    bridge.enqueue(app,cfg,key+':stock101',result['text'],{'reply_markup':result['reply_markup'],'protect_content':True})
    return ''

def command(app,cfg,text,key,bridge):
    if '모의매매' in text or text in ('/start stock101','스톡101','Stock101','stock101','자동매매 상태'):
        return show(app,cfg,key,'paper','status',bridge)
    parts=text.split();head=parts[0].split('@')[0].lower() if parts else ''
    if head not in ('/stock','/stock101'):return None
    if '@' in parts[0] and parts[0].split('@',1)[1].lower()!=cfg.get('bot_username','').lower():return None
    mode='paper';view='status';args=parts[1:]
    if args and args[0].lower() in MODES:mode=args.pop(0).lower()
    if args and args[0].lower() in PAGES:view=args.pop(0).lower()
    if args:return 'Stock101은 텔레그램에서 조회만 지원합니다. /stock을 보내고 상태·보유·체결·전략 버튼을 누르세요. 매수·매도·시작·중지는 실행하지 않았습니다.'
    return show(app,cfg,key,mode,view,bridge)

def callback(app,cfg,data,key,bridge):
    match=re.fullmatch(r'st101:(paper|live):(status|positions|fills|strategies)',data)
    if not match:raise ValueError('Stock101 조회 버튼을 다시 확인해 주세요.')
    return show(app,cfg,key,*match.groups(),bridge)
