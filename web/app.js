class SpeechFilter {
  constructor(){this.stack=[];this.pending="";}
  push(text){let out='';const pairs={'(':')','（':'）','[':']','【':'】'};
    for(const ch of text){if(pairs[ch])this.stack.push(pairs[ch]);else if(this.stack.length){if(ch===this.stack[this.stack.length-1])this.stack.pop();}else out+=ch;}
    // Hold incomplete words so streamed protocol markers cannot be spoken in pieces.
    this.pending+=out;
    const parts=this.pending.match(/^([\s\S]*\s)(\S*)$/);
    if(!parts)return '';
    this.pending=parts[2];return spokenText(parts[1]);
  }
  flush(){const out=spokenText(this.pending);this.pending='';return out;}
}
'use strict';
const $ = (id) => document.getElementById(id);
let token = '', state = null, busy = false, toastTimer;
let recorder=null, voiceSession=false, transcribing=false, voiceStarting=false, speechEpoch=0;
const names = {home:'홈',chat:'대화',memory:'기억과 할 일',automation:'자동화 연습',setup:'설치·연결',activity:'활동 기록'};
const statusNames = {pending:'승인 대기',executing:'실행 중',done:'실행 완료',failed:'실행 실패',unknown:'결과 확인 필요',rejected:'거절됨',expired:'만료됨'};
function el(tag, cls, text) { const node=document.createElement(tag); if(cls) node.className=cls; if(text!==undefined) node.textContent=text; return node; }
function toast(message,action) { $('toast').replaceChildren(el('span','',message));if(action){const b=el('button','quiet','결과 열기');b.onclick=action;$('toast').append(b);}$('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,action?12000:4500); }
function delegationText(text){return text.replace(/^\s*(?:티모(?:에게|한테)|timo[:,])\s*/i,'/muse ');}
function spokenText(text){return String(text).normalize('NFC')
  .replace(/[\u3131-\u318e]+/gu,'')
  .replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}\uFE0F\uFE0E\u200D\u20E3]/gu,'')
  .replace(/AIRI_RESULT_[a-f0-9]{16,64}_(?:BEGIN|END)/gi,'')
  .replace(/(?:작업\s*ID|job\s*id)\s*:\s*[a-f0-9]{24,64}/gi,'')
  .replace(/(^|[^A-Za-z0-9])[a-f0-9]{24,64}(?=$|[^A-Za-z0-9])/gi,'$1')
  .replace(/Muse 작업함에 등록했어요\./g,'티모에게 전달할 요청을 등록했어.')
  .replace(/Muse 연결/g,'티모 연결')
  .replace(/Muse 작업 /g,'티모의 작업 ')
  .replace(/(^|[^A-Za-z0-9])AIRI(?=$|[^A-Za-z0-9])/gi,'$1아이리');}

async function api(path, body) {
  if(['speak','speech-prepare'].includes(path)&&body?.text)body={...body,text:spokenText(body.text)};
  if(['speak','speech-prepare'].includes(path)&&!/[\p{L}\p{N}]/u.test(body?.text||''))return {ok:true,skipped:true};
  if(path==='speak'&&window.airiReportReading&&!body?.reportNarration){window.dispatchEvent(new CustomEvent('airi-report-interrupt'));window.AIRIVoicePlayer?.stop();}
  if(path==='speak'&&state?.settings?.tts_engine==='qwen3_reference'&&window.AIRIVoicePlayer)return window.AIRIVoicePlayer.play(body.text);
  if(path==='speak'){
    const epoch=speechEpoch;
    const clip=await api('speech-prepare',body);if(!clip.id||epoch!==speechEpoch)return {cancelled:true};
    let playback;
    do{if(epoch!==speechEpoch)return {cancelled:true};playback=await api('speech-play',clip);if(playback.busy)await new Promise(r=>setTimeout(r,150));}while(playback.busy);
    if(!playback.cancelled)window.dispatchEvent(new CustomEvent('airi-speech-start',{detail:{id:clip.id}}));
    while(!playback.cancelled&&(await api('speech-state')).speaking)await new Promise(r=>setTimeout(r,100));
    if(!playback.cancelled)window.dispatchEvent(new CustomEvent('airi-speech-finished'));
    return playback;
  }
  const desktopOperation=body!==undefined&&/^(camera|image|files|attachment|video|workbench)/.test(path);
  if(desktopOperation)window.dispatchEvent(new CustomEvent('airi-operation',{detail:{phase:'start',name:path}}));
  const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'X-AIRI-Token':token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json(); if(desktopOperation)window.dispatchEvent(new CustomEvent('airi-operation',{detail:{phase:response.ok?'done':'error',name:path}})); if(data.voice)window.dispatchEvent(new CustomEvent('airi-voice-provider',{detail:data.voice})); if(!response.ok) throw new Error(data.error||'연결을 확인해 주세요.'); return data;
}
function showPage(name) { document.querySelectorAll('.page').forEach(n=>n.classList.toggle('active',n.id==='page-'+name)); document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.page===name)); $('page-title').textContent=names[name]; if(name==='chat')renderMessages(); if(name==='setup') health().catch(e=>toast(e.message)); }
document.querySelectorAll('.nav').forEach(n=>n.addEventListener('click',()=>showPage(n.dataset.page)));
function message(role,text) {const node=el('div','message '+role);const content=el('div','message-text',text);node.append(content);if(role==='assistant'){const button=el('button','speak','읽어주기');button.addEventListener('click',()=>api('speak',{text:content.textContent}).catch(e=>toast(e.message)));node.append(button);} $('messages').append(node);$('messages').scrollTop=$('messages').scrollHeight;return content;}
function renderMessages(){ $('messages').replaceChildren(); (state.messages||[]).forEach(m=>message(m.role,m.content)); $('welcome').hidden=state.messages.length>0; }
function empty(parent,text){parent.append(el('div','empty',text));}
function render(){
  window.dispatchEvent(new CustomEvent('airi-desktop-tasks',{detail:state.tasks||[]}));
  if(typeof renderPlanner==='function')renderPlanner();if(typeof renderMCP==='function')renderMCP();
  $('memory-count').textContent=state.memories.length; $('task-count').textContent=state.tasks.filter(t=>!t.done).length;
  const memoryList=$('memory-list');memoryList.replaceChildren(); if(!state.memories.length)empty(memoryList,'아직 저장한 기억이 없어요.');
  state.memories.forEach(m=>{const item=el('div','item');item.append(el('div','item-content',m.content));const b=el('button','delete','삭제');b.setAttribute('aria-label','메모 삭제');b.onclick=async()=>{if(!confirm('이 메모를 삭제할까요?'))return;try{await api('memory-delete',{id:m.id});await refresh();}catch(e){toast(e.message);}};item.append(b);memoryList.append(item);});
  const approvals=$('approval-list');approvals.replaceChildren();if(!state.approvals.length)empty(approvals,'요청을 만들면 여기에 승인 카드가 나타납니다.');
  state.approvals.forEach(a=>{const card=el('article','approval');const head=el('div','approval-head');head.append(el('strong','', JSON.parse(a.payload).name||'n8n · 메시지 전달 연습'),el('span','pill '+(a.status==='done'?'good':a.status==='pending'?'pending':''),statusNames[a.status]||a.status));card.append(head,el('p','',JSON.parse(a.payload).message));if(a.result)card.append(el('code','',a.result));if(a.status==='pending'){const actions=el('div','approval-actions');for(const [label,approve,cls] of [['승인하고 실행',true,'primary'],['거절',false,'secondary']]){const b=el('button',cls,label);b.onclick=async()=>{actions.querySelectorAll('button').forEach(x=>x.disabled=true);try{const result=await api('decision',{id:a.id,approve});toast(statusNames[result.status]||result.status);}catch(e){toast(e.message);}await refresh();};actions.append(b);}card.append(actions);}approvals.append(card);});
  const pending=state.approvals.filter(a=>a.status==='pending').length;$('approval-count').textContent=pending;$('approval-count').hidden=!pending;
  const events=$('event-list');events.replaceChildren();if(!state.events.length)empty(events,'아직 활동 기록이 없습니다.');state.events.forEach(e=>{const item=el('div','event');item.append(el('time','',new Date(e.created).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})),el('strong','',({saved:'저장',read:'도구 조회',chat:'대화',pending:'승인 요청',done:'실행 완료',error:'오류',blocked:'차단',rejected:'거절',cancelled:'중단'})[e.kind]||e.kind),el('div','',e.detail));events.append(item);});
}
let museSpeechChain=Promise.resolve();
function readMuseResults(incoming){
  if(!$('auto-speak').checked||window.airiFocus||(document.hidden&&!window.airiDesktop))return;
  const epoch=speechEpoch;
  for(const result of incoming){
    // Speak the answer, not its internal job ID/status line.
    const text=result.content.split('\n').slice(1).join('\n').trim();
    if(!text)continue;
    museSpeechChain=museSpeechChain.catch(()=>{}).then(async()=>{
      if(epoch!==speechEpoch||!$('auto-speak').checked||window.airiFocus||(document.hidden&&!window.airiDesktop))return;
      await api('speak',{text:text.length>1400?text.slice(0,1400)+' 나머지는 대화에서 확인해 줘.':text});
    }).catch(error=>toast('Muse 결과 음성을 재생하지 못했어요. '+error.message));
  }
}
async function refresh(){const previous=state;state=await api('state');render();if(previous){const oldIds=new Set((previous.messages||[]).map(m=>m.id));const incoming=(state.messages||[]).filter(m=>!oldIds.has(m.id)&&m.role==='assistant'&&(m.content.startsWith('Muse 작업 ')||m.content.startsWith('# AIRI INTELLIGENCE BRIEF')||m.content.startsWith('AIRI INTELLIGENCE BRIEF')));if(incoming.length&&!busy){renderMessages();const reports=incoming.filter(m=>m.content.includes('AIRI INTELLIGENCE BRIEF'));if(reports.length)window.dispatchEvent(new CustomEvent('airi-desktop-notification',{detail:'분석 브리핑이 완성됐어. 대화에서 확인해 줘.'}));if(incoming.some(m=>m.content.startsWith('Muse 작업 ')))window.dispatchEvent(new CustomEvent('airi-desktop-notification',{detail:'티모의 작업 결과가 도착했어.'}));toast(reports.length?'분석 브리핑이 완성됐어.':'티모의 작업 결과가 도착했어.',()=>showPage('chat'));readMuseResults(incoming.filter(m=>m.content.startsWith('Muse 작업 ')));}const finished=state.tasks.filter(t=>['completed','partial','failed'].includes(t.status)&&previous.tasks.some(old=>old.id===t.id&&['scheduled','running'].includes(old.status)));if(finished.length){const task=finished[0];window.dispatchEvent(new CustomEvent('airi-desktop-notification',{detail:task.title+' · 결과가 도착했어.'}));toast(task.title+' · '+(task.status==='completed'?'작업 결과가 준비됐어요':'결과 확인이 필요해요'),()=>showTaskResult(task));}}}
async function health(){
  const h=await api('health');$('connection').textContent=state.settings.model.startsWith('freellmapi:')?'FreeLLMAPI 선택 · 응답 시 연결 확인':state.settings.model.startsWith('openai:')?'OpenAI 선택 · 응답 시 연결 확인':h.ollama?'로컬 모델 연결됨':'Ollama 연결 필요';$('connection').classList.toggle('ready',h.ollama);
  $('voice-state').textContent=h.voice?'로컬 음성 준비됨':'음성 모델 설치 필요';
  for(const [id,ok] of [['ollama-state',h.ollama],['n8n-state',h.n8n]]){$(id).textContent=ok?'연결됨':'연결 필요';$(id).className='pill'+(ok?' good':'');}
  const select=$('model');select.replaceChildren();const models=h.models.filter(m=>!m.capabilities||m.capabilities.includes('completion'));
  if(!models.length){const o=el('option','','설치된 모델 없음');o.value='';select.append(o);}for(const m of models){const option=el('option','',m.label||(m.name==='openai:auto'?'OpenAI · 등록된 API 사용':m.name));option.value=m.name;select.append(option);}select.value=state.settings.model;
  if(models.length&&!models.some(m=>m.name===state.settings.model)){const missing=el('option','',state.settings.model+' · 설치 필요');missing.value=state.settings.model;select.append(missing);select.value=state.settings.model;}
  select.disabled=busy||!models.length;
}
$('model').onchange=async()=>{try{await api('settings',{model:$('model').value});await refresh();toast('대화 모델을 변경했습니다.');}catch(e){toast(e.message);}};
$('refresh-health').onclick=()=>health().catch(e=>toast(e.message));
async function submitChat(text){
 if(window.Stock101?.matches(text))window.Stock101.open();
  if(busy||!text.trim())return;
  busy=true;
  if(recorder)await stopListening(false);
  await interruptSpeech();
  const epoch=speechEpoch,started=performance.now();
  const chatController=new AbortController();window.airiCancelChat=()=>chatController.abort();
  let mindHandled=false;
  let speechBuffer='',speechChain=Promise.resolve(),prepareChain=Promise.resolve(),firstSpeech=null,speechError=null,backendLabel='',fallbackReason='',routeLabel='';
  const speechFilter=new SpeechFilter();let speechQueued=0;
  busy=true;$('microphone').disabled=true;$('send').disabled=true;$('model').disabled=true;$('welcome').hidden=true;$('message').value='';
  window.dispatchEvent(new CustomEvent('airi-context',{detail:{text,phase:'request'}}));
  message('user',text);const output=message('assistant','');
  $('chat-status').textContent='AIRI가 생각하고 있어요…';
  function speakSentence(sentence){
    const plain=spokenText(sentence.replace(/[*#`]/g,'').trim());if(!/[\p{L}\p{N}]/u.test(plain))return;speechQueued++;
    if(state?.settings?.tts_engine==='qwen3_reference'&&window.AIRIVoicePlayer){
      if(!$('auto-speak').checked||epoch!==speechEpoch)return;
      const playback=window.AIRIVoicePlayer.play(plain,{onStart:()=>{if(firstSpeech===null)firstSpeech=((performance.now()-started)/1000).toFixed(1);}}).catch(e=>{speechError=e;});
      speechChain=Promise.all([speechChain,playback]);return;
    }
    // Synthesis runs ahead while the previous sentence plays; playback stays ordered.
    const prepared=prepareChain.then(async()=>{
      if(!$('auto-speak').checked||epoch!==speechEpoch)return {};
      return api('speech-prepare',{text:plain});
    }).catch(error=>({error}));
    prepareChain=prepared;
    speechChain=speechChain.then(async()=>{
      const clip=await prepared;if(clip.error)throw clip.error;
      if(!clip.id||!$('auto-speak').checked||epoch!==speechEpoch)return;
      let playback;
      do{
        if(epoch!==speechEpoch)return;
        playback=await api('speech-play',{id:clip.id,generation:clip.generation});
        if(playback.busy)await new Promise(r=>setTimeout(r,150));
      }while(playback.busy);
      if(playback.cancelled)return;
      window.dispatchEvent(new CustomEvent('airi-speech-start',{detail:{id:clip.id}}));
      if(firstSpeech===null)firstSpeech=((performance.now()-started)/1000).toFixed(1);
      while(epoch===speechEpoch&&(await api('speech-state')).speaking)await new Promise(r=>setTimeout(r,100));
    }).catch(e=>{speechError=e;});
  }
  function flushSentences(final=false){
    if(final)speechBuffer+=speechFilter.flush();
    let match;
    while((match=speechBuffer.match(/^([\s\S]*?[.!?。！？](?:\s+|$)|[\s\S]*?\n)/))){if(match[0].length>(/[가-힣]/.test(match[0])?80:150))break;speechBuffer=speechBuffer.slice(match[0].length);speakSentence(match[0]);}
    const korean=/[가-힣]/.test(speechBuffer);const limit=korean?100:200;
    if(speechBuffer.length>limit){let cut=speechBuffer.lastIndexOf(' ',limit);if(cut<Math.floor(limit/2))cut=limit;speakSentence(speechBuffer.slice(0,cut));speechBuffer=speechBuffer.slice(cut);}
    if(final){speakSentence(speechBuffer);speechBuffer='';}
  }
  try{
    const response=await fetch('/api/chat',{signal:chatController.signal,method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify({message:delegationText(text),voice:$('auto-speak').checked})});
    if(!response.ok){const d=await response.json();throw new Error(d.error);}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',completed=false,seconds=0,firstToken=0;
    while(true){
      const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let newline;
      while((newline=buffer.indexOf('\n'))>=0){
        const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(!line)continue;const part=JSON.parse(line);
        if(['tool','sources','library_sources','image_job'].includes(part.type))window.dispatchEvent(new CustomEvent('airi-operation',{detail:{phase:'start',name:part.name||part.type}}));
        if(part.type==='affect'){mindHandled=true;const map={HAPPY:'happy',EXCITED:'excited',CONFUSED:'confused',CONCERNED:'worried'};if(map[part.emotion])window.dispatchEvent(new CustomEvent('airi-emotion',{detail:{name:map[part.emotion],intensity:part.intensity}}));window.dispatchEvent(new CustomEvent('airi-mind-state',{detail:part}));}
        if(part.type==='token'){output.textContent+=part.text;speechBuffer+=speechFilter.push(part.text);flushSentences();$('messages').scrollTop=$('messages').scrollHeight;$('chat-status').textContent='답변을 작성하고 읽어주고 있어요…';}
        if(part.type==='approval'&&part.id){const button=el('button','secondary chat-approval','실행 요청 확인');button.type='button';button.onclick=async()=>{await refresh();showPage('automation');};output.parentElement.append(button);}
        if(part.type==='stock101_open'&&window.webkit?.messageHandlers?.airiDesktop)window.Stock101?.open();
        if(part.type==='saved'){window.dispatchEvent(new CustomEvent('airi-saved',{detail:part}));toast(part.kind==='skill'?'스킬을 저장했습니다.':'일정을 저장했습니다.');refresh().catch(()=>{});}
        if(part.type==='route'){routeLabel=part.tier+' · '+part.accuracy;const badge=el('small','muted',routeLabel+' · '+part.reason);output.parentElement.append(badge);}
        if(part.type==='skills')$('chat-status').textContent='스킬 적용: '+part.names.join(', ');
        if(part.type==='tool')$('chat-status').textContent=part.name==='web_search'?'웹 출처와 본문을 확인하고 있어요…':part.name==='WeatherAPI'?'날씨를 조회하고 있어요…':'자료를 확인하고 있어요…';
        if(part.type==='product_results'&&window.AIRIProductResults){const box=el('aside','product-camera-results');window.AIRIProductResults.render(box,part.result);output.parentElement.append(box);}
        if(part.type==='library_sources'){const box=el('aside','research-sources');box.append(el('strong','','NAS 투자 자료 · 참고 페이지'));for(const source of part.sources||[])box.append(el('span','',source.file+' · p. '+source.page));output.parentElement.append(box);}
        if(part.type==='sources'){const list=el('aside','research-sources');list.setAttribute('aria-label','이번 답변의 웹 출처');list.append(el('strong','','조회한 출처'));for(const source of part.sources||[]){if(!/^https:\/\//.test(source.url||''))continue;const a=el('a','',source.title||source.url);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';list.append(a);if(source.published_at)list.append(el('small','',source.published_at));}output.parentElement.append(list);}
        if(part.type==='market'){window.dispatchEvent(new CustomEvent('airi-evidence',{detail:part.cards}));for(const card of part.cards){const box=el('aside','panel market-card');box.append(el('strong','',card.symbol?card.symbol+' · '+card.price+' '+card.currency:'1 '+card.base+' = '+card.rate+' '+card.quote),el('p','muted','As of '+card.as_of+' · '+card.source));if(card.source_url){const a=el('a','','Source ↗');a.href=card.source_url;a.target='_blank';a.rel='noreferrer';box.append(a);}output.parentElement.append(box);}}
        if(part.type==='tool_result'){const badge=el('div','muted','WeatherAPI · '+part.location+' 실제 조회');output.parentElement.append(badge);}
        if(part.type==='backend'){backendLabel=(part.provider||'모델')+' · '+part.model+(part.device_name?' · '+part.device_name:'');fallbackReason=part.reason||'';if(part.fallback){toast((fallbackReason||'주 모델 연결 실패')+' '+(part.provider||'모델')+'로 답합니다.');}$('chat-status').textContent=backendLabel;}
        if(part.type==='image_job')window.dispatchEvent(new CustomEvent('airi-image-job',{detail:part}));
        if(part.type==='done'){completed=true;seconds=part.seconds;firstToken=part.first_token_seconds;}
        if(part.type==='error')throw new Error(part.message);
      }
    }
    if(!completed)throw new Error('응답 연결이 중단되었습니다. 다시 시도해 주세요.');
    window.dispatchEvent(new CustomEvent('airi-chat-result',{detail:{ok:true,text:spokenText(output.textContent).slice(0,200)}}));
    flushSentences(true);await speechChain;
    $('chat-status').textContent=backendLabel+(routeLabel?' · '+routeLabel:'')+(fallbackReason?' · '+fallbackReason:'')+' · 생성 '+seconds+'초'+(firstToken?' · 첫 글자 '+firstToken+'초':'')+(firstSpeech?' · 첫 재생 시작 '+firstSpeech+'초':'');
    if(speechError)toast('읽어주기를 완료하지 못했습니다. '+speechError.message);
    window.dispatchEvent(new CustomEvent('airi-latency',{detail:{'STT 초':window.airiLastSTT??null,'첫 토큰 초':firstToken,'첫 음성 초':firstSpeech,'전체 대화 초':((performance.now()-started)/1000).toFixed(1),'모델':backendLabel}}));
    window.airiLastSTT=null;
    window.dispatchEvent(new CustomEvent('airi-speech-finished'));
    if(!mindHandled&&/고마|잘했|귀여|애교|thank|cute|merci|mignon/i.test(text))window.dispatchEvent(new CustomEvent('airi-emotion',{detail:{name:/귀여|cute|mignon/i.test(text)?'cute':/애교/.test(text)?'aegyo':'happy'}}));
  }catch(e){
    if(e.name==='AbortError'){
      speechBuffer='';speechFilter.flush();
      $('chat-status').textContent='응답 표시를 멈췄습니다';
      window.dispatchEvent(new CustomEvent('airi-chat-result',{detail:{ok:false,cancelled:true,text:'응답 표시를 멈췄습니다'}}));
      return;
    }
    window.dispatchEvent(new CustomEvent('airi-chat-result',{detail:{ok:false,text:e.message}}));
    // A text-stream failure must not cut off audio already received successfully.
    flushSentences(true);await speechChain;
    output.append(el('p','muted','응답을 완료하지 못했어요. '+e.message));$('chat-status').textContent='설치·연결에서 상태를 확인해 주세요.';
    window.dispatchEvent(new CustomEvent('airi-emotion',{detail:{name:'sad'}}));
  }finally{window.airiCancelChat=null;busy=false;$('microphone').disabled=false;$('send').disabled=false;$('model').disabled=false;await refresh().catch(()=>{});window.dispatchEvent(new CustomEvent('airi-chat-finished'));}
}
$('chat-form').onsubmit=e=>{e.preventDefault();submitChat($('message').value);};
$('message').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();submitChat($('message').value);}};
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>submitChat(b.dataset.prompt));
$('clear-chat').onclick=async()=>{if(busy){toast('응답이 끝난 뒤 비워 주세요.');return;}if(!confirm('대화 기록을 비울까요? 저장한 메모와 할 일은 유지됩니다.'))return;try{await api('chat-clear',{});await refresh();renderMessages();}catch(e){toast(e.message);}};
function interruptSpeech(){window.dispatchEvent(new CustomEvent('airi-report-interrupt'));speechEpoch++;window.AIRIVoicePlayer?.stop();window.dispatchEvent(new CustomEvent('airi-speech-finished'));return api('speak-stop',{}).catch(e=>toast(e.message));}
$('stop-speech').onclick=interruptSpeech;

// Prepare the same conversation model while the user starts composing.
// This does not send draft text, generate filler, or start a background polling loop.
let conversationPrepareAt=0;
function prepareConversationInput(){
  if(!token||busy||document.hidden||window.airiFocus||Date.now()-conversationPrepareAt<60000)return;
  conversationPrepareAt=Date.now();
  api('humanlike',{action:'prepare'}).catch(()=>{});
}
$('message').addEventListener('focus',prepareConversationInput);
$('message').addEventListener('input',prepareConversationInput);
for(const [form,input,path,key,msg] of [['memory-form','memory-input','memories','content','기억을 저장했습니다.'],['practice-form','practice-input','practice','message','승인 요청을 만들었습니다.']]){
  $(form).onsubmit=async e=>{e.preventDefault();const b=$(form).querySelector('button');b.disabled=true;try{await api(path,{[key]:$(input).value});if(path!=='practice')$(input).value='';await refresh();toast(msg);}catch(error){toast(error.message);}finally{b.disabled=false;}};
}
(async()=>{try{const boot=await fetch('/api/bootstrap').then(r=>r.json());token=boot.token;await refresh();renderMessages();await health();}catch(e){toast('웹앱에 연결하지 못했습니다. 시작 파일을 다시 실행해 주세요.');}})();
setInterval(()=>{if(!busy&&token)refresh().catch(()=>{});},15000);

function wavBlob(chunks, sampleRate){
  const size=chunks.reduce((n,c)=>n+c.length,0);const all=new Float32Array(size);let offset=0;for(const c of chunks){all.set(c,offset);offset+=c.length;}
  const count=Math.floor(size*16000/sampleRate), buffer=new ArrayBuffer(44+count*2), view=new DataView(buffer);
  function ascii(at,value){for(let i=0;i<value.length;i++)view.setUint8(at+i,value.charCodeAt(i));}
  ascii(0,'RIFF');view.setUint32(4,36+count*2,true);ascii(8,'WAVE');ascii(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);ascii(36,'data');view.setUint32(40,count*2,true);
  for(let i=0;i<count;i++){const start=Math.floor(i*sampleRate/16000),end=Math.max(start+1,Math.floor((i+1)*sampleRate/16000));let sum=0;for(let j=start;j<end&&j<all.length;j++)sum+=all[j];const sample=Math.max(-1,Math.min(1,sum/(end-start)));view.setInt16(44+i*2,Math.round(sample<0?sample*32768:sample*32767),true);}
  return new Blob([buffer],{type:'audio/wav'});
}

/* Presentation adapter only. Tasks and speech remain in the existing AIRI page. */
(()=>{
 const send=detail=>window.webkit?.messageHandlers?.airiDesktop?.postMessage(detail);
 if(!window.webkit?.messageHandlers?.airiDesktop)return;
 window.airiDesktop=true;
 let lastPresence='',lastTasks='',sleeping=false,previousFocus=false;
 window.addEventListener('airi-context',e=>{if(e.detail.phase==='request')send({kind:'request'});});
 window.addEventListener('airi-operation',e=>send({kind:'operation',...e.detail}));
 window.addEventListener('airi-chat-result',e=>send({kind:'result',...e.detail}));
 window.addEventListener('airi-speech-state',e=>{const d=e.detail;const p=d.speaking?'chat':d.preparing?'thinking':'idle';if(p!==window.__desktopSpeech){window.__desktopSpeech=p;send({kind:'speech',state:p});}});
 window.addEventListener('airi-presence',e=>{const p=e.detail.state;if(p!==lastPresence){lastPresence=p;send({kind:'presence',state:p});}});
 window.addEventListener('airi-emotion',e=>send({kind:'emotion',state:e.detail.name}));
 window.addEventListener('airi-spotify',e=>send({kind:'music',playing:!!e.detail.playing}));
 window.addEventListener('airi-desktop-tasks',e=>{const ids=e.detail.filter(t=>t.status==='running').map(t=>t.id).sort().join(',');if(ids!==lastTasks){lastTasks=ids;send({kind:'tasks',active:!!ids});}});
 window.addEventListener('airi-desktop-notification',e=>send({kind:'notification',text:e.detail}));
 window.AIRIDesktopAction=async(action,value)=>{
  if(action==='ask'){
   if(typeof token==='undefined'||!token){send({kind:'error',text:'AIRI 연결을 기다려 주세요.'});return;}
   if(busy){send({kind:'notification',text:'현재 답변이 끝난 뒤 다시 보내 주세요.'});return;}
   await window.AIRIVoicePlayer?.unlock();await submitChat(String(value).slice(0,8000));
  }
  if(action==='listen')$('microphone')?.click();
  if(action==='mute'){
   const checkbox=$('auto-speak');if(checkbox){checkbox.checked=!value;checkbox.dispatchEvent(new Event('change'));}
   if(value)await interruptSpeech();
  }
  if(action==='sleep'){
   if(!sleeping){previousFocus=!!window.airiFocus;sleeping=true;}
   await interruptSpeech();if(typeof endVoice==='function')endVoice();if(typeof releaseMicrophone==='function')releaseMicrophone();
   window.airiFocus=true;
  }
  if(action==='wake'&&sleeping){sleeping=false;window.airiFocus=previousFocus;if(typeof resumeListening==='function')resumeListening();}
  if(action==='settings'){if(window.AIRISettings)window.AIRISettings.open('voice');else showPage('setup');}
 };
 const ready=()=>{if(typeof token!=='undefined'&&token&&state)send({kind:'ready'});else setTimeout(ready,500);};ready();
})();

// Load the PDF report reader after the existing console has mounted.
window.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('script');s.src='/analysis-reports.js';document.head.append(s);},{once:true});
