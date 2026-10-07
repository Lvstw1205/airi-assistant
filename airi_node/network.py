import ipaddress
import json
import socket
import subprocess
import threading
import time
import urllib.request
from .auth import header


def interface(address):
    try:
        result = subprocess.run(['/sbin/route', '-n', 'get', address], capture_output=True, text=True, timeout=2)
        return next(line.split(':', 1)[1].strip() for line in result.stdout.splitlines() if line.strip().startswith('interface:'))
    except (OSError, subprocess.SubprocessError, StopIteration):
        return 'unknown'


class Peer:
    def __init__(self, config, secret, emit=lambda *a: None):
        self.config, self.secret, self.emit = config, secret, emit
        self.state, self.misses, self.latency_ms = 'CHECKING', 0, None
        self.address, self.link, self.last_ok = None, None, None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.extra = set()
        self.zeroconf = self.browser = self.info = None
        self.discovery_status = 'disabled'
        self.last_error = None
        self.attempts = []

    def observe(self, ok, status='OK', address=None, latency_ms=None, now=None):
        with self.lock:
            before = self.state
            if ok:
                self.misses = 0
                self.last_ok = time.time() if now is None else now
                self.state = 'DEGRADED' if status != 'OK' else 'ONLINE'
                self.address, self.latency_ms = address, latency_ms
            else:
                self.misses += 1
                self.state = 'OFFLINE' if self.misses >= 3 else 'DEGRADED' if self.misses >= 2 else self.state
            if before != self.state:
                self.emit('NODE_'+self.state, {'peer': self.config.peer_id, 'missed': self.misses})

    def snapshot(self):
        with self.lock:
            return {'node_id':self.config.peer_id, 'state':self.state, 'missed':self.misses,
                    'address':self.address, 'interface':self.link, 'latency_ms':self.latency_ms,
                    'last_ok':self.last_ok, 'discovery':self.discovery_status, 'last_error':self.last_error,
                    'attempts':self.attempts}

    def start_discovery(self):
        if not self.config.discovery_enabled:
            return
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo
            self.zeroconf = Zeroconf(interfaces=self.config.bind)
            addresses = [socket.inet_aton(x) for x in self.config.bind if not ipaddress.ip_address(x).is_loopback]
            if addresses:
                self.info = ServiceInfo('_airi._tcp.local.', self.config.node_id+'._airi._tcp.local.',
                                        addresses=addresses, port=self.config.port,
                                        properties={'node_id':self.config.node_id, 'schema_version':'1'})
                self.zeroconf.register_service(self.info)
            peer = self
            class Listener:
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info and info.properties.get(b'node_id', b'').decode() == peer.config.peer_id:
                        for value in info.parsed_addresses():
                            ip = ipaddress.ip_address(value)
                            if ip.version == 4 and (ip.is_private or ip.is_link_local) and not ip.is_unspecified:
                                peer.extra.add(value)
                update_service = add_service
                def remove_service(self, zc, type_, name):
                    pass
            self.browser = ServiceBrowser(self.zeroconf, '_airi._tcp.local.', Listener())
            self.discovery_status = 'bonjour+static'
        except Exception as error:
            self.discovery_status = 'static-only:'+type(error).__name__

    def run(self):
        self.start_discovery()
        candidates, refreshed = [], 0
        failures = 0
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not self.stop.is_set():
            started = time.monotonic()
            if started-refreshed >= self.config.network_refresh_seconds or not candidates:
                addresses = list(dict.fromkeys(self.config.peer_addresses+sorted(self.extra)))
                candidates = sorted([(a, interface(a),self.config.port) for a in addresses], key=lambda v:v[1] != 'bridge0')
                if self.config.peer_loopback_port:
                    candidates.append(('127.0.0.1','Thunderbolt SSH relay',self.config.peer_loopback_port))
                refreshed = started
            ok = False
            self.attempts = []
            for address, link, port in candidates:
                before = time.monotonic()
                try:
                    req = urllib.request.Request(f'http://{address}:{port}/health', headers={
                        'Authorization':header(self.secret, self.config.node_id, 'GET', '/health')})
                    with opener.open(req, timeout=self.config.request_timeout) as response:
                        data = json.load(response)
                    if data.get('node_id') != self.config.peer_id or data.get('schema_version') != 1:
                        raise ValueError('Peer identity mismatch')
                    if self.link != link:
                        self.emit('NODE_LINK_CHANGED', {'interface':link})
                    self.link = link
                    self.last_error = None
                    self.observe(True, data['status'], address, round((time.monotonic()-before)*1000, 1))
                    ok = True
                    failures = 0
                    break
                except Exception as error:
                    self.last_error = type(error).__name__+': '+str(error)[:160]
                    self.attempts.append({'address':address,'interface':link,'error':self.last_error})
                    continue
            if not ok:
                self.observe(False)
                failures += 1
            # Initial missed-heartbeat detection always stays within 15 seconds.
            delay = self.config.heartbeat_seconds
            if self.state == 'OFFLINE':
                delay = self.config.reconnect_seconds[min(max(0, failures-3),len(self.config.reconnect_seconds)-1)]
            self.stop.wait(max(.05, delay-(time.monotonic()-started)))

    def close(self):
        self.stop.set()
        if self.zeroconf:
            if self.info:
                self.zeroconf.unregister_service(self.info)
            self.zeroconf.close()
