let wakeWaiting=true, silenceMisses=0, microphoneSession=null, microphoneBlocked=false, listenRetryAt=0;
function releaseMicrophone(){const m=microphoneSession;microphoneSession=null;if(!m)return;m.processor.onaudioprocess=null;m.source.disconnect();m.processor.disconnect();m.mute.disconnect();m.stream.getTracks().forEach(t=>t.stop());m.context.close().catch(()=>{});}
function resumeListening(){if(!microphoneBlocked&&Date.now()>=listenRetryAt&&!window.airiFocus&&token&&$('always-listen').checked&&!busy&&!recorder&&!transcribing&&!voiceStarting&&!window.airiBrowserSpeech)return startListening(wakeWaiting);}
const wakePattern=/(?:헤이|해이|hey|hi)?\s*(?:아이리|아이 리|에어리|airi|airy)[,.!?\s]*/i;
function voiceLabel(){if(recorder?.longMode)return '길게 듣는 중 · 3초 쉬면 자동 전송돼요. 버튼으로도 마칠 수 있어요.';return wakeWaiting?'호출어를 기다려요 · 헤이 아이리 / Hey AIRI':'듣고 있어요…';}
async function startListening(waiting=false){
  if(window.airiFocus)return;
  if(busy||recorder||transcribing||voiceStarting)return;
  if(!navigator.mediaDevices?.getUserMedia){toast('Safari에서 이 주소를 열어 마이크를 사용해 주세요.');return;}
  voiceStarting=true;wakeWaiting=waiting;let stream,context;
  try{
    // Automatic listening must never cancel another tab's ongoing reply.
    if(window.airiBrowserSpeech||(await api('speech-state')).speaking){
      $('voice-state').textContent='답변이 끝나면 다시 들을게요.';
      if(waiting)setTimeout(()=>{if($('always-listen').checked)startListening(true);},700);
      return;
    }
    if(microphoneSession&&microphoneSession.stream.getTracks().some(t=>t.readyState==='ended'))releaseMicrophone();
    if(!microphoneSession){
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    context=new (window.AudioContext||window.webkitAudioContext)();await Promise.race([context.resume(),new Promise((_,reject)=>setTimeout(()=>reject(new Error('처음 한 번 음성대화 시작을 눌러 마이크를 활성화해 주세요.')),2000))]);
    const source=context.createMediaStreamSource(stream),processor=context.createScriptProcessor(4096,1,1),mute=context.createGain();mute.gain.value=0;source.connect(processor);processor.connect(mute);mute.connect(context.destination);
    microphoneSession={stream,context,source,processor,mute};
    }
    ({stream,context}=microphoneSession);const {source,processor,mute}=microphoneSession;
    if(context.state==='suspended')await context.resume();
    microphoneBlocked=false;
    recorder={stream,context,source,processor,mute,chunks:[],started:performance.now(),lastVoice:0,heard:false,voicedFrames:0,longMode:!waiting&&$('long-listen').checked,lastSecond:-1};voiceSession=true;$('end-voice').hidden=false;$('microphone').textContent=waiting?'지금 말하기':'말하기 종료';$('microphone').classList.toggle('recording',!waiting);$('voice-state').textContent=voiceLabel();
    processor.onaudioprocess=event=>{
      if(!recorder||busy||transcribing||window.airiBrowserSpeech||window.airiServerSpeech)return;const input=event.inputBuffer.getChannelData(0),t=performance.now();recorder.chunks.push(new Float32Array(input));
      const rms=Math.sqrt(input.reduce((s,v)=>s+v*v,0)/input.length);
      if(rms>0.015){recorder.voicedFrames+=input.length;recorder.heard=true;recorder.lastVoice=t;}
      if(!recorder.heard){recorder.chunks=recorder.chunks.slice(-4);recorder.started=t;return;}
      if(!wakeWaiting&&(!recorder.lastSignal||t-recorder.lastSignal>2000)){recorder.lastSignal=t;api('voice-activity',{}).catch(()=>{});}
      if(recorder.longMode){const seconds=Math.floor((t-recorder.started)/1000);if(seconds!==recorder.lastSecond){recorder.lastSecond=seconds;$('voice-state').textContent='길게 듣는 중 '+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0')+' / 5:00 · 3초 쉬면 자동 전송';}}
      if((t-recorder.lastVoice>(recorder.longMode?3000:(wakeWaiting?650:1000)))||t-recorder.started>(recorder.longMode?300000:28000)){if(recorder.voicedFrames/context.sampleRate<0.35){recorder.chunks=[];recorder.heard=false;recorder.voicedFrames=0;recorder.started=t;}else stopListening(true);}
    };
  }catch(e){microphoneSession=null;microphoneBlocked=['NotAllowedError','NotFoundError'].includes(e.name);listenRetryAt=Date.now()+5000;stream?.getTracks().forEach(t=>t.stop());if(context)await context.close().catch(()=>{});voiceSession=false;$('end-voice').hidden=true;const reason=e.name==='NotAllowedError'?'마이크 권한을 허용하세요. 내장 브라우저에서 안 되면 Safari로 열어 주세요.':e.name==='NotFoundError'?'마이크를 찾지 못했습니다. macOS 입력 장치를 확인하세요.':e.message;toast(reason);$('voice-state').textContent='마이크 연결 확인 필요';}
  finally{voiceStarting=false;}
}
async function stopListening(send){
  if(!recorder)return;const r=recorder;recorder=null;const rate=r.context.sampleRate;if(!$('always-listen').checked||window.airiFocus)releaseMicrophone();$('microphone').textContent='음성대화 시작';$('microphone').classList.remove('recording');
  if(!send)return;transcribing=true;$('microphone').disabled=true;$('voice-state').textContent=wakeWaiting?'호출어 확인 중…':'정확하게 받아쓰는 중…';
  try{
    const response=await fetch('/api/transcribe',{method:'POST',headers:{'X-AIRI-Token':token,'Content-Type':'audio/wav','X-AIRI-Language':'auto'},body:wavBlob(r.chunks,rate)}),result=await response.json();
    if(!response.ok)throw new Error(result.error);if(!voiceSession)return;
    let text=result.text.trim();
    if(!text){if(!wakeWaiting){silenceMisses++;$('voice-state').textContent='잘 듣지 못했어요. 다시 말해 주세요.';if(silenceMisses>=2)wakeWaiting=true;}return;}
    if(wakeWaiting){if(!wakePattern.test(text))return;text=text.replace(wakePattern,'').trim();wakeWaiting=false;silenceMisses=0;
      if(!text){await api('speak',{text:result.language==='en'?"I'm listening.":'네, 듣고 있어요.'});while((await api('speech-state')).speaking&&voiceSession)await new Promise(r=>setTimeout(r,250));return;}
    }
    if(/대화\s*(종료|그만)|그만\s*들어|대기\s*(해|모드)|stop listening|go to sleep/i.test(text)){wakeWaiting=true;return;}
    silenceMisses=0;$('voice-state').textContent='음성 인식 완료 · '+result.seconds+'초';window.airiLastSTT=result.seconds;
    await submitChat(text);
  }catch(e){listenRetryAt=Date.now()+1500;voiceSession=$('always-listen').checked;toast(e.message);$('voice-state').textContent='음성 연결을 확인해 주세요.';}
  finally{transcribing=false;$('microphone').disabled=false;if(voiceSession){await new Promise(r=>setTimeout(r,100));if(voiceSession)startListening(wakeWaiting);}else{$('end-voice').hidden=true;}}
}
function endVoice(){speechEpoch++;window.AIRIVoicePlayer?.stop();const keepWaiting=$('always-listen').checked;voiceSession=false;stopListening(false);api('speak-stop',{}).catch(()=>{});$('end-voice').hidden=true;$('voice-state').textContent=keepWaiting?'호출어 대기로 돌아갑니다.':'음성대화를 종료했습니다.';if(keepWaiting)setTimeout(()=>{if(!busy&&!transcribing)startListening(true);},600);}
$('microphone').onclick=()=>{microphoneBlocked=false;window.AIRIVoicePlayer?.unlock().catch(()=>{});if(recorder){if(wakeWaiting){wakeWaiting=false;recorder.longMode=$('long-listen').checked;$('microphone').textContent='말하기 종료';$('voice-state').textContent=voiceLabel();}else stopListening(true);}else startListening(false);};
$('end-voice').onclick=endVoice;
$('always-listen').checked=localStorage.getItem('airi-always-listen')==='true';
$('always-listen').onchange=()=>{microphoneBlocked=false;localStorage.setItem('airi-always-listen',String($('always-listen').checked));if($('always-listen').checked){if(recorder){wakeWaiting=true;$('voice-state').textContent=voiceLabel();}else startListening(true);}else{endVoice();releaseMicrophone();}};
window.addEventListener('pagehide',()=>{voiceSession=false;releaseMicrophone();});
setTimeout(()=>{if($('always-listen').checked&&token)startListening(true);},1200);

$('long-listen').checked=localStorage.getItem('airi-long-listen')==='true';
$('long-listen').onchange=()=>{localStorage.setItem('airi-long-listen',String($('long-listen').checked));if(recorder&&!wakeWaiting){recorder.longMode=$('long-listen').checked;$('voice-state').textContent=voiceLabel();}};

setInterval(resumeListening,750);
window.addEventListener('airi-chat-finished',resumeListening);
window.addEventListener('airi-speech-finished',()=>setTimeout(resumeListening,100));
window.addEventListener('online',()=>{listenRetryAt=0;resumeListening();});
window.addEventListener('pointerdown',()=>{if(microphoneBlocked){microphoneBlocked=false;listenRetryAt=0;}resumeListening();},{passive:true});

window.addEventListener('airi-speech-start',()=>{if(recorder&&wakeWaiting){recorder.chunks=[];recorder.heard=false;recorder.voicedFrames=0;recorder.started=performance.now();recorder.lastVoice=0;}});

// Native automatic camera speech must not be transcribed as the user's voice.
window.addEventListener('airi-speech-state',e=>{
 if(window.airiBrowserSpeech)return;
 const speaking=!!e.detail?.speaking;
 if(speaking!==!!window.airiServerSpeech&&recorder){recorder.chunks=[];recorder.heard=false;recorder.voicedFrames=0;recorder.started=performance.now();recorder.lastVoice=0;}
 window.airiServerSpeech=speaking;
});
