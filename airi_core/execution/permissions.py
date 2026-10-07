import hashlib
import json
from pathlib import Path
import re
import shlex
import time
import uuid
from airi_node.ledger import encoded

TIERS=('READ_ONLY','LOW_RISK_WRITE','CONFIRM_REQUIRED','BLOCKED')

def redact(value):
    if isinstance(value,dict):
        return {k:'[REDACTED]' if re.search(r'token|password|secret|authorization|api.?key|email.?body',k,re.I) else redact(v) for k,v in value.items()}
    if isinstance(value,list):return [redact(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)(?:Bearer\s+|sk-[a-zA-Z0-9_-]{8,}|hsurr:)[^\s\"\']*','[REDACTED]',value)
        value=re.sub(r'(?i)\b(token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',value)
        value=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',value)
        return value[:8000]
    return value


def classify_shell(command,root):
    """Classify only. No shell evaluator or privileged executor is exposed."""
    if not isinstance(command,str) or len(command)>4000 or any(x in command for x in ('\x00','\n','\r','`','$(', '${')):
        return 'DANGEROUS','BLOCKED'
    try:tokens=list(shlex.shlex(command,posix=True,punctuation_chars=';&|<>()'))
    except ValueError:return 'DANGEROUS','BLOCKED'
    if not tokens:return 'DANGEROUS','BLOCKED'
    if any(t in ('|','||','&&',';','>','>>','<','(',')','&') for t in tokens):return 'DANGEROUS','CONFIRM_REQUIRED'
    name=Path(tokens[0]).name;args=tokens[1:]
    if name in ('security','networksetup','sudo','eval','sh','bash','zsh','osascript') or name=='defaults' and 'write' in args:
        return 'DANGEROUS','BLOCKED'
    if name in ('rm','rmdir','mv','chmod','chown','curl','wget'):
        return 'DANGEROUS','CONFIRM_REQUIRED'
    safe={'ls','cat','head','tail','grep','rg','pwd','which','df','du','ps'}
    if name=='find' and any(x in args for x in ('-delete','-exec','-execdir','-ok','-okdir','-fprint','-fprintf','-fls')):return 'DANGEROUS','CONFIRM_REQUIRED'
    if name=='git':
        if not args or args[0] not in ('status','diff','log') or any(x.startswith(('--output','--ext-diff','--textconv','-c')) for x in args):return 'DANGEROUS','CONFIRM_REQUIRED'
    elif name=='ollama' and args!=['list']:return 'DANGEROUS','CONFIRM_REQUIRED'
    elif name=='top' and args!=['-l','1']:return 'DANGEROUS','CONFIRM_REQUIRED'
    elif name not in safe|{'find','ollama','top'}:return 'DANGEROUS','CONFIRM_REQUIRED'
    # Reject options which launch programs or write outputs even on read-like commands.
    if any(x.startswith(('--pre','--hostname-bin','--pager','--exec','--output','--search-zip')) for x in args):return 'DANGEROUS','CONFIRM_REQUIRED'
    for arg in args:
        if arg.startswith('/') or arg.startswith('~'):
            p=Path(arg).expanduser().resolve()
            if not p.is_relative_to(Path(root).resolve()) and not p.is_relative_to(Path('/private/tmp')):
                return 'DANGEROUS','CONFIRM_REQUIRED'
        if '..' in Path(arg).parts:return 'DANGEROUS','CONFIRM_REQUIRED'
    return 'SAFE','READ_ONLY'


class PermissionGate:
    def __init__(self,ledger):
        self.ledger=ledger
        with ledger.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS airi_exec_approval_usage(approval_id TEXT PRIMARY KEY, consumed REAL NOT NULL)')

    def check(self,tool_id,args,tier,task_id=None,actor='airi',approval_id=None,reversible=False):
        if tier not in TIERS:raise ValueError('Unknown permission tier')
        signature=hashlib.sha256(encoded([tool_id,args,task_id]).encode()).hexdigest()
        now=self.ledger.clock()
        with self.ledger.db(True) as c:
            c.execute("UPDATE airi_exec_approvals SET state='EXPIRED',decided=? WHERE state='PENDING' AND expires<=?",(now,now))
            outcome='ALLOW';approval=None
            if tier=='BLOCKED':outcome='BLOCKED'
            elif tier=='LOW_RISK_WRITE' and not reversible:outcome='DENY'
            elif tier=='CONFIRM_REQUIRED':
                prior=c.execute('SELECT * FROM airi_exec_approvals WHERE approval_id=?',(approval_id,)).fetchone() if approval_id else None
                metadata=json.loads(prior['args_redacted_json']) if prior else {}
                used=c.execute('SELECT 1 FROM airi_exec_approval_usage WHERE approval_id=?',(approval_id,)).fetchone()
                if prior and prior['state']=='GRANTED' and prior['expires']>now and metadata.get('signature')==signature and not used:
                    c.execute('INSERT INTO airi_exec_approval_usage VALUES(?,?)',(approval_id,now))
                else:
                    outcome='WAITING_APPROVAL'
                    approval=str(uuid.uuid4())
                    c.execute('INSERT INTO airi_exec_approvals VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (approval,task_id,tool_id,tier,tool_id+' 요청',encoded({'arguments':redact(args),'signature':signature}),
                         'PENDING',now,now+600,None,None))
                    self.ledger.event(c,'APPROVAL_REQUESTED',data={'approval_id':approval,'task_id':task_id,'tool_id':tool_id})
            c.execute('INSERT INTO airi_exec_audit(ts,task_id,actor,action,tier,result,detail_json) VALUES(?,?,?,?,?,?,?)',
                (now,task_id,actor,tool_id,tier,outcome,encoded(redact(args))))
        return {'allowed':outcome=='ALLOW','status':outcome,'approval_id':approval}

    def decide(self,identifier,allow,channel,owner_authenticated):
        if not owner_authenticated or channel not in ('ui','telegram'):raise PermissionError('Owner authentication required')
        now=self.ledger.clock()
        with self.ledger.db(True) as c:
            row=c.execute('SELECT * FROM airi_exec_approvals WHERE approval_id=?',(identifier,)).fetchone()
            if not row:raise ValueError('Unknown approval')
            state='EXPIRED' if row['expires']<=now else 'GRANTED' if allow else 'DENIED'
            if row['state']!='PENDING':return row['state']
            c.execute('UPDATE airi_exec_approvals SET state=?,decided=?,via=? WHERE approval_id=?',(state,now,channel,identifier))
            c.execute('INSERT INTO airi_exec_audit(ts,task_id,actor,action,tier,result,detail_json) VALUES(?,?,?,?,?,?,?)',
                      (now,row['task_id'],'owner',row['tool_id'],row['tier'],state,encoded({'channel':channel})))
            self.ledger.event(c,'APPROVAL_GRANTED' if state=='GRANTED' else 'APPROVAL_DENIED',data={'approval_id':identifier})
        return state

    def pending(self):
        now=self.ledger.clock()
        with self.ledger.db(True) as c:
            c.execute("UPDATE airi_exec_approvals SET state='EXPIRED',decided=? WHERE state='PENDING' AND expires<=?",(now,now))
            return [dict(r) for r in c.execute("SELECT approval_id,tool_id,summary,tier,state,requested,expires,args_redacted_json FROM airi_exec_approvals WHERE state='PENDING' ORDER BY requested")]
