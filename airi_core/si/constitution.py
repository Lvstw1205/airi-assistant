"""Capability-neutral skill proposals with explicit review and reversible versions."""
import difflib,hashlib,json,re,time

def validate_candidate(candidate,cfg,allowed_tools):
    fields={'name','description','tool_profile','procedure','done','references'}
    if not isinstance(candidate,dict) or set(candidate)!=fields:raise ValueError('스킬 초안 필드를 확인해줘.')
    if any(not isinstance(candidate[x],str) or not candidate[x].strip() for x in ('name','description','procedure','done')):raise ValueError('스킬 이름, 목적, 절차, 완료 조건이 필요해.')
    if not isinstance(candidate['references'],list) or any(not isinstance(x,str) for x in candidate['references']):raise ValueError('출처 형식을 확인해줘.')
    profile=candidate['tool_profile']
    if not isinstance(profile,list) or any(x not in allowed_tools for x in profile):raise ValueError('스킬은 기존 허용 도구만 조합할 수 있어.')
    raw=json.dumps(candidate,ensure_ascii=False)
    if len(raw.encode())>cfg['max_skill_bytes']:raise ValueError('스킬 크기 상한을 넘었어.')
    if any(p.casefold() in raw.casefold() for p in cfg['protected_files']):raise ValueError('정체성, 코드와 권한은 SI 수정 대상이 아니야.')
    if re.search(r'(?:disable|bypass|expand).{0,30}(?:gate|permission|network)|권한.{0,8}(?:확장|상향)|게이트.{0,8}(?:우회|해제)',raw,re.I):raise ValueError('스킬로 권한을 넓힐 수 없어.')
    return hashlib.sha256(raw.encode()).hexdigest()

def version_diff(old,new):
    return ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='previous',tofile='candidate'))

def may_apply(*,owner_approved,regressions,evaluation_days,cfg):
    return bool(owner_approved and regressions==0 and evaluation_days>=cfg['minimum_evaluation_days'])

def skill_state(successes,consecutive_failures,cfg):
    if consecutive_failures>=cfg['demote_consecutive_failures']:return 'provisional'
    return 'trusted' if successes>=cfg['trusted_successes'] else 'provisional'
