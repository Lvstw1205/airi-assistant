"""Transcribe PCM WAV locally, no ffmpeg or network needed at runtime."""
import json
from pathlib import Path
import sys
import wave
import re

import numpy as np
import mlx_whisper

def transcribe(filename,language='auto'):
    with wave.open(filename, 'rb') as audio:
        if audio.getframerate() != 16000 or audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getnframes() > 16000 * 301:
            raise ValueError('Expected <=5 minutes, 16kHz mono PCM16 WAV')
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
    if not len(samples) or float(np.sqrt(np.mean(samples*samples))) < 0.002:
        return {'text': ''}
    else:
        model = Path(__file__).resolve().parents[1] / '.runtime/models/whisper-turbo'
        result = mlx_whisper.transcribe(samples, path_or_hf_repo=str(model), language=None if language=='auto' else language, verbose=None, condition_on_previous_text=False, temperature=0, initial_prompt='AIRI, 아이리.', no_speech_threshold=0.5, logprob_threshold=-0.8)
        text=result['text'].strip()
        segments=result.get('segments',[])
        bad_language=result.get('language') not in ('ko','en','fr','ja')
        repeated=bool(re.search(r'(.{3,30}?)\1{2,}',text.replace(' ','')))
        uncertain=not segments or sum(s.get('avg_logprob',-2) for s in segments)/len(segments)<-0.8 or all(s.get('no_speech_prob',0)>0.55 for s in segments)
        if bad_language or repeated or uncertain:text=''
        return {'text':text,'language':result.get('language'),'uncertain':bad_language or repeated or uncertain}

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        import os,threading,time
        parent=os.getppid()
        def watch_parent():
            while os.getppid()==parent:time.sleep(3)
            os._exit(0)
        threading.Thread(target=watch_parent,daemon=True).start()
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if request.get('warmup'):
                    # Exercise the same public API/model cache used by real input.
                    model=Path(__file__).resolve().parents[1]/'.runtime/models/whisper-turbo'
                    mlx_whisper.transcribe(np.zeros(16000,dtype=np.float32),path_or_hf_repo=str(model),language='ko',verbose=None,condition_on_previous_text=False,temperature=0)
                    value={'ready':True}
                else:value=transcribe(request['file'],request.get('language','auto'))
            except Exception:
                value={'error':'로컬 음성 인식에 실패했습니다.'}
            print(json.dumps(value,ensure_ascii=False),flush=True)
    else:
        print(json.dumps(transcribe(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'auto'),ensure_ascii=False))
