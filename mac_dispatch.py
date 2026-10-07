"""Transport and routing for pure background inference; no external side effects.

Staged for integration after M1 identity, model inventory and SSH pairing are
verified. Does not configure networking, install keys, or run at import time.
"""
import ipaddress
import json
from pathlib import Path
import re
import subprocess


def ssh_command(host, username, key, known_hosts):
    address = ipaddress.ip_address(host)
    networks = ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','fc00::/7')
    if not any(address in ipaddress.ip_network(n) for n in networks):
        raise ValueError('Worker must be on the private local network.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}', username):
        raise ValueError('Invalid worker account.')
    if not Path(key).is_file() or not Path(known_hosts).is_file():
        raise ValueError('Worker SSH pairing is incomplete.')
    return ['/usr/bin/ssh','-F','/dev/null','-T','-i',str(key),
            '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+json.dumps(str(known_hosts)),'-o','ConnectTimeout=3',
            '-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2',
            username+'@'+host,'airi-worker']


def exchange(command, request, timeout=135):
    data=json.dumps(request).encode()
    if len(data)>160000:raise ValueError('Worker input is too large.')
    try:
        result=subprocess.run(command,input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              timeout=timeout,check=True)
        if len(result.stdout)>256000:raise ValueError()
        envelope=json.loads(result.stdout)
        if envelope.get('ok') is not True or envelope['result'].get('version')!=1:raise ValueError()
        return envelope['result']
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise ValueError('M1 worker unavailable or returned an incomplete result.') from None


def can_offload(model, local_models, remote_models, paired):
    """A shared model name is insufficient: compare model digests too."""
    if not paired:return False
    local=next((m.get('digest') for m in local_models if m.get('name')==model),None)
    remote=next((m.get('digest') for m in remote_models if m.get('name')==model),None)
    return bool(local and local==remote)


def background_complete(messages, model, max_tokens, remote_call, local_call, eligible):
    if eligible:
        try:
            answer=remote_call({'version':1,'action':'complete','model':model,
                                'messages':messages,'max_tokens':max_tokens})
            if answer.get('model')!=model or not isinstance(answer.get('text'),str) or not answer['text'].strip():
                raise ValueError('Invalid worker completion.')
            return {'text':answer['text'],'node':'M1','fallback':False}
        except ValueError:
            # Safe only for pure, buffered text inference. Never repeat tools,
            # file writes, sends, or other side effects via this fallback path.
            return {'text':local_call(messages,model,max_tokens),'node':'primary','fallback':True}
    return {'text':local_call(messages,model,max_tokens),'node':'primary','fallback':False}
