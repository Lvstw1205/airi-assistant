"""Local, self-contained VRM assets; no remote textures or executable content."""
import json
import os
from pathlib import Path
import struct
from urllib.parse import unquote

MAX_BYTES=40*1024*1024

def validate(data):
    if len(data)<20 or len(data)>MAX_BYTES:raise ValueError('40MB 이하의 VRM 파일을 선택하세요.')
    magic,version,total=struct.unpack_from('<III',data)
    if magic!=0x46546c67 or version!=2 or total!=len(data):raise ValueError('유효한 VRM/GLB 파일이 아닙니다.')
    size,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4e4f534a or size>len(data)-20:raise ValueError('VRM 메타데이터가 올바르지 않습니다.')
    try:doc=json.loads(data[20:20+size])
    except (ValueError,UnicodeError):raise ValueError('VRM 메타데이터를 읽지 못했습니다.')
    if not isinstance(doc,dict) or not any(k in doc.get('extensions',{}) for k in ('VRM','VRMC_vrm')):
        raise ValueError('리깅된 VRM 0.x 또는 1.0 모델이 필요합니다.')
    for item in doc.get('buffers',[])+doc.get('images',[]):
        if not isinstance(item,dict):raise ValueError('VRM 리소스 형식이 올바르지 않습니다.')
        uri=item.get('uri')
        if uri and (not isinstance(uri,str) or not uri.startswith('data:')):raise ValueError('외부 파일 없이 텍스처가 포함된 VRM을 선택하세요.')
    if len(doc.get('nodes',[]))>1000 or len(doc.get('meshes',[]))>150:raise ValueError('이 Mac에서 사용하기에 모델이 너무 복잡합니다.')
    return doc

def status(app):
    exists=(app.DATA/'avatar/current.vrm').is_file()
    mode=app.settings().get('avatar_mode','body')
    # Previous default was an empty waiting screen; show the bundled character.
    if mode=='placeholder':mode='body'
    if mode=='vrm' and not exists:mode='body'
    return {'available':exists,'mode':mode,
            'name':app.settings().get('avatar_name','VRM 캐릭터') if exists else ''}

def upload(app,handler):
    try:
        size=int(handler.headers.get('Content-Length','0'))
        if not 20<=size<=MAX_BYTES:raise ValueError('40MB 이하의 VRM 파일을 선택하세요.')
        data=handler.rfile.read(size);validate(data)
        name=Path(unquote(handler.headers.get('X-AIRI-Filename','character.vrm'))).name[:150]
        folder=app.DATA/'avatar';folder.mkdir(exist_ok=True)
        temp=folder/'current.vrm.tmp';temp.write_bytes(data);os.replace(temp,folder/'current.vrm')
        with app.db() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('avatar_mode',json.dumps('vrm')))
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('avatar_name',json.dumps(name)))
        return handler.send_json(status(app))
    except (ValueError,TypeError,KeyError,struct.error) as error:return handler.send_json({'error':str(error)},400)
