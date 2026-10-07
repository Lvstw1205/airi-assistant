"""Paired, TLS-pinned inference workers. No file, shell or task-execution API."""
import base64
import datetime as dt
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = 'airi-device-v1:'
MAX_BODY = 8 * 1024 * 1024
NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    '127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128', 'fc00::/7'))


def private_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError('기기의 로컬 IP 주소가 필요합니다.') from None
    if not any(address in network for network in NETWORKS):
        raise ValueError('개인 네트워크의 기기만 연결할 수 있습니다.')
    return str(address)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
            json.dump(value, f)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def decode_pairing(code):
    try:
        if not isinstance(code, str) or not code.startswith(PREFIX) or len(code) > 4096:
            raise ValueError()
        raw = code.strip()[len(PREFIX):]
        item = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        if item.get('v') != 1 or type(item['port']) is not int or not 1024 <= item['port'] <= 65535:
            raise ValueError()
        if not re.fullmatch(r'[0-9a-f]{64}', item['fingerprint']) or not re.fullmatch(r'[0-9a-f]{64}', item['secret']):
            raise ValueError()
        host = private_address(item['host'])
        name = str(item.get('name', '추가 기기')).strip()[:60] or '추가 기기'
        if any(ord(c) < 32 for c in name):
            raise ValueError()
        return {'host': host, 'port': item['port'], 'fingerprint': item['fingerprint'],
                'secret': item['secret'], 'name': name}
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError('연결 코드가 올바르지 않습니다. 추가 기기의 전체 코드를 복사하세요.') from None


def encode_pairing(item):
    return PREFIX + base64.urlsafe_b64encode(json.dumps({'v': 1, **item}, separators=(',', ':')).encode()).decode().rstrip('=')


def signature(secret, method, path, stamp, nonce, payload):
    value = '\n'.join((method, path, stamp, nonce, hashlib.sha256(payload).hexdigest()))
    return hmac.new(bytes.fromhex(secret), value.encode(), hashlib.sha256).hexdigest()


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, item, timeout):
        # The copied pairing code is the trust anchor. Verify its exact certificate
        # before sending an HTTP request or any conversation content.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.fingerprint = item['fingerprint']
        super().__init__(private_address(item['host']), item['port'], timeout=timeout, context=context)

    def connect(self):
        super().connect()
        actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
        if not hmac.compare_digest(actual, self.fingerprint):
            self.close()
            raise ValueError('기기 인증서가 연결 코드와 다릅니다. 새 코드를 확인하세요.')


def remote_open(item, path, body=None, timeout=3):
    if path not in ('/status', '/v1/models', '/v1/chat/completions'):
        raise ValueError('Unsupported worker operation')
    payload = b'' if body is None else json.dumps(body).encode()
    if len(payload) > MAX_BODY:
        raise ValueError('기기에 보낼 요청이 너무 큽니다.')
    method = 'GET' if body is None else 'POST'
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    connection = PinnedConnection(item, timeout)
    try:
        connection.request(method, path, body=None if body is None else payload, headers={
            'Content-Type': 'application/json', 'X-AIRI-Time': stamp, 'X-AIRI-Nonce': nonce,
            'X-AIRI-Signature': signature(item['secret'], method, path, stamp, nonce, payload),
            'Connection': 'close'})
        response = connection.getresponse()
        if response.status != 200:
            response.close()
            raise ValueError('추가 기기의 인증 또는 모델 응답을 확인하지 못했습니다.')
        return response
    except BaseException:
        connection.close()
        raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Ollama redirect refused')


def local_open(base, path, body=None, timeout=3):
    request = urllib.request.Request(base.rstrip('/') + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def local_models(base='http://127.0.0.1:11434'):
    with local_open(base, '/api/tags') as response:
        value = json.loads(response.read(2 * 1024 * 1024))
    return [m for m in value.get('models', []) if isinstance(m, dict) and isinstance(m.get('name'), str)
            and not m.get('remote_host') and not m.get('remote_model') and ':cloud' not in m['name']
            and not m['name'].endswith('-cloud')]


def hardware():
    import psutil
    return {'system': platform.system(), 'processor': platform.machine(),
            'cpu_count': psutil.cpu_count(logical=True) or 1,
            'memory_gb': round(psutil.virtual_memory().total / 1024 ** 3, 1)}


def lan_address():
    import psutil
    candidates = []
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family == socket.AF_INET:
                try:
                    host = private_address(address.address)
                    if not ipaddress.ip_address(host).is_loopback:
                        candidates.append(host)
                except ValueError:
                    pass
    if not candidates:
        raise ValueError('로컬 네트워크 주소를 찾지 못했습니다. --listen 에 기기의 사설 IP를 지정하세요.')
    return candidates[0]


def worker_identity(folder, host, port, name, rotate=False):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path, cert_path = folder / 'tls.key', folder / 'tls.pem'
    if not key_path.exists() or not cert_path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AIRI Inference Worker')])
        today = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(today - dt.timedelta(minutes=5))
                .not_valid_after(today + dt.timedelta(days=3650)).sign(key, hashes.SHA256()))
        for path, content in ((key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption())),
                              (cert_path, cert.public_bytes(serialization.Encoding.PEM))):
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as f:
                f.write(content)
    secret_path = folder / 'identity.json'
    if rotate or not secret_path.exists():
        atomic_json(secret_path, {'secret': secrets.token_hex(32)})
    secret = json.loads(secret_path.read_text())['secret']
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return {'host': private_address(host), 'port': port, 'name': name,
            'secret': secret, 'fingerprint': cert.fingerprint(hashes.SHA256()).hex()}


class WorkerHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass

    def reply(self, code, value):
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def authorized(self, body):
        stamp, nonce = self.headers.get('X-AIRI-Time', ''), self.headers.get('X-AIRI-Nonce', '')
        try:
            if abs(time.time() - int(stamp)) > 90 or not re.fullmatch('[0-9a-f]{32}', nonce):
                return False
        except ValueError:
            return False
        expected = signature(self.server.identity['secret'], self.command, self.path, stamp, nonce, body)
        if not hmac.compare_digest(expected, self.headers.get('X-AIRI-Signature', '')):
            return False
        with self.server.auth_lock:
            self.server.nonces = {k: t for k, t in self.server.nonces.items() if time.time() - t < 180}
            if nonce in self.server.nonces or len(self.server.nonces) >= 5000:
                return False
            self.server.nonces[nonce] = time.time()
        return True

    def do_GET(self):
        if not self.authorized(b''):
            return self.reply(403, {'error': 'Pairing authentication required'})
        if self.path not in ('/status', '/v1/models'):
            return self.reply(404, {'error': 'Unsupported operation'})
        try:
            models = local_models(self.server.ollama)
            if self.path == '/v1/models':
                return self.reply(200, {'data': [{'id': m['name']} for m in models]})
            self.reply(200, {'version': 1, 'hardware': hardware(), 'models': models,
                             'active_jobs': int(self.server.inference_lock.locked())})
        except Exception:
            self.reply(503, {'error': 'Local Ollama unavailable'})

    def do_POST(self):
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError()
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError()
        except (ValueError, OSError):
            return self.reply(400, {'error': 'Invalid body'})
        if not self.authorized(body):
            return self.reply(403, {'error': 'Pairing authentication required'})
        if self.path != '/v1/chat/completions':
            return self.reply(404, {'error': 'Unsupported operation'})
        started = False
        acquired = self.server.inference_lock.acquire(timeout=3)
        if not acquired:
            return self.reply(503, {'error': 'Worker busy'})
        try:
            request = json.loads(body)
            if request.get('model') not in [m['name'] for m in local_models(self.server.ollama)]:
                raise ValueError('Model not installed locally')
            with local_open(self.server.ollama, self.path, request, timeout=120) as response:
                self.send_response(200)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.end_headers()
                started = True
                self.close_connection = True
                total = 0
                while True:
                    chunk = response.read1(16384)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 16 * 1024 * 1024:
                        raise ValueError('Response too large')
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception:
            if not started:
                self.reply(502, {'error': 'Inference unavailable'})
            self.close_connection = True
        finally:
            self.server.inference_lock.release()


def make_worker(folder, host, port, name='추가 기기', rotate=False, ollama='http://127.0.0.1:11434'):
    host = private_address(host)
    if ipaddress.ip_address(host).version == 6:
        class WorkerServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6
    else:
        WorkerServer = ThreadingHTTPServer
    server = WorkerServer((host, port), WorkerHandler)
    server.daemon_threads = True
    server.identity = worker_identity(folder, host, server.server_port, name, rotate)
    server.ollama = ollama
    server.auth_lock, server.inference_lock = threading.Lock(), threading.Lock()
    server.nonces = {}
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(Path(folder) / 'tls.pem'), str(Path(folder) / 'tls.key'))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def run_worker(folder, host=None, port=8770, name='추가 기기', rotate=False):
    server = make_worker(folder, host or lan_address(), port, name, rotate)
    print('AIRI 추가 기기 준비 완료 · Ollama를 이 기기에서 실행해 두세요.', flush=True)
    print('메인 화면 → Settings → 연결 → 기기 추가에 아래 코드를 붙여넣으세요.', flush=True)
    print('연결 코드는 비밀번호처럼 보관하세요. 공개 저장소나 채팅에 올리지 마세요.', flush=True)
    print(encode_pairing(server.identity), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
