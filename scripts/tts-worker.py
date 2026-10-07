"""Keep the local ONNX voice model warm. JSON lines over local process pipes."""
import json,os,re,sys,threading,time
from pathlib import Path
from supertonic import TTS
parent=os.getppid()
def watch_parent():
    while os.getppid()==parent:time.sleep(3)
    os._exit(0)
threading.Thread(target=watch_parent,daemon=True).start()
root=Path(__file__).resolve().parents[1]
tts=TTS(model_dir=root/'.runtime/models/supertonic-3',auto_download=False,intra_op_num_threads=4,inter_op_num_threads=1)
styles={}
for line in sys.stdin:
    try:
        r=json.loads(line);voice=r['voice'];text=r['text'];started=time.monotonic()
        if not re.fullmatch('[FM][1-5]',voice):raise ValueError('invalid voice')
        if voice not in styles:styles[voice]=tts.get_voice_style(voice)
        # Keep one voice style while selecting the phoneme language automatically.
        # Explicit language codes are more reliable for French than the model's
        # fallback token, especially for accents and short utterances.
        if re.search(r'[가-힣]', text): lang='ko'
        elif re.search(r'[àâçéèêëîïôùûüÿœ]', text, re.I) or re.search(r'\b(bonjour|merci|avec|pour|dans|est|une|les|des|je|vous|français)\b', text, re.I): lang='fr'
        else: lang='en'
        wav,_=tts.synthesize(text,voice_style=styles[voice],lang=lang,total_steps=5,speed=float(r['speed']),verbose=False)
        tts.save_audio(wav,r['path'])
        print(json.dumps({'ok':True,'seconds':round(time.monotonic()-started,2)}),flush=True)
    except Exception:
        print(json.dumps({'error':'로컬 신경망 음성을 생성하지 못했습니다.'}),flush=True)
