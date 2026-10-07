/* AIRI 2: bounded Home, reusable detail drawers, one runtime presence state. */
(()=>{
 const root=document.querySelector('.airi-console');root.classList.add('companion-shell');
 const office=el('div','office-scene background-layer');office.setAttribute('aria-label','AIRI 배경 환경');office.setAttribute('aria-hidden','true');root.prepend(office);
 const rail=el('nav','companion-rail');rail.setAttribute('aria-label','주 메뉴');
 const brand=el('a','rail-brand');brand.href='/';brand.append(el('strong','','AIRI'),el('span','rail-tagline','Always with you'));rail.append(brand);
 const toggle=el('button','rail-toggle','☰');toggle.title='메뉴 접기 / 펼치기';toggle.setAttribute('aria-label',toggle.title);toggle.setAttribute('aria-expanded','true');toggle.onclick=()=>{const collapsed=root.classList.toggle('rail-collapsed');toggle.setAttribute('aria-expanded',String(!collapsed));};rail.append(toggle);
 const originalShow=showPage;
 const viewNames={tasks:'Tasks · 일정',study:'Study · 학습',markets:'Markets · 시세와 뉴스',work:'Work · 작업',files:'Files · 자료'};
 for(const [id,title] of Object.entries(viewNames)){const page=el('section','page');page.id='page-'+id;page.append(el('h1','detail-title',title));pages[id]=page;$('drawer-body').append(page);names[id]=title;}
 pages.tasks.append($('console-calendar'),$('console-tasks'));
 pages.markets.append(document.querySelector('.console-left').lastElementChild);
 const marketPanel=el('section','console-panel');marketPanel.innerHTML='<div class="console-heading"><h2>WATCHLIST</h2><button id="market-refresh" class="quiet">갱신</button></div><div id="console-markets"></div>';pages.markets.prepend(marketPanel);
 const response=document.querySelector('.response-panel');pages.chat.prepend(response);response.querySelector('.console-heading').remove();
 const transcript=$('messages');transcript.before(el('h2','','대화 기록'));
 const shortcuts=document.querySelector('.console-shortcuts');pages.work.append(shortcuts);
 const create=el('button','primary','새 작업 만들기');create.onclick=()=>$('home-new-task').click();pages.work.prepend(create,el('p','muted','예약 작업과 분석 결과는 Tasks에서, 생성 이미지는 이미지 작업실에서 확인하세요.'));
 const allTasks=el('button','secondary','작업 및 결과 보기');allTasks.onclick=()=>showPage('tasks');pages.work.append(allTasks);
 const skillsLink=el('button','secondary','저장한 스킬 관리');skillsLink.onclick=()=>showPage('memory');pages.study.append(el('p','muted','저장한 학습 스킬을 활용해 한국어·영어·프랑스어로 연습합니다. 아래 목표는 이 브라우저에 저장됩니다.'));
 const goal=el('textarea');goal.rows=3;goal.placeholder='예: TCF 말하기 · 하루 20분';goal.value=localStorage.getItem('airi-study-goal')||'';goal.setAttribute('aria-label','학습 목표');goal.onchange=()=>{localStorage.setItem('airi-study-goal',goal.value);updateCards();};
 const study=el('button','primary','학습 시작');study.onclick=()=>{showPage('home');submitChat((goal.value||'프랑스어 회화')+' 연습을 도와줘. 한 문제씩 진행해줘.');};pages.study.append(goal,study,skillsLink);
 showPage=function(name){if(name==='home'){originalShow(name);}else originalShow(name);for(const b of rail.querySelectorAll('[data-view]')){b.classList.toggle('selected',b.dataset.view===name);if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}};
 for(const [id,label,glyph] of [['home','Home','⌂'],['chat','Chat','◌'],['tasks','Tasks','☑'],['study','Study','▤'],['markets','Markets','↗'],['work','Work','▦'],['files','Files','▱'],['setup','Settings','⚙']]){const b=el('button','rail-link');b.dataset.view=id;b.title=label;b.append(el('span','rail-symbol',glyph),el('span','rail-label',label));b.setAttribute('aria-label',label);b.onclick=()=>showPage(id);rail.append(b);}
 root.append(rail);rail.querySelector('[data-view="home"]').classList.add('selected');
 const header=document.querySelector('.console-header'),clockTime=$('console-clock'),clockDate=$('console-date');header.replaceChildren();const clock=el('div','presence-clock');clock.append(clockTime,clockDate);header.append(clock);
 const statuses=el('div','presence-status');statuses.setAttribute('aria-label','시스템 상태');
 for(const [id,text] of [['presence-voice','Voice · 대기'],['presence-nas','NAS · 확인 중'],['presence-mac1','Mac1 · 확인 중'],['presence-mac2','M1 · AIRI 연결 설정 필요']]){const b=el('button','status-chip',text);b.id=id;b.onclick=()=>showPage(id==='presence-nas'?'files':'setup');statuses.append(b);}header.append(statuses);
 const power=el('button','power-button','일시정지');power.title='자동 듣기와 이 브라우저의 음성 알림 일시정지';header.append(power);
 const column=document.querySelector('.console-right');column.replaceChildren();column.setAttribute('aria-label','상황 카드');
 const center=document.querySelector('.console-center');center.querySelector('.companion-title').remove();
 const welcome=el('div','presence-caption');welcome.innerHTML='<span>YOUR SPACE, TOGETHER.</span><h1>좋은 하루를, User.</h1>';center.prepend(welcome);
 const composer=$('console-composer'),wrap=composer.querySelector('.composer-wrap');
 const preferences=el('article','panel presence-preferences');preferences.append(el('h2','','음성 · 집중 모드'));
 const mic=$('microphone');mic.classList.add('compact-mic');mic.setAttribute('aria-label','음성대화 시작 / 말하기 종료');
 for(const selector of ['.wake-controls','.voice-controls']){const n=wrap.querySelector(selector);if(n)preferences.append(n);}
 $('page-setup').append(preferences);
 const form=$('chat-form');form.prepend(mic);$('message').placeholder='AIRI에게 말하거나 메시지를 남겨주세요…';$('message').rows=1;
 const attachment=el('button','attach-button','＋');attachment.type='button';attachment.title='자료 첨부';attachment.setAttribute('aria-label','자료 첨부');attachment.onclick=()=>{showPage('memory');$('task-file').click();};form.insertBefore(attachment,$('message'));
 const details=el('button','conversation-open','대화 보기');details.type='button';details.onclick=()=>showPage('chat');form.append(details);
 const quick=el('nav','quick-actions');quick.setAttribute('aria-label','빠른 실행');
 for(const [label,glyph,action] of [['새 일정','✓',()=>{resetTask();showPage('memory');$('task-input').focus();}],['프랑스어 학습','▤',()=>{showPage('study');}],['데이터 분석','▥',()=>{resetTask();showPage('memory');$('task-input').value='데이터 분석';$('task-action').value='ai';$('task-instructions').focus();}],['뉴스','◈',()=>{showPage('markets');}],['파일','□',()=>{showPage('files');}]]){const b=el('button','quick-action');b.setAttribute('aria-label',label);b.append(el('span','quick-glyph',glyph),el('span','',label));b.onclick=action;quick.append(b);}
 center.append(quick);
 const modelLabel=$('model').closest('label')||$('model');preferences.append(modelLabel);
 const sceneLabel=el('label','','사무실 시간대'),scene=el('select');scene.setAttribute('aria-label','사무실 시간대');for(const [id,text] of [['auto','Mac 시간에 맞춤'],['morning','아침'],['afternoon','오후'],['evening','저녁'],['night','밤']]){const o=el('option','',text);o.value=id;scene.append(o);}scene.value=localStorage.getItem('airi-environment')||'auto';scene.onchange=()=>{localStorage.setItem('airi-environment',scene.value);updateTime();};sceneLabel.append(scene);preferences.append(sceneLabel);
 const focus=el('label','','집중 모드 · 뉴스/일정 음성 알림 잠시 끄기'),focusInput=el('input');focusInput.type='checkbox';focusInput.checked=localStorage.getItem('airi-focus')==='true';focus.prepend(focusInput);preferences.append(focus);
 let restore=null;function setFocus(value){focusInput.checked=value;window.airiFocus=value;localStorage.setItem('airi-focus',String(value));power.textContent=value?'다시 시작':'일시정지';if(value){restore={news:briefingCheck.checked,reminders:$('schedule-reminders').checked};briefingCheck.checked=false;$('schedule-reminders').checked=false;if(recorder)stopListening(false);voiceSession=false;interruptSpeech();}else if(restore){briefingCheck.checked=restore.news;$('schedule-reminders').checked=restore.reminders;if($('always-listen').checked)startListening(true);}}focusInput.onchange=()=>setFocus(focusInput.checked);power.onclick=()=>setFocus(!focusInput.checked);window.airiFocus=focusInput.checked;
 const integration=el('article','panel');integration.innerHTML='<h2>다음 연결</h2><p>M1 · 이 AIRI에 두 번째 기기의 주소와 인증이 아직 등록되지 않았습니다. Thunderbolt 케이블의 네트워크 연결과 AIRI 앱 연결은 별도입니다. 현재 표시는 케이블 연결 상태를 측정한 결과가 아닙니다.</p><section class="spotify-setup" aria-labelledby="spotify-setup-title"><h3 id="spotify-setup-title">Spotify</h3><p>Client ID만 저장하고, 로그인은 PKCE OAuth 창에서 진행합니다. Client Secret은 AIRI에 입력하지 않습니다.</p><label>Spotify Client ID<input id="spotify-client-id" autocomplete="off" spellcheck="false" placeholder="Spotify Developer Dashboard의 Client ID"></label><div class="spotify-actions"><button id="spotify-save-client" class="secondary" type="button">Client ID 저장</button><button id="spotify-connect" class="primary" type="button">Connect Spotify</button><button id="spotify-disconnect" class="secondary" type="button" hidden>Disconnect</button></div><p id="spotify-oauth-status" class="muted" role="status">Spotify 연결 대기</p><small>Redirect URI: http://127.0.0.1:8765/spotify/callback</small></section><p>캐릭터 런타임 · 현재는 교체 가능한 raster 어댑터와 눈·입·음량 기반 viseme 인터페이스를 사용합니다. 최종 PNG/PSD 또는 Live2D/VRM을 연결해도 홈 레이아웃은 바꾸지 않습니다.</p>';pages.setup.append(integration);
 $('spotify-save-client').onclick=async()=>{try{await window.AIRISpotify.configure($('spotify-client-id').value);$('spotify-oauth-status').textContent='Client ID 저장됨 · Connect Spotify를 눌러 로그인하세요.';toast('Spotify Client ID를 저장했습니다.');}catch(e){toast(e.message);}};
 $('spotify-connect').onclick=()=>window.AIRISpotify.connect();
 $('spotify-disconnect').onclick=async()=>{try{await window.AIRISpotify.disconnect();updateCards();}catch(e){toast(e.message);}};
 window.addEventListener('airi-spotify',e=>{const s=e.detail||{};$('spotify-oauth-status').textContent=s.connected?'Spotify Connected':s.configured?(s.client_id_source==='settings_or_spotify_api_registration'?'기존 Spotify API 등록 확인 · 로그인 필요':'Client ID 저장됨 · 로그인 필요'):'Spotify 연결 대기';$('spotify-connect').disabled=!s.configured;$('spotify-disconnect').hidden=!s.connected;const input=$('spotify-client-id');if(input&&s.configured&&!input.value)input.value=state?.settings?.spotify_client_id||'';});
 const diag=el('pre','presence-diagnostics');diag.textContent='아직 측정된 음성 대화가 없습니다.';preferences.append(el('h3','','대화 지연 측정'),diag);window.addEventListener('airi-latency',e=>{diag.textContent=Object.entries(e.detail).map(([k,v])=>`${k}: ${v??'미측정'}`).join('\n');});
 function card(title,buttonText,action){const c=el('section','context-card'),h=el('div','context-heading');h.append(el('h2','',title));if(action){const b=el('button','quiet',buttonText);b.onclick=action;h.append(b);}c.append(h);return c;}
 let cardSignature='',marketWidgetItems=[],marketWidgetState='loading';
 function miniCalendar(tasks){
  const wrap=el('div','mini-calendar'),head=el('div','mini-calendar-head'),now=new Date();
  head.append(el('strong','',now.toLocaleDateString('ko-KR',{year:'numeric',month:'long'})),el('span','','이번 주'));wrap.append(head);
  const grid=el('div','studio-week');const start=new Date(now);start.setDate(now.getDate()-now.getDay());
  for(let i=0;i<7;i++){const date=new Date(start);date.setDate(start.getDate()+i);const key=localDate(date),b=el('button','studio-weekday'+(key===localDate(now)?' today':''));
   b.append(el('span','',date.toLocaleDateString('ko-KR',{weekday:'short'})),el('strong','',String(date.getDate())));
   b.setAttribute('aria-label',date.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'}));
   if(tasks.some(t=>t.due_date===key&&!t.done))b.classList.add('has-task');
   b.onclick=()=>{selectedDate=key;calendarMonth=new Date(date.getFullYear(),date.getMonth(),1);showPage('tasks');renderPlanner();};grid.append(b);
  }wrap.append(grid);return wrap;
 }

 function updateCards(){if(!state)return;const tasks=state.tasks||[],active=tasks.find(t=>t.status==='running')||tasks.find(t=>t.status==='awaiting_approval');const upcoming=tasks.filter(t=>!t.done&&t.due_date&&(!t.status||!['cancelled','expired','failed','completed'].includes(t.status))&&new Date(t.due_date+'T'+(t.end_time||t.due_time||'23:59')).getTime()>=Date.now()).sort((a,b)=>(a.due_date+(a.due_time||'')).localeCompare(b.due_date+(b.due_time||''))).slice(0,3);const signature=JSON.stringify([upcoming,active,goal.value,tasks,localDate(new Date()),window.AIRISpotify?.status(),marketWidgetState,marketWidgetItems]);if(signature===cardSignature||column.contains(document.activeElement))return;cardSignature=signature;column.replaceChildren();
 const today=card('일정','달력 열기',()=>showPage('tasks'));today.classList.add('today-widget');today.append(miniCalendar(tasks));const agenda=el('div','widget-agenda');for(const t of upcoming.slice(0,3)){const b=el('button','agenda-item');b.append(el('time','',t.due_date.slice(5)+' · '+(t.due_time||'종일')),el('strong','',t.title));b.onclick=()=>editTask(t);agenda.append(b);}if(!upcoming.length)agenda.append(el('p','context-empty','오늘 예정된 일정이 없어요.'));today.append(agenda);column.append(today);
 const music=card('음악','연결 설정',()=>window.AIRISettings?window.AIRISettings.open('music'):showPage('setup'));music.classList.add('music-widget');
 const musicRow=el('div','music-row'),musicInfo=el('div','music-info'),spotifyState=window.AIRISpotify?.status()||{connected:false};
 const deviceLabel=spotifyState.device||((spotifyState.devices||[]).length?'재생 기기 미선택':'활성 재생 기기 없음');
 const musicDetail=spotifyState.track?(spotifyState.track+' · '+(spotifyState.artist||'')+' · '+deviceLabel):(spotifyState.connected?'연결됨 · '+deviceLabel+' · Spotify에서 이 Mac의 재생을 시작하세요':(spotifyState.error||'Spotify 앱에서 음악을 재생하면 현재 곡이 표시됩니다.'));
 musicInfo.append(el('strong','',spotifyState.track||(spotifyState.connected?'재생을 기다리는 중':spotifyState.configured?'Spotify 로그인 필요':'Spotify 연결 대기')),el('small','',musicDetail));music.dataset.playing=String(!!spotifyState.playing);
 const previous=el('button','music-play','◀');previous.disabled=!spotifyState.connected;previous.setAttribute('aria-label','이전 곡');previous.onclick=()=>window.AIRISpotify.command('previous').then(()=>{cardSignature='';updateCards();}).catch(e=>toast(e.message));
 const play=el('button','music-play',spotifyState.playing?'Ⅱ':'▶');play.disabled=!spotifyState.connected;play.setAttribute('aria-label','음악 재생 / 일시정지');play.onclick=async()=>{play.disabled=true;try{await window.AIRISpotify.command(spotifyState.playing?'pause':'play');}catch(e){toast(e.message);}finally{cardSignature='';updateCards();}};
 const next=el('button','music-play','▶');next.disabled=!spotifyState.connected;next.setAttribute('aria-label','다음 곡');next.onclick=()=>window.AIRISpotify.command('next').then(()=>{cardSignature='';updateCards();}).catch(e=>toast(e.message));
 musicRow.append(el('div','album-art','♫'),musicInfo,previous,play,next);music.append(musicRow);
 const output=spotifyState.audio_output||{},currentOutput=output.current;
 music.append(el('small','',currentOutput?'Mac 소리 출력 · '+currentOutput.name:'Mac 소리 출력 확인 중'));
 const controls=el('div','spotify-device-controls'),devices=el('select');devices.setAttribute('aria-label','블루투스 오디오 출력');
 const empty=el('option','','블루투스 스피커 / 이어폰 선택');empty.value='';devices.append(empty);
 for(const device of output.devices||[]){const option=el('option','',device.name+(device.type==='builtin'?' · 내장':' · Bluetooth')+(device.active?' · 사용 중':''));option.value=device.id;devices.append(option);}devices.value=currentOutput?.id||'';
 devices.onchange=async()=>{if(!devices.value)return;devices.disabled=true;try{await window.AIRISpotify.command('audio_output',{output_id:devices.value});toast('Mac 소리 출력을 변경했어. 이 Mac의 음악과 아이리 음성이 선택한 기기로 나가.');}catch(e){toast(e.message);}finally{devices.disabled=false;cardSignature='';updateCards();}};
 const retry=el('button','quiet','새로고침');retry.onclick=()=>window.AIRISpotify.refresh().catch(e=>toast(e.message));controls.append(devices,retry);music.append(controls);
 const bluetooth=el('button','homepod-open','블루투스 연결 설정');bluetooth.onclick=()=>window.AIRISpotify.command('bluetooth_settings').catch(e=>toast(e.message));music.append(bluetooth);
 music.append(el('small','',output.error||((output.devices||[]).some(d=>d.type==='bluetooth')?'음악은 이 Mac에서 재생해 줘. 다른 기기에서 재생 중인 음악은 전환되지 않아.':'연결된 블루투스 오디오 기기가 없어. 연결 설정에서 페어링한 뒤 새로고침해 줘.')));
 column.append(music);
 const watch=card('관심 종목','관리',()=>showPage('markets'));watch.classList.add('watch-widget');
 if(!marketWidgetItems.length)watch.append(el('p','context-empty',marketWidgetState==='loading'?'시세 조회 중…':marketWidgetState==='error'?'시세를 확인하지 못했어요. 관리에서 다시 조회하세요.':'등록된 관심 종목이 없어요.'));
 for(const item of marketWidgetItems.slice(0,4)){const row=el('div','watch-row');const valid=!item.error&&Number.isFinite(item.price),change=valid&&Number.isFinite(item.regularMarketChangePercent)?item.regularMarketChangePercent:null;
 row.append(el('strong','',item.symbol||item.label),el('span','',valid?item.price.toLocaleString(undefined,{maximumFractionDigits:2})+' '+(item.currency||''):'조회 실패'),el('em',change===null?'flat':change<0?'down':'up',change===null?'—':(change>0?'+':'')+change.toFixed(2)+'%'));
 row.title=item.error||((item.as_of?'기준 '+item.as_of:'기준 시각 미제공')+(item.stale?' · 이전 시세':''));watch.append(row);}
 const quoteDate=marketWidgetItems.filter(i=>i.as_of).map(i=>new Date(i.as_of)).sort((a,b)=>a-b)[0];watch.append(el('small','widget-note',(quoteDate&&!isNaN(quoteDate)?'시세 기준 '+quoteDate.toLocaleString('ko-KR',{timeZone:'UTC',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · ':'')+'Yahoo · 지연 가능'));column.append(watch);
 const learning=card(active?'작업 현황':'학습','자세히',()=>showPage(active?'tasks':'study'));learning.classList.add('learning-widget');
 learning.append(el('div','study-mark',active?'↗':'▤'),el('strong','',active?.title||goal.value||'학습 목표를 정해보세요'),el('p','',active?(active.status==='running'?'Mac1에서 실행 중':'실행 승인 대기'):goal.value?'목표를 저장했어요. 학습을 시작할 수 있어요.':'목표를 저장하고 AIRI와 연습하세요.'));column.append(learning);window.dispatchEvent(new CustomEvent('airi-home-cards'));
 }
 const oldRender=render;render=function(){oldRender();updateCards();};
 function updateTime(){const phase=scene.value==='auto'?window.AIRIAssets.phase(new Date().getHours()):scene.value;if(root.dataset.environment!==phase){root.dataset.environment=phase;window.dispatchEvent(new CustomEvent('airi-environment',{detail:{phase}}));}welcome.querySelector('h1').textContent=({morning:'좋은 아침, User.',afternoon:'오늘도 함께, User.',evening:'편안한 저녁, User.',night:'조용한 밤, User.'})[phase];}updateTime();setInterval(()=>{updateTime();updateCards();},60000);
 const runtime={state:'IDLE',emotion:'neutral',intensity:0,expires:0,speaking:false,lastInteraction:Date.now()};window.airiPresence=runtime;
 document.addEventListener('pointerdown',()=>runtime.lastInteraction=Date.now());document.addEventListener('keydown',()=>runtime.lastInteraction=Date.now());
 const outputStatus=el('div','voice-output-status');outputStatus.setAttribute('role','status');outputStatus.hidden=true;$('console-composer').prepend(outputStatus);
 const enableAudio=el('button','quiet','음성 켜기');enableAudio.type='button';enableAudio.onclick=()=>window.AIRIVoicePlayer.unlock().then(()=>{outputStatus.hidden=false;outputStatus.textContent='브라우저 음성 재생 준비됨';}).catch(e=>toast(e.message));preferences.append(enableAudio);
 window.addEventListener('airi-speech-state',e=>{runtime.speaking=!!e.detail.speaking;runtime.preparing=!!e.detail.preparing;runtime.voiceAt=Date.now();outputStatus.hidden=!(runtime.speaking||runtime.preparing);if(!outputStatus.hidden)outputStatus.textContent=runtime.speaking?'AIRI가 말하고 있어요':(e.detail.wait_seconds>=5?'응답이 늦어지고 있어요…':'잠깐만…');});window.addEventListener('airi-speech-finished',()=>{runtime.speaking=false;runtime.preparing=false;outputStatus.hidden=true;});
 window.addEventListener('airi-emotion',e=>{if(window.AIRICharacterRuntime.emotions.includes(e.detail.name)){runtime.emotion=e.detail.name;runtime.intensity=Math.min(1,Math.max(0,e.detail.intensity??.3));runtime.expires=Date.now()+5000;}});
 const labels={IDLE:'대기',LISTENING:'듣는 중',THINKING:'생각 중',SPEAKING:'말하는 중',WORKING:'작업 중',STUDYING:'학습 중',RELAXING:'휴식',SLEEPY:'조용히 대기'};
 setInterval(()=>{const active=state?.tasks?.some(t=>t.status==='running');if(Date.now()-(runtime.voiceAt||0)>1500)runtime.speaking=false;runtime.state=runtime.speaking?'SPEAKING':recorder&&!wakeWaiting?'LISTENING':busy||transcribing?'THINKING':active?'WORKING':pages.study.classList.contains('active')&&drawer.open?'STUDYING':Date.now()-runtime.lastInteraction>90000?(root.dataset.environment==='night'?'SLEEPY':'RELAXING'):'IDLE';if(Date.now()>runtime.expires){runtime.intensity=0;runtime.emotion='neutral';}root.dataset.presence=runtime.state;$('presence-voice').textContent='Voice · '+labels[runtime.state];$('presence-voice').dataset.active=String(['SPEAKING','LISTENING'].includes(runtime.state));window.dispatchEvent(new CustomEvent('airi-presence',{detail:{...runtime}}));},200);
  async function nodeStatus(){if(!token)return;try{const data=await api('companion/status');$('presence-nas').textContent='NAS · '+(data.nas.connected?'연결됨':'오프라인');$('presence-mac1').textContent=(data.node||'Mac')+' · '+(data.standby?'이전 점검 중':'연결됨');$('presence-mac2').textContent='M1 · '+(data.mac2?.connected?'작업자 연결됨':data.mac2?.state==='unconfigured'?'AIRI 연결 설정 필요':data.mac2?.state==='checking'?'확인 중':'작업자 오프라인');$('presence-mac2').title=(data.mac2?.hardware||'M1')+' · SSH로 인증한 작업자 상태 · '+(data.mac2?.routing?.enabled?'백그라운드 분산 켜짐':'분산 꺼짐');$('presence-mac1').title='API '+data.counts.apis+' · 스킬 '+data.counts.skills+' · '+data.data_home;window.airiNodeStatus=data;}catch(e){$('presence-mac1').textContent='Mac1 · 응답 없음';$('presence-nas').textContent='NAS · 확인 불가';$('presence-mac2').textContent='Mac2 · 확인 불가';}}setInterval(nodeStatus,15000);setTimeout(nodeStatus,1500);
 window.addEventListener('airi-markets',e=>{marketWidgetItems=e.detail.items||[];marketWidgetState=e.detail.error?'error':'ready';updateCards();});
 window.addEventListener('airi-spotify',()=>updateCards());
 window.addEventListener('airi-saved',e=>{if(e.detail.kind==='task')showPage('tasks');});
 window.addEventListener('airi-image-job',()=>showPage('chat'));
 if(state)updateCards();
})();
