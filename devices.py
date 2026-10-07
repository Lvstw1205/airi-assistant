"""Single-machine first; opt-in paired workers and automatic inference routing."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import uuid
import device_transport as transport

_registries = {}
_registry_lock = threading.Lock()


class Registry:
    def __init__(self, data, local_base='http://127.0.0.1:11434/v1'):
        self.path = Path(data) / 'devices' / 'registry.json'
        self.local_base = local_base.rstrip('/')
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.observations = {}
        self.checked_at = 0
        self.failed_until = {}
        self.current = {}
        self.stop = threading.Event()
        self.thread = None

    def load(self):
        if not self.path.exists():
            return []
        value = json.loads(self.path.read_text())
        if not isinstance(value, list) or len(value) > 16:
            raise ValueError('기기 설정을 읽지 못했습니다. 등록 파일을 확인하세요.')
        return value

    def probe(self, item):
        start = time.monotonic()
        result = {'id': item['id'], 'name': item['name'], 'online': False, 'models': [],
                  'enabled': item.get('enabled', True), 'local': item['id'] == 'local', 'checked_at': time.time()}
        if not result['enabled']:
            result['state'] = 'disabled'
            return result
        try:
            if item['id'] == 'local':
                value = {'models': transport.local_models(self.local_base.removesuffix('/v1')),
                         'hardware': transport.hardware(), 'active_jobs': 0}
            else:
                with transport.remote_open(item, '/status', timeout=3) as response:
                    value = json.loads(response.read(2 * 1024 * 1024))
                if value.get('version') != 1:
                    raise ValueError('Unsupported worker version')
            models = [m for m in value['models'] if isinstance(m, dict) and isinstance(m.get('name'), str)]
            hw = value.get('hardware', {})
            result.update(online=True, state='ready' if models else 'no_models', models=models,
                          hardware={'memory_gb': max(0, min(8192, float(hw.get('memory_gb', 0)))),
                                    'cpu_count': max(1, min(1024, int(hw.get('cpu_count', 1)))),
                                    'system': str(hw.get('system', ''))[:30]},
                          active_jobs=max(0, int(value.get('active_jobs', 0))),
                          latency_ms=round((time.monotonic() - start) * 1000, 1))
        except Exception:
            result.update(state='offline', error='Ollama 또는 기기 연결을 확인하세요.')
        return result

    def refresh(self, force=False):
        with self.refresh_lock:
            if not force and time.time() - self.checked_at < 15:
                return
            with self.lock:
                items = [{'id': 'local', 'name': '이 컴퓨터', 'enabled': True}] + self.load()
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(self.probe, items))
            with self.lock:
                # Do not let a concurrent refresh resurrect a removed connection.
                valid = {'local'} | {d['id'] for d in self.load()}
                self.observations = {d['id']: d for d in results if d['id'] in valid}
                self.checked_at = time.time()

    def candidates(self, model):
        self.refresh()
        with self.lock:
            records = []
            for item in self.observations.values():
                if not item['online'] or not item['enabled'] or self.failed_until.get(item['id'], 0) > time.time():
                    continue
                match = next((m for m in item['models'] if m['name'] == model), None)
                if not match:
                    continue
                hw = item.get('hardware', {})
                # Capacity/availability heuristic, not a claimed inference benchmark.
                score = hw.get('memory_gb', 0) + hw.get('cpu_count', 1) * 0.5
                score /= 1 + item.get('active_jobs', 0) * 2 + item.get('latency_ms', 0) / 1000
                records.append((score, item, match.get('digest')))
            records.sort(key=lambda row: (-row[0], row[1]['id'] != 'local', row[1]['id']))
            if not records:
                self.current.pop(model, None)
                return []
            # Prefer the coordinator's installed digest as the model identity.
            local = next((r for r in records if r[1]['id'] == 'local'), None)
            digest = local[2] if local else records[0][2]
            records = [r for r in records if r[2] == digest] if digest else records[:1]
            previous = next((r for r in records if r[1]['id'] == self.current.get(model)), None)
            if previous and previous[0] >= records[0][0] * 0.8:
                records.remove(previous)
                records.insert(0, previous)
            self.current[model] = records[0][1]['id']
            return [r[1] for r in records]

    def endpoints(self, model):
        candidates = self.candidates(model)
        with self.lock:
            saved = {d['id']: d for d in self.load()}
        endpoints = []
        for item in candidates:
            endpoint = {'base_url': self.local_base, 'health_timeout': 3, 'response_timeout': 120,
                        'device_id': item['id'], 'device_name': item['name'],
                        'installed_models': [m['name'] for m in item['models']], '_registry': self}
            if item['id'] != 'local':
                private = saved.get(item['id'])
                if not private or not private.get('enabled', True):
                    continue
                host = '[' + private['host'] + ']' if ':' in private['host'] else private['host']
                endpoint.update(base_url='https://' + host + ':' + str(private['port']) + '/v1', device=private)
            endpoints.append(endpoint)
        return endpoints

    def failure(self, identifier):
        with self.lock:
            self.failed_until[identifier] = time.time() + 30
            self.current = {k: v for k, v in self.current.items() if v != identifier}

    def status(self, model):
        candidates = self.candidates(model) if model and not model.startswith(('openai:', 'freellmapi:', 'airi:')) else []
        self.refresh()
        with self.lock:
            winner = candidates[0] if candidates else None
            nodes = []
            eligible = {d['id'] for d in candidates}
            for value in self.observations.values():
                item = dict(value)
                item['models'] = [{'name': m['name']} for m in value['models']]
                item['eligible'] = item['id'] in eligible
                item['main'] = bool(winner and winner['id'] == item['id'])
                item['cooldown'] = self.failed_until.get(item['id'], 0) > time.time()
                nodes.append(item)
            return {'mode': 'automatic', 'devices': nodes, 'selected_model': model,
                    'external_model': bool(model and model.startswith(('openai:', 'freellmapi:', 'airi:'))),
                    'main': {'id': winner['id'], 'name': winner['name']} if winner else None,
                    'reason': '설치 모델·가중치, 메모리·CPU, 응답 시간과 사용 상태를 기준으로 자동 선택합니다.',
                    'coordinator': '이 컴퓨터', 'checked_at': self.checked_at}

    def add(self, code, name=''):
        item = transport.decode_pairing(code)
        if name:
            name = str(name).strip()
            if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
                raise ValueError('기기 이름은 1~60자로 입력하세요.')
            item['name'] = name
        item.update(id=uuid.uuid4().hex, enabled=True)
        observation = self.probe(item)
        if not observation['online']:
            raise ValueError('기기를 확인하지 못했습니다. 같은 네트워크, 기기 실행, 연결 코드를 확인하세요.')
        with self.lock:
            saved = self.load()
            old = next((d for d in saved if (d['host'], d['port']) == (item['host'], item['port'])), None)
            if old:
                item['id'] = old['id']
                saved = [d for d in saved if d['id'] != old['id']]
            if len(saved) >= 16:
                raise ValueError('추가 기기는 최대 16대까지 등록할 수 있습니다.')
            saved.append(item)
            transport.atomic_json(self.path, saved)
            observation['id'] = item['id']
            self.observations[item['id']] = observation
            self.failed_until.pop(item['id'], None)
            self.checked_at = 0
        return item['id']

    def change(self, identifier, enabled=None, remove=False):
        if identifier == 'local':
            raise ValueError('이 컴퓨터는 기본 연결입니다.')
        with self.lock:
            saved = self.load()
            target = next((d for d in saved if d['id'] == identifier), None)
            if not target:
                raise ValueError('등록된 기기를 찾지 못했습니다.')
            if remove:
                saved.remove(target)
                self.observations.pop(identifier, None)
            else:
                if type(enabled) is not bool:
                    raise ValueError('기기 사용 여부가 올바르지 않습니다.')
                target['enabled'] = enabled
            transport.atomic_json(self.path, saved)
            self.checked_at = 0
            self.current.clear()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        def monitor():
            while not self.stop.is_set():
                try:
                    self.refresh()
                except (OSError, ValueError):
                    pass
                self.stop.wait(15)
        self.thread = threading.Thread(target=monitor, daemon=True, name='airi-devices')
        self.thread.start()


def registry(data=None, local_base=None):
    data = Path(data or os.environ.get('AIRI_DATA', str(Path(__file__).resolve().parent / 'data')))
    if local_base is None:
        cfg = json.loads((Path(__file__).resolve().parent / 'config/llm.json').read_text())
        local_base = cfg['primary']['base_url']
    key = (str(data.resolve()), local_base)
    with _registry_lock:
        if key not in _registries:
            _registries[key] = Registry(data, local_base)
        return _registries[key]


def routed_endpoints(config, model):
    current = registry(local_base=config['primary']['base_url'])
    # Keep explicit legacy config compatible until users add devices in the UI.
    if not current.load():
        unique = {}
        for endpoint in (config['primary'], config['fallback']):
            unique.setdefault(endpoint['base_url'].rstrip('/'), endpoint)
        return list(unique.values())
    return current.endpoints(model)


def open_endpoint(endpoint, url, body, timeout):
    base = endpoint['base_url'].rstrip('/')
    if not url.startswith(base + '/'):
        raise ValueError('Wrong worker destination')
    path = urlsplit(url).path
    return transport.remote_open(endpoint['device'], path, body, timeout)


def failed(endpoint):
    if endpoint.get('_registry'):
        endpoint['_registry'].failure(endpoint['device_id'])


def available_models(app):
    state = registry(app.DATA).status(app.settings()['model'])
    names = sorted({m['name'] for d in state['devices'] if d['online'] and d['enabled'] for m in d['models']})
    return [{'name': name} for name in names]


def action(app, body):
    current = registry(app.DATA)
    action = body.get('action')
    if action == 'add':
        current.add(body.get('code'), body.get('name', ''))
    elif action == 'remove':
        current.change(body.get('id'), remove=True)
    elif action == 'toggle':
        current.change(body.get('id'), enabled=body.get('enabled'))
    elif action != 'refresh':
        raise ValueError('Unknown device action')
    current.refresh(force=True)
    return current.status(app.settings()['model'])
