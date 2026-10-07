'use strict';
let taskFiles=[],uploadingFiles=false;
function fileMeta(id){return (state.attachments||[]).find(f=>f.id===id);}
async function downloadAttachment(file){try{const r=await fetch('/api/attachment/'+file.id,{headers:{'X-AIRI-Token':token}});if(!r.ok)throw new Error('파일을 내려받지 못했습니다.');const url=URL.createObjectURL(await r.blob()),a=el('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message);}}
function attachmentCard(file,remove){const card=el('div','attachment-card'),badge=el('span','file-badge',file.name.split('.').pop().toUpperCase()),body=el('div','attachment-info');body.append(el('strong','',file.name),el('small','',Math.ceil(file.size/1024)+'KB · '+(file.chars||0).toLocaleString()+'자'+(file.truncated?' · 일부 내용만 읽음':'')));const actions=el('div','attachment-actions'),preview=el('button','quiet','내용 보기'),download=el('button','quiet','원본');preview.type=download.type='button';preview.onclick=async()=>{let details=card.querySelector('pre');if(details){details.remove();return;}try{const data=await api('attachment/'+file.id+'?preview=1');details=el('pre','attachment-preview',data.text);card.append(details);}catch(e){toast(e.message);}};download.onclick=()=>downloadAttachment(file);actions.append(preview,download);if(remove){const x=el('button','quiet','제외');x.type='button';x.onclick=remove;actions.append(x);}card.append(badge,body,actions);return card;}
function renderTaskFiles(){const list=$('task-attachments');list.replaceChildren();for(const file of taskFiles)list.append(attachmentCard(file,()=>{taskFiles=taskFiles.filter(f=>f.id!==file.id);renderTaskFiles();}));}
const originalEditTask=editTask;editTask=function(t){originalEditTask(t);taskFiles=JSON.parse(t.attachment_ids||'[]').map(fileMeta).filter(Boolean);renderTaskFiles();};
const originalResetTask=resetTask;resetTask=function(){originalResetTask();taskFiles=[];renderTaskFiles();};
$('task-cancel').onclick=resetTask;
const originalTaskSubmit=$('task-form').onsubmit;
$('task-form').onsubmit=async e=>{if(uploadingFiles){e.preventDefault();toast('첨부 파일을 읽는 중입니다. 완료 후 저장하세요.');return;}await originalTaskSubmit(e);};
$('task-file').onchange=async()=>{const files=Array.from($('task-file').files);if(!files.length)return;if(taskFiles.length+files.length>5){toast('작업당 최대 5개를 첨부하세요.');$('task-file').value='';return;}uploadingFiles=true;$('task-submit').disabled=true;try{for(const file of files){if(file.size>20*1024*1024)throw new Error(file.name+': 최대 20MB입니다.');$('task-file-name').textContent=file.name+' 읽는 중…';const response=await fetch('/api/upload',{method:'POST',headers:{'X-AIRI-Token':token,'X-AIRI-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file});const value=await response.json();if(!response.ok)throw new Error(value.error);taskFiles.push(value);renderTaskFiles();}toast('참고 파일을 첨부했습니다. 작업 지시를 적고 저장하세요.');}catch(e){toast(e.message);}finally{uploadingFiles=false;$('task-submit').disabled=false;$('task-file-name').textContent=taskFiles.length+'개 파일 첨부됨';$('task-file').value='';}};
function renderHome(){const tasks=state.tasks,today=localDate(new Date());$('home-today').textContent=new Date().toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'});$('stat-today').textContent=tasks.filter(t=>t.due_date===today&&!t.done&&!['cancelled','expired'].includes(t.status)).length;$('stat-scheduled').textContent=tasks.filter(t=>['scheduled','running'].includes(t.status)).length;$('stat-done').textContent=tasks.filter(t=>t.done).length;$('stat-attention').textContent=tasks.filter(t=>['awaiting_approval','failed','unknown','expired','partial'].includes(t.status)).length;const list=$('home-task-list');list.replaceChildren();if(!tasks.length)empty(list,'아직 맡긴 일이 없어요.\n첫 작업을 만들어 보세요.');const priority={partial:2,running:0,awaiting_approval:1,failed:2,unknown:2,scheduled:3,manual:4,completed:5,cancelled:6};for(const t of [...tasks].sort((a,b)=>(priority[a.status]??6)-(priority[b.status]??6)||b.id-a.id).slice(0,6)){const button=el('button','home-task'),dot=el('span','task-status-dot '+t.status),body=el('span','home-task-body');body.append(el('strong','',t.title),el('small','',dueLabel(t)));button.append(dot,body,el('span','task-pill '+t.status,taskStatuses[t.status]||'직접 할 일'));button.onclick=()=>t.result?showTaskResult(t):editTask(t);list.append(button);}$('home-knowledge').textContent='기억 '+state.memories.length+' · 스킬 '+(state.skills||[]).length+' · 첨부 자료 '+(state.attachments||[]).length;}
const originalPlanner=renderPlanner;renderPlanner=function(){originalPlanner();renderHome();};
$('home-new-task').onclick=()=>{resetTask();showPage('memory');$('task-input').focus();};$('home-all-tasks').onclick=()=>showPage('memory');
setInterval(()=>{document.body.classList.toggle('airi-listening',!!recorder&&!transcribing);document.body.classList.toggle('airi-thinking',busy||transcribing);},500);
if(state)renderHome();
async function loadVoicePreferences(){try{const catalog=await api('voices');const prefs=state.settings;$('persona-mode').value=prefs.persona||'free';$('tts-engine').value=prefs.tts_engine||(catalog.neural?'supertonic':'macos');$('neural-voice').value=prefs.neural_voice||'F1';$('tts-speed').value=String(prefs.tts_speed||1.05);syncVoiceControls();$('persona-summary').textContent=$('persona-mode').value==='free'?'편한 말투':'차분한 비서';}catch(e){toast(e.message);}}
async function saveVoicePreferences(){await api('preferences',{persona:$('persona-mode').value,tts_engine:$('tts-engine').value,neural_voice:$('neural-voice').value,tts_speed:Number($('tts-speed').value)});await refresh();$('persona-summary').textContent=$('persona-mode').value==='free'?'편한 말투':'차분한 비서';}
$('preferences-form').onsubmit=async e=>{e.preventDefault();try{await saveVoicePreferences();toast('대화 성격과 목소리를 저장했습니다.');}catch(error){toast(error.message);}};
$('voice-preview').onclick=async()=>{try{await saveVoicePreferences();await api('speak',{text:'안녕, 나는 아이리야. Hello, I am AIRI. Bonjour, je suis AIRI.'});}catch(error){toast(error.message);}};
let preferencesLoaded=false;const preferencesTimer=setInterval(()=>{if(token&&state&&!preferencesLoaded){preferencesLoaded=true;clearInterval(preferencesTimer);loadVoicePreferences();}},300);

async function showTaskResult(task){
  let dialog=$('task-result-dialog');if(dialog)dialog.remove();
  dialog=el('dialog','result-dialog');dialog.id='task-result-dialog';
  const head=el('div','result-heading'),close=el('button','quiet','닫기');close.onclick=()=>dialog.close();
  head.append(el('h2','',task.title+' · 결과'),close);dialog.append(head,el('p','muted',taskStatuses[task.status]||task.status));
  const actions=el('div','form-actions'),download=el('button','secondary','보고서 .md 다운로드');
  const save=(blob,name)=>{const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  download.onclick=()=>save(new Blob([task.result],{type:'text/markdown;charset=utf-8'}),task.title+'.md');const edit=el('button','secondary','일정 편집'),remove=el('button','quiet','일정 삭제');edit.onclick=()=>{dialog.close();editTask(task);};remove.onclick=()=>removeTask(task);actions.append(download,edit,remove);dialog.append(actions,renderResultDocument(task.result));document.body.append(dialog);dialog.showModal();api('task-read',{id:task.id}).catch(()=>{});
  try{const data=await api('task-result/'+task.id);for(const file of data.files){const b=el('button','secondary',file.name);b.onclick=async()=>{try{const r=await fetch('/api/task-file/'+task.id+'/'+file.key,{headers:{'X-AIRI-Token':token}});if(!r.ok)throw new Error('파일 다운로드 실패');save(await r.blob(),file.name);}catch(e){toast(e.message);}};actions.append(b);}}catch(e){toast(e.message);}
}

function renderResultDocument(text){
  const root=el('div','result-body');let table=null;
  for(const line of text.split('\n')){
    if(/^\s*\|/.test(line)){
      if(/^\s*\|[\s:|\-]+$/.test(line))continue;
      if(!table){const wrap=el('div','result-table');table=el('table');wrap.append(table);root.append(wrap);}
      const row=el('tr');for(const cell of line.trim().replace(/^\||\|$/g,'').split('|'))row.append(el(table.rows.length?'td':'th','',cell.trim()));table.append(row);continue;
    }
    table=null;if(!line.trim())continue;
    const heading=line.match(/^(#{1,3})\s+(.*)/);
    if(heading)root.append(el('h'+Math.min(4,heading[1].length+1),'',heading[2]));
    else if(line==='---')root.append(el('hr'));
    else root.append(el('p','',line.replace(/^[-*] /,'• ').replace(/\*\*/g,'')));
  }
  return root;
}

// One canonical profile and an explicit fallback status across all speech paths.
(()=>{
 const panel=el('article','panel');panel.id='voice-profile-panel';panel.append(el('h2','','AIRI 참조 목소리'));
 const status=el('p','muted','참조 음성 준비 상태 확인 중…');status.setAttribute('role','status');panel.append(status);
 const actions=el('div','form-actions');let testing=false;
 for(const [lang,label] of [['en','English'],['ko','한국어'],['fr','Français'],['ja','日本語'],['mixed','혼합 문장']]){
  const button=el('button','secondary',label+' 듣기');button.type='button';
  button.onclick=async()=>{if(testing)return;testing=true;actions.querySelectorAll('button').forEach(b=>b.disabled=true);try{await window.AIRIVoicePlayer.unlock();await interruptSpeech();status.textContent=label+' 테스트 음성 생성 중…';const result=await window.AIRIVoicePlayer.play('AIRI voice test',{test_language:lang,onStart:()=>status.textContent=label+' · 브라우저에서 재생 중'});status.textContent=result.cancelled?'테스트를 중지했습니다.':label+' · 브라우저 재생 완료';}catch(e){status.textContent=e.message;}finally{testing=false;actions.querySelectorAll('button').forEach(b=>b.disabled=false);}};actions.append(button);
 }
 panel.append(actions,el('p','footnote','같은 참조 프로필로 새 문장을 생성합니다. 기본 음성으로 대체되면 아래에 표시합니다.'));
 const stop=el('button','secondary','테스트 중지');stop.type='button';stop.onclick=()=>interruptSpeech();panel.append(stop);
 $('page-setup').append(panel);
 let previous='';window.addEventListener('airi-voice-provider',event=>{const v=event.detail;if(!v?.backend)return;const key=JSON.stringify(v);if(key===previous)return;previous=key;status.textContent=v.fallback?'대체 음성: '+v.backend+' · 참조 목소리와 다름 · '+(v.reason||''):v.backend==='qwen3_reference'?'AIRI 참조 음성 · 생성 '+v.seconds+'초 · '+v.language:'기본 음성: '+v.backend+' · 참조 복제 미사용';});
 const init=setInterval(async()=>{if(!token)return;clearInterval(init);try{const v=await api('voice-profile');status.textContent=v.ready?v.profile+(v.selected==='qwen3_reference'?' · 사용 중':' · 목소리 설정에서 AIRI 참조 음성을 선택하세요.'):'참조 음성 설치 필요 · 기존 음성은 사용 가능합니다.';}catch(e){status.textContent=e.message;}},800);
})();

function syncVoiceControls(){const reference=$('tts-engine').value==='qwen3_reference';for(const id of ['neural-voice','tts-speed']){$(id).disabled=reference;$(id).title=reference?'기본 대체 음성용 설정 · 참조 목소리는 하나의 고정 프로필을 사용합니다.':'';}}
$('tts-engine').addEventListener('change',syncVoiceControls);
