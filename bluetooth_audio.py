"""Enumerate connected Bluetooth audio outputs and switch macOS default output.
No pairing, shell interpolation, microphone changes, or remote Spotify transfer.
"""
import ctypes as C
import subprocess

def four(s):return int.from_bytes(s.encode('ascii'),'big')
class Address(C.Structure):
 _fields_=[('selector',C.c_uint32),('scope',C.c_uint32),('element',C.c_uint32)]

def libraries():
 ca=C.CDLL('/System/Library/Frameworks/CoreAudio.framework/CoreAudio')
 cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
 for name in ('AudioObjectGetPropertyData','AudioObjectSetPropertyData'):
  f=getattr(ca,name);f.restype=C.c_int32
  f.argtypes=[C.c_uint32,C.POINTER(Address),C.c_uint32,C.c_void_p,C.POINTER(C.c_uint32) if 'Get' in name else C.c_uint32,C.c_void_p]
 ca.AudioObjectGetPropertyDataSize.argtypes=[C.c_uint32,C.POINTER(Address),C.c_uint32,C.c_void_p,C.POINTER(C.c_uint32)];ca.AudioObjectGetPropertyDataSize.restype=C.c_int32
 cf.CFStringGetCString.argtypes=[C.c_void_p,C.c_void_p,C.c_long,C.c_uint32];cf.CFStringGetCString.restype=C.c_bool
 cf.CFRelease.argtypes=[C.c_void_p]
 return ca,cf

def read(ca,obj,selector,scope='glob'):
 a=Address(four(selector),four(scope),0);size=C.c_uint32()
 if ca.AudioObjectGetPropertyDataSize(obj,C.byref(a),0,None,C.byref(size)):raise ValueError('오디오 기기 정보를 읽지 못했어.')
 data=C.create_string_buffer(size.value)
 if ca.AudioObjectGetPropertyData(obj,C.byref(a),0,None,C.byref(size),data):raise ValueError('오디오 기기가 연결 해제됐어. 새로고침해 줘.')
 return data.raw[:size.value]

def integer(ca,obj,selector):return int.from_bytes(read(ca,obj,selector)[:4],'little')
def string(ca,cf,obj,selector):
 value=C.c_void_p(int.from_bytes(read(ca,obj,selector),'little'));buf=C.create_string_buffer(4096)
 try:return buf.value.decode('utf-8') if cf.CFStringGetCString(value,buf,len(buf),0x08000100) else ''
 finally:
  if value:cf.CFRelease(value)

def status():
 try:
  ca,cf=libraries();active=integer(ca,1,'dOut');raw=read(ca,1,'dev#');devices=[];current=None
  for offset in range(0,len(raw),4):
   obj=int.from_bytes(raw[offset:offset+4],'little')
   try:
    if not read(ca,obj,'stm#','outp') or not integer(ca,obj,'livn'):continue
    name=string(ca,cf,obj,'lnam');transport=integer(ca,obj,'tran');uid=string(ca,cf,obj,'uid ')
    kind='bluetooth' if transport in (four('blue'),four('blea')) else 'builtin' if transport==four('bltn') else 'other'
    row={'id':uid,'name':name,'type':kind,'active':obj==active}
    if obj==active:current=row
    if kind in ('bluetooth','builtin'):devices.append(row)
   except ValueError:continue
  return {'available':True,'devices':devices,'current':current,'error':None}
 except Exception:return {'available':False,'devices':[],'current':None,'error':'Mac 오디오 출력을 확인하지 못했어.'}

def select(uid):
 if not isinstance(uid,str) or not uid or len(uid)>1024:raise ValueError('출력 기기를 선택해 줘.')
 snapshot=status()
 if not any(x['id']==uid for x in snapshot['devices']):raise ValueError('연결된 블루투스 기기 또는 내장 스피커만 선택할 수 있어. 먼저 Mac에서 연결해 줘.')
 ca,cf=libraries();raw=read(ca,1,'dev#')
 for offset in range(0,len(raw),4):
  obj=int.from_bytes(raw[offset:offset+4],'little')
  if string(ca,cf,obj,'uid ')!=uid:continue
  if integer(ca,obj,'tran') not in (four('blue'),four('blea'),four('bltn')) or not read(ca,obj,'stm#','outp') or not integer(ca,obj,'livn'):break
  a=Address(four('dOut'),four('glob'),0);value=C.c_uint32(obj)
  if ca.AudioObjectSetPropertyData(1,C.byref(a),0,None,C.sizeof(value),C.byref(value)):raise ValueError('Mac이 출력 변경을 거부했어. 사운드 설정에서 연결을 확인해 줘.')
  result=status()
  if not result.get('current') or result['current']['id']!=uid:raise ValueError('출력 전환을 확인하지 못했어. 새로고침해 줘.')
  return result
 raise ValueError('기기가 연결 해제됐어. 새로고침해 줘.')

def open_settings():
 subprocess.run(['/usr/bin/open','x-apple.systempreferences:com.apple.BluetoothSettings'],check=True,timeout=5)
