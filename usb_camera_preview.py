"""One PS5 decoder; latest JPEG only, shared by automatic and requested observations."""
import atexit, datetime as dt, os, selectors, subprocess, threading, time

class Preview:
    def __init__(self, app):
        import camera_sources
        self.camera=camera_sources.service(app,1)
        self.condition=threading.Condition(); self.thread=None; self.cancel=threading.Event()
        self.frame=None; self.stamp=0; self.last_request=0; self.continuous=False
        atexit.register(self.close)

    def set_continuous(self, enabled):
        with self.condition: self.continuous=bool(enabled)
        if not enabled: self.stop()

    def stop(self):
        with self.condition:
            self.cancel.set(); self.frame=None; self.condition.notify_all()

    def close(self):
        self.stop()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(3)

    def get(self):
        c=self.camera.config()
        if not c['enabled']: raise ValueError('카메라 1 사용이 꺼져 있어.')
        started=time.monotonic()
        with self.condition:
            self.last_request=started
            if self.thread and self.thread.is_alive() and self.cancel.is_set():
                raise ValueError('카메라 1 스트림을 다시 연결 중이야.')
            if not self.thread or not self.thread.is_alive():
                if self.camera.devices().count('AIRI Camera 1')!=1: raise ValueError('PS5 카메라 1 USB 연결을 확인해 줘.')
                self.frame=None; self.cancel=threading.Event()
                self.thread=threading.Thread(target=self.read,args=(self.camera.generation,self.cancel),daemon=True,name='airi-ps5-frames'); self.thread.start()
            deadline=started+12
            while self.frame is None or self.stamp<started:
                remaining=deadline-time.monotonic()
                if remaining<=0 or self.cancel.is_set(): raise ValueError('카메라 1의 새 영상을 받지 못했어.')
                self.condition.wait(min(.3,remaining))
            self.camera.last=dt.datetime.now(dt.timezone.utc).isoformat()
            return self.frame

    def read(self,generation,cancel):
        process=None
        try:
            args=[self.camera.ffmpeg(),'-nostdin','-hide_banner','-loglevel','error','-f','avfoundation',
                  '-framerate','30','-video_size','1920x1080','-pixel_format','uyvy422','-i','AIRI Camera 1:none',
                  '-an','-vf',r'select=gte(n\,45),fps=2','-threads','1','-c:v','mjpeg','-q:v','3','-f','image2pipe','pipe:1']
            process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            buffer=bytearray()
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout,selectors.EVENT_READ)
                while not cancel.is_set() and (self.continuous or time.monotonic()-self.last_request<8):
                    self.camera._check(generation)
                    if not poll.select(.2):
                        if process.poll() is not None: break
                        continue
                    block=os.read(process.stdout.fileno(),65536)
                    if not block: break
                    buffer.extend(block)
                    if len(buffer)>4*1024*1024: raise ValueError('Frame limit')
                    while True:
                        end=buffer.find(b'\xff\xd9')
                        if end<0: break
                        frame=bytes(buffer[:end+2]); del buffer[:end+2]
                        if frame.startswith(b'\xff\xd8'):
                            with self.condition:
                                self.frame=frame; self.stamp=time.monotonic(); self.condition.notify_all()
        except Exception: pass
        finally:
            if process:
                if process.poll() is None: process.kill()
                process.wait(); process.stdout.close()
            with self.condition: cancel.set(); self.frame=None; self.condition.notify_all()

_SERVICES={}; _LOCK=threading.Lock()
def service(app):
    with _LOCK:
        key=str(app.DATA)
        if key not in _SERVICES: _SERVICES[key]=Preview(app)
        return _SERVICES[key]
