// One AudioContext owns streamed speech, cancellation and mouth timing.
(()=>{
 const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('airi-voice-output'):null;channel?.addEventListener('message',()=>stop());
 let context,queue=Promise.resolve(),generationQueue=Promise.resolve(),revision=0,current=null;
 const requests=new Set();let previousPlayback=Promise.resolve();
 const emit=(name,detail)=>window.dispatchEvent(new CustomEvent(name,{detail}));
 async function unlock(){
  if(!context||context.state==='closed'){context=new (window.AudioContext||window.webkitAudioContext)();context.addEventListener?.('statechange',()=>{if(current&&['suspended','interrupted'].includes(context.state))context.resume().catch(()=>{});});}
  if(context.state==='running')return;
  let timeout;
  try{await Promise.race([context.resume(),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Safari 음성이 잠겨 있어요. 음성 켜기를 누른 뒤 다시 재생하세요.')),3000);})]);}
  finally{clearTimeout(timeout);}
 }
 window.addEventListener('pageshow',()=>{if(context&&context.state!=='running')unlock().catch(()=>{});});
 for(const event of ['pointerdown','keydown'])window.addEventListener(event,()=>{if(!context||context.state!=='running')unlock().catch(()=>{});},{passive:true});
 function stop(){revision++;for(const request of requests)request.abort();requests.clear();if(current){current.abort.abort();for(const source of current.sources){try{source.stop();}catch{}}}window.airiBrowserSpeech=false;emit('airi-speech-state',{speaking:false,level:0});emit('airi-speech-finished');}
 async function play(text,{test_language,onStart}={}){
  text=String(text).replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\uFE0E\u200D\u20E3]/gu,'').trim();
  if(!/[\p{L}\p{N}]/u.test(text))return {ok:true,skipped:true};
  const version=revision;
  // At most one sentence ahead: generate the next sentence while the current
  // one plays, without concurrent inference or changing the speaker identity.
  const aheadGate=previousPlayback;previousPlayback=queue.catch(()=>{});
  const abort=new AbortController();requests.add(abort);
  const packets=[];let producerDone=false,producerError=null,wake=null;
  const signal=()=>{wake?.();wake=null;};
  generationQueue=generationQueue.catch(()=>{}).then(async()=>{
   await aheadGate;if(version!==revision){producerDone=true;requests.delete(abort);signal();return;}
   try{
    const response=await fetch('/api/voice-stream',{method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify({text,...(test_language?{test_language}:{})}),signal:abort.signal});
    if(!response.ok){const error=await response.json();throw Error(error.error||'음성 연결 실패');}
    const reader=response.body.getReader();
    while(true){const part=await reader.read();if(part.done)break;packets.push(part);signal();}
   }catch(error){producerError=error;}finally{producerDone=true;requests.delete(abort);signal();}
  });
  const reader={async read(){while(!packets.length&&!producerDone)await new Promise(resolve=>{wake=resolve;});if(packets.length)return packets.shift();if(producerError)throw producerError;return {done:true};}};
  const job=queue.catch(()=>{}).then(async()=>{
   if(version!==revision)return {cancelled:true};
   channel?.postMessage('playing');
   await unlock();if(context.state!=='running')throw Error('브라우저에서 한 번 클릭한 뒤 음성을 재생하세요.');
   const id=globalThis.crypto?.randomUUID?.()||('airi-'+Date.now()+'-'+Math.random().toString(16).slice(2));
   const session={abort,sources:new Set(),start:null,end:context.currentTime,segments:[],pending:[],buffered:0,firstChunkAt:null,firstChunkDuration:0,id,created:Date.now()};current=session;
   window.airiBrowserSpeech=true;let frame,done=false,started=false;
   const gain=context.createGain();
   // Gain changes energy only: no pitch shifting or identity replacement.
   const hour=Number(new Intl.DateTimeFormat('en',{hour:'numeric',hourCycle:'h23',timeZone:'UTC'}).format(new Date()));
   const emotion=window.airiCharacterRuntime?.snapshot()?.emotion||'neutral';
   gain.gain.value=hour>=22||hour<7?.72:['sleepy','sad','worried'].includes(emotion)?.8:1;gain.connect(context.destination);
   function tick(){if(version!==revision)return;const now=context.currentTime;
    const segment=session.segments.find(s=>now>=s.start&&now<s.end);let level=0;
    if(segment){const offset=Math.floor((now-segment.start)*segment.rate),n=Math.min(segment.samples.length,offset+Math.ceil(segment.rate*.02));let power=0;for(let i=offset;i<n;i++)power+=segment.samples[i]**2;level=Math.min(1,Math.sqrt(power/Math.max(1,n-offset))*5);}
    if(segment&&!started){started=true;onStart?.();emit('airi-speech-start',{id:session.id});}
    const speaking=started; // Retain speech ownership through buffering; amplitude still closes the mouth.
    emit('airi-speech-state',{speaking,preparing:!started,level,id:session.id,wait_seconds:Math.floor((Date.now()-session.created)/1000),audio_context:context.state,elapsed:session.start===null?0:Math.max(0,now-session.start),duration:session.start===null?0:session.end-session.start});
    document.body.classList.toggle('airi-speaking',speaking);
    if(typeof $==='function'&&$('face-status'))$('face-status').textContent=speaking?'말하고 있어요':'음성 준비 중';
    frame=(window.airiDesktop&&document.hidden)?setTimeout(tick,100):requestAnimationFrame(tick);
   }
   frame=(window.airiDesktop&&document.hidden)?setTimeout(tick,100):requestAnimationFrame(tick);
   function flush(){
    if(!session.pending.length)return;
    const rate=session.pending[0].rate;
    if(session.pending.some(p=>p.rate!==rate))throw Error('음성 샘플 속도가 변경되었습니다. 다시 재생해 주세요.');
    const samples=new Float32Array(session.pending.reduce((n,p)=>n+p.samples.length,0));
    const boundaries=[];let offset=0;
    for(const part of session.pending){if(offset)boundaries.push(offset);samples.set(part.samples,offset);offset+=part.samples.length;}
    // Decoder chunks occasionally have a discontinuity. Repair only a 3 ms
    // neighborhood of an abrupt boundary; do not fade every streamed packet.
    for(const boundary of boundaries){
     if(Math.abs(samples[boundary]-samples[boundary-1])<.04)continue;
     const radius=Math.min(Math.round(rate*.0015),boundary,samples.length-boundary-1);
     const lo=boundary-radius,hi=boundary+radius,left=samples[lo],right=samples[hi];
     for(let i=lo+1;i<hi;i++)samples[i]=left+(right-left)*(i-lo)/(hi-lo);
    }
    const fade=Math.min(Math.round(rate*.003),Math.floor(samples.length/2));
    for(let i=0;i<fade;i++){samples[i]*=i/fade;samples[samples.length-1-i]*=i/fade;}
    const buffer=context.createBuffer(1,samples.length,rate);buffer.copyToChannel(samples,0);
    const source=context.createBufferSource();source.buffer=buffer;source.connect(gain);
    const start=context.currentTime+.06;session.start=start;session.end=start+buffer.duration;
    session.segments.push({start,end:session.end,samples,rate});session.sources.add(source);
    source.onended=()=>{source.disconnect();session.sources.delete(source);};source.start(start);
    session.pending=[];session.buffered=0;
   }
   async function drain(){
    let stalledAt=null,last=context.currentTime;
    while(version===revision&&context.currentTime<session.end){
     await new Promise(r=>setTimeout(r,30));
     if(context.currentTime===last){stalledAt??=Date.now();if(Date.now()-stalledAt>10000)throw Error('음성이 일시 중지됐습니다. 화면을 한 번 누른 뒤 다시 재생하세요.');}
     else{last=context.currentTime;stalledAt=null;}
    }
   }
   try{
    const decoder=new TextDecoder();let pending='';
    while(true){const part=await reader.read();if(part.done)break;pending+=decoder.decode(part.value,{stream:true});let line;
     while((line=pending.indexOf('\n'))>=0){const item=JSON.parse(pending.slice(0,line));pending=pending.slice(line+1);if(version!==revision)return {cancelled:true};
      if(item.voice)emit('airi-voice-provider',item.voice);
      if(item.type==='error')throw Error(item.error);
      if(item.type==='done')done=true;
      if(item.type==='audio'){
       const bytes=Uint8Array.from(atob(item.pcm),c=>c.charCodeAt(0));const view=new DataView(bytes.buffer),samples=new Float32Array(bytes.length/2);
       for(let i=0;i<samples.length;i++)samples[i]=view.getInt16(i*2,true)/32768;
       if(!samples.length||!Number.isFinite(item.sample_rate)||item.sample_rate<8000)throw Error('잘못된 음성 데이터');
       const duration=samples.length/item.sample_rate;
       if(session.firstChunkAt===null){session.firstChunkAt=Date.now();session.firstChunkDuration=duration;}
       session.pending.push({samples,rate:item.sample_rate});session.buffered+=duration;
       // Validate the complete sentence before playback. A fast first packet
       // cannot predict sustained inference speed, particularly on a busy GPU.

      }
     }
    }
    if(!done)throw Error('음성 스트림이 중단되었습니다.');
    flush();
    if(session.start===null)throw Error('생성된 음성 데이터가 없습니다. 다시 재생해 주세요.');
    await drain();
    return {ok:true,cancelled:version!==revision};
   }catch(error){if(error.name==='AbortError'||version!==revision)return {cancelled:true};throw error;}
   finally{cancelAnimationFrame(frame);clearTimeout(frame);for(const source of session.sources){try{source.stop();}catch{}}gain.disconnect();if(current===session){current=null;window.airiBrowserSpeech=false;document.body.classList.remove('airi-speaking');emit('airi-speech-state',{speaking:false,level:0});emit('airi-speech-finished');}}
  });queue=job;return job;
 }
 window.AIRIVoicePlayer={play,stop,unlock};
 window.addEventListener('pagehide',stop);
})();
