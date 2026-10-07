"""Two explicit cameras. Legacy PTZ/presence always retain the Tapo service (camera 2)."""
import json, re, subprocess, threading, time
from pathlib import Path
import camera_bridge

USB_NAME = 'AIRI Camera 1'
USB_DEFAULTS = {'enabled': True, 'name': '카메라 1 · PS5 HD Camera',
                'device_name': USB_NAME, 'vision_model': 'gemma4:26b', 'timeout': 15, 'retries': 0}

def camera_id(value):
    if type(value) is not int or value not in (1, 2):
        raise camera_bridge.CameraError('카메라는 1 또는 2를 선택해 줘.')
    return value

def explicit_id(query):
    match = re.search(r'(?:camera|카메라)\s*([12])(?:번)?|([12])\s*번\s*(?:카메라|캠)', query, re.I)
    if match: return int(match.group(1) or match.group(2))
    if re.search(r'PS5|플레이스테이션', query, re.I): return 1
    if re.search(r'홈캠|tapo|home\s*cam', query, re.I): return 2
    return None

def selected_id(query, tool=None):
    chosen = explicit_id(query)
    if chosen: return chosen
    if tool in ('camera_check_person', 'camera_compare_previous') or re.search(r'방에|거실|출입문|room|누가.*왔', query, re.I): return 2
    return 1

def motion_request(query):
    if explicit_id(query) == 1 and re.search(r'돌려|회전|이동|움직|pan|tilt|rotate|turn.*(?:left|right)', query, re.I):
        return {'text': '카메라 1은 고정형 PS5 카메라라 모터로 돌릴 수 없어. 회전과 손 따라가기는 카메라 2 홈캠에서 할 수 있어.'}
    return None

class USBCamera(camera_bridge.CameraService):
    transport = 'USB'
    def __init__(self, app):
        super().__init__(app)
        self.path = app.DATA / 'camera' / 'usb-settings.json'
        self._device_cache = (0, [])

    def config(self):
        with self.lock:
            try:
                raw = json.loads(self.path.read_text()) if self.path.exists() else {}
                c = {**USB_DEFAULTS, **raw}
                if set(c) != set(USB_DEFAULTS) or type(c['enabled']) is not bool: raise ValueError()
                # Bind to the named PS5 camera; never fall back to another camera or a screen.
                if c['device_name'] != USB_NAME: raise ValueError()
                if not isinstance(c['name'], str) or not 1 <= len(c['name']) <= 80: raise ValueError()
                if not isinstance(c['vision_model'], str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,120}', c['vision_model']): raise ValueError()
                if re.search(r'cloud|openai|freellm', c['vision_model'], re.I): raise ValueError()
                if type(c['timeout']) is not int or not 5 <= c['timeout'] <= 30 or c['retries'] != 0: raise ValueError()
                return c
            except (ValueError, OSError, TypeError):
                raise camera_bridge.CameraError('카메라 1 설정을 읽지 못했어.') from None

    def devices(self):
        with self.lock:
            if time.monotonic() - self._device_cache[0] < 5: return self._device_cache[1]
        try:
            p = subprocess.run([self.ffmpeg(), '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5)
            text = p.stderr.decode('utf-8', errors='replace').split('AVFoundation video devices:')[-1].split('AVFoundation audio devices:')[0]
            names = re.findall(r'\[\d+\]\s+([^\r\n]+)', text)
        except (OSError, subprocess.SubprocessError): names = []
        with self.lock: self._device_cache = (time.monotonic(), names)
        return names

    def status(self):
        c = self.config()
        try: self.ffmpeg(); available = True
        except camera_bridge.CameraError: available = False
        return {**c, 'id': 1, 'kind': 'usb', 'connected': self.devices().count(USB_NAME) == 1,
                'ffmpeg_available': available, 'active': self.active, 'last_capture': self.last,
                'has_previous_observation': self.previous is not None, 'ptz': False,
                'ocr_available': (Path(__file__).parent / '.runtime/camera/camera-ocr').is_file(),
                'retention': '요청한 사진은 메모리에서만 처리. 상품 검색에는 확인한 제품명/바코드만 전송.'}

    def save(self, values):
        if set(values) - {'enabled', 'vision_model', 'timeout'}: raise camera_bridge.CameraError('지원하지 않는 카메라 1 설정이야.')
        with self.lock:
            old = self.config(); new = {**old, **values}
            # Validate without committing malformed settings.
            if type(new['enabled']) is not bool: raise camera_bridge.CameraError('사용 여부를 확인해 줘.')
            model = new['vision_model']
            if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,120}', model) or re.search(r'cloud|openai|freellm', model, re.I):
                raise camera_bridge.CameraError('카메라 1에는 설치된 로컬 영상 모델만 사용할 수 있어.')
            if type(new['timeout']) is not int or not 5 <= new['timeout'] <= 30: raise camera_bridge.CameraError('촬영 제한은 5~30초야.')
            camera_bridge.atomic_json(self.path, new)
            self.generation += 1; self.previous = None; self.last = None; self._stop()
        import usb_camera_preview
        usb_camera_preview.service(self.app).stop()
        return self.status()

    def _capture_command(self, c):
        return [self.ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation',
                '-framerate', '30', '-video_size', '1920x1080', '-pixel_format', 'uyvy422',
                '-i', USB_NAME + ':none', '-vf', r'select=gte(n\,45)', '-frames:v', '1', '-an',
                '-fps_mode', 'passthrough', '-threads', '1', '-c:v', 'mjpeg', '-q:v', '2', '-f', 'image2pipe', 'pipe:1']

    def _capture(self, c, generation):
        if not c['enabled']: raise camera_bridge.CameraError('카메라 1이 꺼져 있어. 설정에서 켜 줘.')
        if self.devices().count(USB_NAME) != 1:
            raise camera_bridge.CameraError('카메라 1이 연결되지 않았거나 같은 이름이 여러 개야. PS5 USB 연결과 펌웨어 로더를 확인해 줘.')
        self._check(generation)
        import usb_camera_preview
        try: frame=usb_camera_preview.service(self.app).get()
        except ValueError as error: raise camera_bridge.CameraError(str(error)) from None
        self._check(generation)
        return frame

    def local_evidence(self, frame):
        binary = Path(__file__).parent / '.runtime/camera/camera-ocr'
        if not binary.is_file(): return {'available': False}
        try:
            p = subprocess.run([str(binary)], input=frame, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
            if p.returncode or len(p.stdout) > 60000: raise ValueError()
            return {**json.loads(p.stdout), 'available': True}
        except (ValueError, OSError, subprocess.SubprocessError): return {'available': False}

_USB = {}; _LOCK = threading.Lock()
def service(app, number=1):
    number = camera_id(number)
    if number == 2: return camera_bridge.service(app)
    with _LOCK:
        key = str(app.DATA.resolve())
        if key not in _USB: _USB[key] = USBCamera(app)
        return _USB[key]

def status(app):
    home = service(app, 2).status()
    # Never return credentials or LAN address in the camera selector.
    home = {k: home[k] for k in ('enabled', 'active', 'last_capture', 'vision_model')}
    home.update(id=2, name='카메라 2 · Tapo 홈캠', kind='rtsp', ptz=True)
    return {'cameras': [service(app, 1).status(), home], 'product_camera': 1, 'tracking_camera': 2}

def capability_context(app):
    return ('AIRI has two explicit cameras: camera 1 is the fixed PS5 HD Camera for objects, labels and product search; '
            'camera 2 is the existing Tapo home camera with ONVIF movement and hand tracking. '
            'Generic product requests use camera 1. Explicit camera numbers override that choice. Never substitute camera 2 when camera 1 fails. '
            'Use fresh camera results; readable label evidence is not a guarantee of exact product identity. '
            'Product shopping searches use only product identity text, not images or room OCR. Do not invent live prices.')
