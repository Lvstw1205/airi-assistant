import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque


def signature(secret, method, path, ts, nonce, body):
    value = '\n'.join((method.upper(), path, str(ts), nonce, hashlib.sha256(body).hexdigest()))
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def header(secret, node_id, method, path, body=b'', now=None, nonce=None):
    ts = int(time.time() if now is None else now)
    nonce = nonce or secrets.token_hex(16)
    return f'AIRI {node_id}:{ts}:{nonce}:{signature(secret, method, path, ts, nonce, body)}'


class Auth:
    def __init__(self, config, secret, clock=time.time):
        self.config, self.secret, self.clock = config, secret, clock
        self.nonces, self.windows, self.lock = {}, defaultdict(deque), threading.Lock()

    def verify(self, authorization, method, path, body):
        try:
            scheme, value = authorization.split(' ', 1)
            node, ts, nonce, mac = value.split(':')
            now = self.clock()
            if scheme != 'AIRI' or node not in (self.config.peer_id, self.config.node_id):
                return False
            if abs(now-int(ts)) > self.config.skew_seconds or len(nonce) != 32:
                return False
            int(nonce, 16)
            if not hmac.compare_digest(mac, signature(self.secret, method, path, ts, nonce, body)):
                return False
        except (ValueError, AttributeError):
            return False
        with self.lock:
            self.nonces = {k:v for k,v in self.nonces.items() if v > now}
            if (node, nonce) in self.nonces:
                return False
            window = self.windows[(node, 'POST' if method == 'POST' else 'READ')]
            while window and window[0] <= now-60:
                window.popleft()
            limit = self.config.post_limit if method == 'POST' else self.config.read_limit
            if len(window) >= limit:
                return False
            window.append(now)
            self.nonces[(node, nonce)] = now+self.config.nonce_seconds
            return True
