"""Warm Qwen3 Base worker: cached speaker embedding, generated speech only."""
import base64,argparse,contextlib,hashlib,json,os,sys,threading,time,wave
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--reference',required=True)
    parser.add_argument('--streaming-interval',type=float,default=1.0)
    args=parser.parse_args();out=sys.stdout
    os.umask(0o077)
    parent=os.getppid()
    def watch():
        while os.getppid()==parent:time.sleep(3)
        os._exit(0)
    threading.Thread(target=watch,daemon=True).start()
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import mlx.core as mx
        from scipy.signal import resample_poly
        from mlx_audio.tts.utils import load_model
        model=load_model(args.model)
        source=Path(args.reference)
        digest=hashlib.sha256(source.read_bytes()+Path(args.model,'config.json').read_bytes()+b'mlx-audio-0.5.3-first12s-v1').hexdigest()
        cache=source.parent/'features';cache.mkdir(mode=0o700,exist_ok=True)
        with wave.open(str(source),'rb') as audio:
            if audio.getsampwidth()!=2:raise ValueError('PCM16 reference required')
            samples=np.frombuffer(audio.readframes(min(audio.getnframes(),audio.getframerate()*12)),dtype='<i2').astype(np.float32)/32768
            samples=samples.reshape(-1,audio.getnchannels()).mean(axis=1)
            samples=resample_poly(samples,24000,audio.getframerate()).astype(np.float32)
        reference=mx.array(samples)
        embedding_path=cache/(digest+'.safetensors')
        if embedding_path.exists():embedding=mx.load(str(embedding_path))['speaker']
        else:
            embedding=model.extract_speaker_embedding(reference);mx.eval(embedding)
            mx.save_safetensors(str(embedding_path),{'speaker':embedding});embedding_path.chmod(0o600)
        # This worker owns one immutable speaker. Reuse its cached conditioning
        # through the installed model's documented embedding method.
        model.extract_speaker_embedding=lambda audio,sr=24000:embedding
    for line in sys.stdin:
        try:
            request=json.loads(line);started=time.monotonic();first=None;chunks=[];generated_tokens=0;token_limit=1800
            with contextlib.redirect_stdout(sys.stderr):
                language={'en':'English','ko':'Korean','fr':'French','ja':'Japanese'}.get(request.get('language'),'Auto')
                for chunk in model.generate(text=request['text'],ref_audio=reference,ref_text=None,lang_code=language,
                                            stream=True,streaming_interval=args.streaming_interval,max_tokens=token_limit,temperature=.4,verbose=False):
                    generated_tokens+=getattr(chunk,'token_count',0)
                    if first is None:first=time.monotonic()-started
                    samples=np.array(chunk.audio,dtype=np.float32).reshape(-1)
                    if not np.isfinite(samples).all():raise ValueError('Invalid audio chunk')
                    chunks.append(samples)
                    if request.get('stream_events'):
                        print(json.dumps({'type':'audio','sample_rate':model.sample_rate,
                            'pcm':base64.b64encode((np.clip(samples,-1,1)*32767).astype('<i2').tobytes()).decode()}),file=out,flush=True)
                if generated_tokens>=token_limit:raise ValueError('Voice generation reached its length limit; remaining text was not spoken')
                if not chunks:raise ValueError('No audio generated')
                pcm=np.clip(np.concatenate(chunks),-1,1)
                if not np.isfinite(pcm).all() or np.sqrt(np.mean(pcm*pcm))<.0001:raise ValueError('Invalid generated audio')
                with wave.open(request['path'],'wb') as wav:
                    wav.setparams((1,2,model.sample_rate,0,'NONE','not compressed'));wav.writeframes((pcm*32767).astype('<i2').tobytes())
                result={'seconds':round(time.monotonic()-started,3),'first_chunk_seconds':round(first,3),
                        'duration':round(len(pcm)/model.sample_rate,3),'peak_memory_gb':round(mx.get_peak_memory()/1e9,3),
                        'conditioning':'speaker_embedding','reference_sha256':digest,'language':request.get('language')}
            print(json.dumps(result),file=out,flush=True)
        except Exception as error:
            print(json.dumps({'error':type(error).__name__+': '+str(error)[:160]}),file=out,flush=True)

if __name__=='__main__':main()
