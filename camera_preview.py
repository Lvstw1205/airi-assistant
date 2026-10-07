"""Opt-in in-memory preview; one RTSP decoder, idle shutdown, no recording."""
import atexit, os, selectors, subprocess, threading, time
from urllib.parse import quote
import camera_bridge

class Preview:
 def __init__(self, app):
  self.camera=camera_bridge.service(app);self.condition=threading.Condition();self.thread=None;self.cancel=None
  self.last_request=0;self.frame=None;self.stamp=0;self.identity=None
  atexit.register(self.close)
 def close(self):
  self.stop()
  if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=3)
 def stop(self):
  with self.condition:
   if self.cancel:self.cancel.set()
   self.frame=None;self.condition.notify_all()
 def get(self):
  camera=self.camera;c=camera.config()
  if not c['enabled'] or not all(c.get(k) for k in ('host','username','password')):raise ValueError('Camera is disabled or not configured.')
  identity=(c['host'],c['port'],c['stream'],c['username'],c['password'],camera.generation)
  started=time.monotonic()
  with self.condition:
   self.last_request=started
   if self.thread and self.thread.is_alive() and identity!=self.identity:
    self.cancel.set();raise ValueError('Camera settings changed; reconnecting preview.')
   if not self.thread or not self.thread.is_alive():
    self.frame=None;self.identity=identity;self.cancel=threading.Event()
    self.thread=threading.Thread(target=self.read,args=(c,camera.generation,self.cancel),daemon=True);self.thread.start()
   deadline=started+6
   while self.stamp<started or self.frame is None:
    remaining=deadline-time.monotonic()
    if remaining<=0 or self.cancel.is_set():raise ValueError('Live camera preview unavailable; retrying.')
    self.condition.wait(min(.2,remaining))
   camera._check(identity[-1])
   return self.frame
 def read(self,c,generation,cancel):
  process=None
  try:
   host='['+c['host']+']' if ':' in c['host'] else c['host']
   url='rtsp://%s:%s@%s:%d/%s'%(quote(c['username'],safe=''),quote(c['password'],safe=''),host,c['port'],c['stream'])
   process=subprocess.Popen([self.camera.ffmpeg(),'-nostdin','-hide_banner','-loglevel','error','-rtsp_transport','tcp','-timeout','4000000','-fflags','nobuffer','-flags','low_delay','-probesize','32768','-analyzeduration','0','-i',url,'-an','-vf','fps=5,scale=640:-2','-threads','1','-c:v','mjpeg','-q:v','5','-f','image2pipe','pipe:1'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   buffer=bytearray()
   with selectors.DefaultSelector() as selector:
    selector.register(process.stdout,selectors.EVENT_READ)
    while not cancel.is_set() and time.monotonic()-self.last_request<8:
     self.camera._check(generation)
     if not selector.select(.2):
      if process.poll() is not None:break
      continue
     chunk=os.read(process.stdout.fileno(),65536)
     if not chunk:break
     buffer.extend(chunk)
     if len(buffer)>2*1024*1024:raise ValueError('Preview frame too large.')
     while True:
      end=buffer.find(b'\xff\xd9')
      if end<0:break
      image=bytes(buffer[:end+2]);del buffer[:end+2]
      if image.startswith(b'\xff\xd8'):
       with self.condition:self.frame=image;self.stamp=time.monotonic();self.condition.notify_all()
  except Exception:
   pass # Never expose RTSP credentials or decoder stderr.
  finally:
   if process:
    if process.poll() is None:process.kill()
    process.wait();process.stdout.close()
   with self.condition:cancel.set();self.frame=None;self.condition.notify_all()

_SERVICES={};_LOCK=threading.Lock()
def service(app):
 with _LOCK:
  key=str(app.DATA)
  if key not in _SERVICES:_SERVICES[key]=Preview(app)
  return _SERVICES[key]
