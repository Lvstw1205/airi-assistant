"""Private, local-first voice identity service. No reference audio leaves this Mac."""
import hashlib
import speech_text
import json
import os
from pathlib import Path
import re
import secrets
import select
import subprocess
import threading
import time

MODEL_DIR = 'qwen3-tts-0.6b-4bit'
TEST_PHRASES = {
    'en': 'Hey User, I’m here. What are we working on today?',
    'ko': '팀, 나 여기 있어. 오늘은 뭐부터 할까?',
    'fr': 'Salut User, je suis là. On commence par quoi aujourd’hui ?',
    'ja': 'ティム、ここにいるよ。今日は何から始めようか？',
    'mixed': '오늘 Spotify playlist는 pretty good인데?',
}
LANGUAGES = {'en':'English','ko':'Korean','fr':'French','ja':'Japanese','auto':'Auto'}


def language(text):
    if re.search(r'[\u3040-\u30ff]', text): return 'ja'
    if re.search(r'[가-힣]', text): return 'ko'
    if re.search(r'[àâçéèêëîïôùûüÿœ]', text, re.I) or re.search(r'\b(bonjour|salut|merci|avec|pour|dans|une|les|des|je|tu|vous|français|on commence)\b', text, re.I): return 'fr'
    return 'en'


class SpeechCancelled(ValueError): pass


class VoiceService:
    def __init__(self, app):
        self.app=app
        self.lock=threading.Lock()
        self.process_lock=threading.Lock()
        self.process=None
        self.active=False
        self.epoch=0
        self.last={}
        self.fail_until=0

    def prewarm(self):
        """Load the selected voice before the first spoken request, without playback."""
        if self.app.settings().get('tts_engine')=='qwen3_reference' and self.ready():
            with self.process_lock:self._worker()

    def ready(self):
        root=self.app.ROOT
        return ((root/'.runtime/voice-venv/bin/python').exists()
                and (root/'.runtime/models'/MODEL_DIR/'model.safetensors').exists()
                and self.reference().is_file())

    def profile(self):
        path=self.app.ROOT/'config/voice-reference.json'
        if path.exists():
            return json.loads(path.read_text())
        return {'profile':'AIRI canonical reference','reference':'AIRI_voice_reference_final.wav',
                'reference_note':'User-confirmed singing reference; conversational timbre remains experimental.'}

    def reference(self):
        base=(self.app.DATA/'voice/reference').resolve()
        reference=(base/self.profile()['reference']).resolve()
        reference.relative_to(base)  # A profile cannot read files outside private voice storage.
        return reference

    def status(self):
        reference=self.reference()
        return {'profile':self.profile()['profile'],'reference_present':reference.exists(),
                'preferred':'qwen3_reference','ready':self.ready(),
                'selected':self.app.settings().get('tts_engine','supertonic'),
                'languages':list(LANGUAGES)[:-1], 'last':dict(self.last),
                'quality':'experimental_reference',
                'reference_note':self.profile()['reference_note'],
                'streaming':'pcm_chunks','alignment':'audio_envelope',
                'cloud_uploads':False, 'tests':TEST_PHRASES}

    def cancel(self, force=False):
        with self.process_lock:
            self.epoch+=1
            if self.active or force:
                process=self.process
                self.process=None
                if process and process.poll() is None: process.terminate()

    def _worker(self):
        if self.process is None or self.process.poll() is not None:
            log=self.app.DATA/'logs/voice-reference-worker.log'
            log.parent.mkdir(parents=True,exist_ok=True)
            with open(log,'ab') as errors:
                os.chmod(log,0o600)
                self.process=subprocess.Popen([
                    str(self.app.ROOT/'.runtime/voice-venv/bin/python'),
                    str(self.app.ROOT/'scripts/voice-reference-worker.py'),
                    '--model',str(self.app.ROOT/'.runtime/models'/MODEL_DIR),
                    '--reference',str(self.reference()),
                ],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,bufsize=0,
                    env=dict(os.environ,HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false'))
        return self.process

    def synthesize(self, text, legacy, engine=None, on_chunk=None):
        text=speech_text.clean(text)
        if not re.search(r'[가-힣A-Za-z0-9\u3040-\u30ff\u4e00-\u9fff]',text):raise ValueError('읽을 문장이 없습니다.')
        selected=engine or self.app.settings().get('tts_engine','supertonic')
        epoch=self.epoch
        if selected!='qwen3_reference':
            audio=legacy(text,selected)
            self.last={'backend':selected,'canonical_voice':False,'fallback':False}
            return audio
        emitted=False
        process=None
        with self.lock:
            if epoch!=self.epoch: raise SpeechCancelled('음성 생성이 취소되었습니다.')
            try:
                if not self.ready(): raise ValueError('참조 음성 모델 또는 프로필이 설치되지 않았습니다.')
                if time.monotonic()<self.fail_until: raise ValueError('참조 음성 모델 재시도 대기 중')
                folder=self.app.DATA/'speech-queue';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
                audio=folder/(secrets.token_hex(16)+'.wav')
                for old in folder.glob('*.wav'):
                    if old.stat().st_mtime<time.time()-3600:old.unlink(missing_ok=True)
                with self.process_lock:
                    if epoch!=self.epoch: raise SpeechCancelled('음성 생성이 취소되었습니다.')
                    process=self._worker()
                    self.active=True
                request={'text':text,'path':str(audio),'language':language(text),'stream_events':bool(on_chunk)}
                process.stdin.write((json.dumps(request)+'\n').encode());process.stdin.flush()
                last_progress=time.monotonic()
                pending=b''
                while True:
                    while b'\n' not in pending:
                        while not select.select([process.stdout],[],[],.1)[0]:
                            if epoch!=self.epoch: raise SpeechCancelled('음성 생성이 취소되었습니다.')
                            if time.monotonic()-last_progress>90: raise TimeoutError('참조 음성 생성 시간 초과')
                        chunk=os.read(process.stdout.fileno(),65536)
                        if not chunk:raise ValueError('참조 음성 워커가 종료되었습니다.')
                        pending+=chunk
                        last_progress=time.monotonic()
                    line,pending=pending.split(b'\n',1)
                    if epoch!=self.epoch: raise SpeechCancelled('음성 생성이 취소되었습니다.')
                    if not line: raise ValueError('참조 음성 워커가 종료되었습니다.')
                    result=json.loads(line)
                    if result.get('error'):raise ValueError(result['error'])
                    if result.get('type')=='audio':
                        emitted=True
                        on_chunk(result)
                    else:break
                if not audio.is_file(): raise ValueError('생성 음성 파일이 없습니다.')
                audio.chmod(0o600)
                self.last={'backend':'qwen3_reference','canonical_voice':True,'fallback':False,**result}
                self.app.event('voice','Qwen3 reference · '+request['language']+' · '+str(result.get('seconds'))+'s')
                return audio
            except (BrokenPipeError,ConnectionResetError):
                # Discard this request's unread worker output before another
                # sentence acquires the lock. Never cancel an unrelated request.
                with self.process_lock:
                    if self.process is process:
                        if process.poll() is None:process.terminate()
                        self.process=None
                raise
            except SpeechCancelled: raise
            except Exception as error:
                if epoch!=self.epoch:raise SpeechCancelled('음성 생성이 취소되었습니다.')
                with self.process_lock:
                    if self.process and self.process.poll() is None:self.process.terminate()
                    self.process=None
                # A request arriving during cooldown must not extend it forever.
                if time.monotonic()>=self.fail_until:self.fail_until=time.monotonic()+60
                reason=str(error)[:180]
                self.last={'backend':'text_only','canonical_voice':False,'fallback':False,'reason':reason}
                self.app.event('voice','Reference voice unavailable; no speaker replacement · '+reason)
                raise ValueError('아이리 목소리를 만들지 못했어. 다른 목소리로 바꾸지 않고 텍스트를 남겼어.') from error

            finally:
                with self.process_lock:self.active=False
