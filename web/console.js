/* One workspace, with existing editors kept in accessible native dialogs. */
const consoleRoot=el('section','airi-console');
consoleRoot.innerHTML=`<header class="console-header"><a href="/" class="console-brand">AIRI<span>PERSONAL INTELLIGENCE</span></a><div id="console-clock"></div><button id="console-settings" class="secondary">연결 · 설정</button></header><div class="console-grid"><aside class="console-left"><section id="console-calendar" class="console-panel"></section><section class="console-panel"><div class="console-heading"><h2>NEWS</h2><button id="news-refresh" class="quiet">조회</button></div><div id="console-news" class="subtle">캐나다와 미국의 주요 뉴스</div></section></aside><section class="console-center"><div class="face-stage"><div class="orbit orbit-outer"></div><div class="orbit orbit-inner"></div><div class="face-frame"><div class="face-motion"><img src="/assets/airi-cyber.png" alt="AIRI" width="1254" height="1254"><img class="face-blink" src="/assets/airi-cyber-blink.png" alt="" aria-hidden="true" width="1254" height="1254"><img class="face-talk" src="/assets/airi-cyber-talk.png" alt="" aria-hidden="true" width="1254" height="1254"></div></div><span class="face-status" id="face-status" role="status">대기 중</span></div><div class="companion-title"><h1>A I R I</h1></div><div id="console-composer"></div></section><aside class="console-right"><section id="console-tasks" class="console-panel"></section><section class="console-panel response-panel"><div class="console-heading"><h2>CONVERSATION</h2><button id="console-history" class="quiet">전체 기록</button></div><div id="console-response" aria-live="polite">편하게 말해 주세요. 무엇부터 함께 할까요?</div><div id="console-evidence"></div></section><div class="console-shortcuts"><button id="console-memory" class="secondary">기억 · 파일</button><button id="console-approvals" class="secondary">실행 승인</button><button id="console-activity" class="secondary">활동</button></div></aside></div><footer class="console-footer"><span id="console-connection">연결 확인 중</span><span>VANCOUVER <span id="console-date"></span></span></footer>`;
document.body.prepend(consoleRoot);
const drawer=el('dialog','console-drawer');drawer.innerHTML='<div class="drawer-head"><h2 id="drawer-title">작업실</h2><button id="drawer-close" class="secondary">닫기</button></div><div id="drawer-body"></div>';document.body.append(drawer);
const pages={};for(const id of ['memory','setup','automation','activity','chat']){pages[id]=$('page-'+id);$('drawer-body').append(pages[id]);}
$('console-calendar').append(document.querySelector('.calendar-panel'));
$('console-tasks').append(document.querySelector('.task-overview'));
$('console-composer').append(document.querySelector('.composer-wrap'));
const newTask=$('home-new-task');newTask.textContent='새 작업';$('console-tasks').append(newTask);
$('drawer-body').append(document.querySelector('.voice-preferences'));
showPage=function(name){if(name==='home'){drawer.close();return;}if(name==='chat')renderMessages();for(const [id,page] of Object.entries(pages))page.classList.toggle('active',id===name);document.querySelector('.voice-preferences').hidden=name!=='setup';$('drawer-title').textContent=names[name]||'작업실';if(!drawer.open)drawer.showModal();if(name==='setup')health().catch(e=>toast(e.message));};
$('drawer-close').onclick=()=>drawer.close();drawer.addEventListener('click',e=>{if(e.target===drawer)drawer.close();});
for(const [id,page] of [['console-settings','setup'],['console-memory','memory'],['console-approvals','automation'],['console-activity','activity'],['console-history','chat']])$(id).onclick=()=>showPage(page);
const previousRender=render;render=function(){previousRender();renderConsole();};
function renderConsole(){if(!state)return;const last=state.messages.filter(m=>m.role==='assistant').at(-1);if(last&&!busy)$('console-response').textContent=last.content;const pending=state.approvals.filter(a=>a.status==='pending').length;$('console-approvals').textContent='실행 승인'+(pending?' '+pending:'');$('console-connection').textContent=$('connection').textContent;}
new MutationObserver(()=>{const last=$('messages').querySelector('.message.assistant:last-child .message-text');if(last&&busy)$('console-response').textContent=last.textContent;}).observe($('messages'),{childList:true,subtree:true,characterData:true});
function renderEvidence(cards){const host=$('console-evidence');host.replaceChildren();for(const c of cards){const item=el('div','evidence');item.append(el('strong','',c.symbol||c.base+'/'+c.quote),el('small','',(c.as_of||'')+' · '+(c.source||'')));if(c.source_url){const a=el('a','','출처 열기');a.href=c.source_url;a.target='_blank';a.rel='noreferrer';item.append(a);}host.append(item);}}
window.addEventListener('airi-evidence',e=>renderEvidence(e.detail));
let speechPollActive=false;
async function pollSpeechState(){
 let delay=1500;
 try{if(document.hidden||!token||window.airiBrowserSpeech)return;
  const s=await api('speech-state');if(window.airiBrowserSpeech)return;
  delay=s.speaking?180:1500;document.body.classList.toggle('airi-speaking',s.speaking);
  document.body.style.setProperty('--mouth-level',s.level||0);
  window.dispatchEvent(new CustomEvent('airi-speech-state',{detail:s}));
  const label=s.speaking?'말하고 있어요':transcribing?'듣고 이해하는 중':busy?'생각하는 중':recorder?'듣고 있어요':'대기 중';
  if($('face-status').textContent!==label)$('face-status').textContent=label;
 }catch(e){$('face-status').textContent='연결 확인 필요';}finally{setTimeout(pollSpeechState,delay);}
}pollSpeechState();
function consoleClock(){const d=new Date();$('console-clock').textContent=d.toLocaleTimeString('en-CA',{hour:'2-digit',minute:'2-digit',hour12:false});$('console-date').textContent=d.toLocaleDateString('en-CA');}consoleClock();setInterval(consoleClock,30000);
const newsCategories=[['canada','캐나다'],['us','미국'],['business','경제'],['technology','기술·과학']];
const newsData={},newsErrors={},newsUnchanged={};let newsSelected='canada',newsLoading=false,newsInitialized=false;
const newsTabs=el('div','news-categories');newsTabs.setAttribute('role','group');newsTabs.setAttribute('aria-label','뉴스 카테고리');
for(const [id,label] of newsCategories){const b=el('button','quiet',label);b.dataset.category=id;b.onclick=()=>{newsSelected=id;renderNews();if(newsInitialized)refreshNews(false,id);};newsTabs.append(b);}
$('console-news').before(newsTabs);
const newsProgress=el('p','news-progress','최근 24시간 뉴스 · 전체 분류를 30초마다 확인합니다.');newsProgress.setAttribute('aria-live','polite');$('console-news').before(newsProgress);
const briefingToggle=el('label','news-briefing-toggle'),briefingCheck=el('input');briefingCheck.type='checkbox';briefingCheck.checked=localStorage.getItem('airi-news-briefing')!=='false';briefingCheck.onchange=()=>localStorage.setItem('airi-news-briefing',String(briefingCheck.checked));briefingToggle.append(briefingCheck,el('span','','중요 뉴스 자동 브리핑'));
const briefingCard=el('div','news-briefing-card');briefingCard.hidden=true;$('console-news').after(briefingToggle,el('p','news-note','중요 소식을 본문·출처로 검증한 뒤 사건별로 알려 줍니다. 검증되지 않은 제목은 읽지 않습니다. 같은 사건은 한 번 · 최소 30분 간격.'),briefingCard);
function newsTime(value){return value?new Date(value).toLocaleString('ko-KR',{timeZone:'UTC',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'발행 시각 미제공';}
function renderNews(){
 for(const b of newsTabs.children)b.setAttribute('aria-pressed',String(b.dataset.category===newsSelected));
 const host=$('console-news'),data=newsData[newsSelected];host.replaceChildren();
 if(!data){host.append(el('p','',newsErrors[newsSelected]||'뉴스를 불러오는 중…'));return;}
 host.append(el('p','news-meta',data.source+' · 확인 '+newsTime(data.checked_at)+' (설정한 지역)'));
 if(newsErrors[newsSelected]||data.stale)host.append(el('p','news-warning',newsErrors[newsSelected]||data.error));
 if(data.failed_sources?.length)host.append(el('p','news-warning','일부 출처 연결 실패: '+data.failed_sources.join(', ')));
 else if(newsUnchanged[newsSelected])host.append(el('p','news-note','새 기사 없음 · 기존 최신 기사를 유지합니다.'));
 const newest=data.items.find(i=>i.published);if(newest&&Date.now()-Date.parse(newest.published)>86400000)host.append(el('p','news-warning','최근 발행 기사가 24시간 이상 전입니다.'));
 const recent=data.items.filter(i=>i.published&&Date.now()-Date.parse(i.published)>=0&&Date.now()-Date.parse(i.published)<=86400000);
 if(!recent.length)host.append(el('p','news-warning','최근 24시간 내 확인된 기사가 없습니다. 다음 갱신 때 다시 확인합니다.'));
 for(const item of recent.slice(0,5)){const row=el('div','feed-row'),a=el('a','',item.title);a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';const minutes=Math.max(0,Math.floor((Date.now()-Date.parse(item.published))/60000));const age=minutes<1?'방금':minutes<60?minutes+'분 전':Math.floor(minutes/60)+'시간 전';row.append(a,el('small','',item.source+' · '+age+' · 발행 '+newsTime(item.published)));if(item.importance)row.append(el('span','news-important',item.importance));host.append(row);}
}
async function refreshNews(force=false,category=null){
 if(newsLoading||!token)return;newsLoading=true;$('news-refresh').disabled=true;
 const categories=category?newsCategories.filter(([id])=>id===category):newsCategories;
 try{for(const [id,label] of categories){newsProgress.textContent=label+' 뉴스 확인 중…';try{const data=await api('dashboard/news/'+id+(force?'?refresh=1':''));const old=newsData[id];newsUnchanged[id]=!!old&&JSON.stringify(old.items)===JSON.stringify(data.items);newsData[id]=data;delete newsErrors[id];}catch(e){newsErrors[id]='연결 실패 · '+(newsData[id]?'이전 기사를 표시합니다.':'다음 차례에 다시 시도합니다.');}if(newsSelected===id)renderNews();}newsInitialized=true;}
 finally{newsLoading=false;$('news-refresh').disabled=false;newsProgress.textContent='30초마다 전체 확인 · 최근 24시간 · RSS 발행 지연 가능';}
}
$('news-refresh').textContent='전체 갱신';$('news-refresh').onclick=()=>refreshNews(true);renderNews();
const newsStartTimer=setInterval(()=>{if(token&&!newsLoading){clearInterval(newsStartTimer);refreshNews(true);}},1000);
setInterval(()=>{if(!document.hidden)refreshNews();},30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&newsInitialized)refreshNews(true);});
let newsBriefingBusy=false;
setInterval(async()=>{
 if(window.airiReportReading||window.airiFocus||newsBriefingBusy||newsLoading||!newsInitialized||!token||!briefingCheck.checked||document.hidden||busy||transcribing||voiceStarting||(recorder&&!wakeWaiting)||reminderPolling)return;
 newsBriefingBusy=true;let resume=false;
 try{const {briefing}=await api('news-briefing',{});if(!briefing)return;briefingCard.replaceChildren(el('strong','','AIRI · 중요 뉴스'),el('p','',briefing.importance));const link=el('a','',briefing.title);link.href=briefing.url;link.target='_blank';link.rel='noopener noreferrer';briefingCard.append(link,el('small','',briefing.source+' · 발행 '+newsTime(briefing.published)));if(briefing.report){const details=el('details'),report=el('pre','intelligence-report',briefing.report);report.style.whiteSpace='pre-wrap';report.style.overflowWrap='anywhere';report.style.maxHeight='60vh';report.style.overflow='auto';details.append(el('summary','','전체 분석 보기'),report);briefingCard.append(details);}briefingCard.hidden=false;toast(briefing.text);
  if('Notification' in window&&Notification.permission==='granted'){try{new Notification('AIRI · 중요 뉴스',{body:briefing.title,tag:briefing.url});}catch(e){/* The on-screen briefing remains available. */}}
  if($('auto-speak').checked){resume=!!recorder&&wakeWaiting;if(resume)await stopListening(false);await api('speak',{text:briefing.text});while((await api('speech-state')).speaking)await new Promise(r=>setTimeout(r,250));}
 }catch(e){newsProgress.textContent='중요 뉴스 브리핑 연결을 확인하지 못했습니다.';}
 finally{newsBriefingBusy=false;if(resume&&!recorder&&!busy&&!transcribing&&voiceSession)startListening(true);}
},15000);
if(state)renderConsole();

let nextBlink;function scheduleBlink(){clearTimeout(nextBlink);nextBlink=setTimeout(()=>{if(!document.hidden){document.body.classList.add('airi-blinking');setTimeout(()=>document.body.classList.remove('airi-blinking'),155);}scheduleBlink();},2800+Math.random()*5200);}scheduleBlink();

window.addEventListener('airi-saved',e=>{const result=e.detail,host=$('console-evidence');host.replaceChildren();const receipt=el('div','evidence');receipt.append(el('strong','',result.kind==='task'?'일정 저장 완료':'스킬 저장 완료'),el('small','',result.kind==='task'?`${result.due_date}${result.last_date?' ~ '+result.last_date:''} ${result.due_time}${result.end_time?'~'+result.end_time:''} · ${result.title}${result.count?' · '+result.count+'개':''}`:result.name));const button=el('button','secondary',result.kind==='task'?'달력에서 보기':'스킬 확인');button.onclick=()=>{if(result.kind==='task'){selectedDate=result.due_date;calendarMonth=new Date(result.due_date+'T12:00:00');calendarMonth.setDate(1);renderPlanner();showPage('home');$('console-calendar').scrollIntoView({behavior:'smooth',block:'nearest'});}else showPage('memory');};receipt.append(button);host.append(receipt);});

$('schedule-reminders').checked=localStorage.getItem('airi-schedule-reminders')!=='false';
$('schedule-reminders').onchange=()=>localStorage.setItem('airi-schedule-reminders',String($('schedule-reminders').checked));
$('notification-permission').onclick=async()=>{if(!('Notification' in window)){toast('이 브라우저는 시스템 알림을 지원하지 않습니다. 화면·음성 알림은 사용할 수 있어요.');return;}const permission=await Notification.requestPermission();toast(permission==='granted'?'Mac 알림을 켰습니다.':'화면·음성 알림으로 알려드릴게요.');};
let reminderPolling=false;
setInterval(async()=>{if(window.airiReportReading||newsBriefingBusy||reminderPolling||!token||!$('schedule-reminders').checked||busy||transcribing||voiceStarting||(recorder&&!wakeWaiting))return;reminderPolling=true;let resume=false;try{const result=await api('reminder-claim',{});if(!result.reminder)return;const notice=result.reminder;toast(notice.text,()=>{selectedDate=notice.due_date;calendarMonth=new Date(notice.due_date+'T12:00:00');calendarMonth.setDate(1);renderPlanner();showPage('home');});if('Notification' in window&&Notification.permission==='granted')new Notification('AIRI · 일정 알림',{body:notice.text,tag:'airi-reminder-'+notice.id});if($('auto-speak').checked){resume=!!recorder&&wakeWaiting;if(resume)await stopListening(false);await api('speak',{text:notice.text});while((await api('speech-state')).speaking)await new Promise(r=>setTimeout(r,250));}}catch(e){toast('일정 알림: '+e.message);}finally{reminderPolling=false;if(resume&&!recorder&&!busy&&!transcribing&&voiceSession)startListening(true);}},15000);

// A bounded background briefing job; headline cards and existing navigation stay intact.
(()=>{
 const bar=el('div','news-categories'),select=el('select'),start=el('button','quiet','분석 브리핑 만들기'),status=el('span','news-note','본문·사건 통합·출처 검증 · 로컬 분석');
 const profiles=[['morning','Morning'],['evening','Evening'],['breaking','Breaking'],['market','Market'],['technology','AI & Technology'],['canada','Canada'],['korea','Korea'],['company','Company']];
 for(const [id,label] of profiles){const option=el('option','',label);option.value=id;select.append(option);}select.setAttribute('aria-label','브리핑 종류');
 const company=el('input');company.placeholder='기업명 (예: NVIDIA)';company.setAttribute('aria-label','기업명');company.hidden=true;select.onchange=()=>{company.hidden=select.value!=='company';};
 const details=el('details'),summary=el('summary','','최근 분석 브리핑'),body=el('pre','intelligence-report');body.style.whiteSpace='pre-wrap';body.style.overflowWrap='anywhere';body.style.maxHeight='60vh';body.style.overflow='auto';details.append(summary,body);details.hidden=true;bar.append(select,company,start,status);$('console-news').before(bar,details);
 let timer=null,retry=false;
 async function poll(id){try{const job=await api('intelligence?id='+encodeURIComponent(id));status.textContent=job.progress||job.state;if(job.state==='completed'){clearInterval(timer);timer=null;start.disabled=false;body.textContent=job.text;details.hidden=false;details.open=true;}else if(job.state==='failed'){clearInterval(timer);timer=null;start.disabled=false;retry=true;status.textContent=job.error||'분석 실패';}}catch(error){clearInterval(timer);timer=null;start.disabled=false;status.textContent=error.message;}}
 start.onclick=async()=>{start.disabled=true;status.textContent='브리핑 준비 중';try{const job=await api('intelligence',{profile:select.value,company:select.value==='company'?company.value.trim():null,force:retry});await poll(job.id);if(start.disabled)timer=setInterval(()=>poll(job.id),5000);}catch(error){start.disabled=false;status.textContent=error.message;}};
 function restoreBrief(attempt=0){if(!token){if(attempt<20)setTimeout(()=>restoreBrief(attempt+1),500);return;}api('intelligence').then(data=>{if(data.latest){body.textContent=data.latest.text;details.hidden=false;}}).catch(()=>{});}restoreBrief();
 window.addEventListener('pagehide',()=>clearInterval(timer));
})();
