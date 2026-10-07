/* Personal AIRI UI adapter. Reuses existing controls and authenticated APIs. */
(()=>{
 'use strict';
 const body=document.body,html=document.documentElement;
 body.classList.add('apple-ui');body.dataset.appleView='chat';
 let saved={};try{const value=JSON.parse(localStorage.getItem('airi-ui-preferences')||'{}');if(value&&typeof value==='object')saved=value;}catch{}
 if(!['system','light','dark'].includes(saved.appearance))saved.appearance='system';
 if(!['13','15','17','20'].includes(String(saved.size)))saved.size='15';
 if(!['ko','en','fr'].includes(saved.language))saved.language='ko';
 const ui={appearance:saved.appearance||'system',size:saved.size||'15',language:saved.language||'ko',reduceMotion:!!saved.reduceMotion,reduceTransparency:!!saved.reduceTransparency,highContrast:!!saved.highContrast,sidebarCollapsed:!!saved.sidebarCollapsed};
 function apply(){html.dataset.appearance=ui.appearance;html.dataset.reduceMotion=String(ui.reduceMotion);html.dataset.reduceTransparency=String(ui.reduceTransparency);html.dataset.highContrast=String(ui.highContrast);html.dataset.sidebarCollapsed=String(ui.sidebarCollapsed);html.style.setProperty('--chat-size',ui.size+'px');localStorage.setItem('airi-ui-preferences',JSON.stringify(ui));}
 apply();
 const labels={ko:{home:'아바타',chat:'대화',tasks:'일정',study:'학습',markets:'시장',work:'작업',files:'파일',setup:'설정',search:'검색',controls:'제어 센터',inspector:'맥락 보기',newChat:'새 대화'},en:{home:'Avatar',chat:'Chat',tasks:'Calendar',study:'Study',markets:'Markets',work:'Work',files:'Files',setup:'Settings',search:'Search',controls:'Control Center',inspector:'Context',newChat:'New chat'},fr:{home:'Avatar',chat:'Discussion',tasks:'Calendrier',study:'Étude',markets:'Marchés',work:'Travail',files:'Fichiers',setup:'Réglages',search:'Rechercher',controls:'Centre de contrôle',inspector:'Contexte',newChat:'Nouvelle discussion'}};
 const button=(text,action,cls='')=>{const b=el('button',cls,text);b.type='button';b.onclick=action;return b;};
 const row=(title,control,description='')=>{const r=el('div','apple-row'),l=el('label','',title);if(description)l.append(el('small','',description));if(control.id)l.htmlFor=control.id;r.append(l,control);return r;};
 const select=(id,values,current,change)=>{const s=el('select');s.id=id;for(const [value,label] of values){const o=el('option','',label);o.value=value;s.append(o);}s.value=current;s.onchange=()=>change(s.value);return s;};
 const toggle=(id,value,change)=>{const c=el('input');c.id=id;c.type='checkbox';c.checked=value;c.onchange=()=>change(c.checked);return c;};
 const header=document.querySelector('.console-header'),composer=document.querySelector('.composer-wrap'),homeComposer=$('console-composer');
 const sidebarButton=button('☰',()=>{ui.sidebarCollapsed=!ui.sidebarCollapsed;apply();sidebarButton.setAttribute('aria-expanded',String(!ui.sidebarCollapsed));});sidebarButton.setAttribute('aria-label','사이드바 접기 또는 펼치기');sidebarButton.setAttribute('aria-expanded',String(!ui.sidebarCollapsed));header.prepend(sidebarButton);
 const mic=el('span','apple-mic','마이크 꺼짐');mic.setAttribute('role','status');mic.setAttribute('aria-live','polite');header.append(mic);
 let lastMind=null,lastSI=null,currentSettings='general',inspectorMode='state';
 const quickButton=button('검색',()=>openLauncher());quickButton.title='⌘K';header.append(quickButton);
 const controlButton=button('제어 센터',()=>openControls());header.append(controlButton);
 const inspectorButton=button('맥락 보기',()=>{inspectorMode='state';inspector.classList.toggle('open');inspectorButton.setAttribute('aria-expanded',String(inspector.classList.contains('open')));if(inspector.classList.contains('open'))loadStatus();});inspectorButton.setAttribute('aria-expanded','false');
 $('drawer-title').after(inspectorButton);
 const newButton=button('새 대화',()=>newConversation());$('drawer-title').after(newButton);
 const inspector=el('aside','apple-inspector');inspector.setAttribute('aria-label','대화 맥락');const inspectorClose=button('닫기',()=>inspector.classList.remove('open'));const inspectorBody=el('div');inspector.append(inspectorClose,el('h2','','대화 맥락'),inspectorBody);$('drawer-body').append(inspector);
 const oldRenderMessages=renderMessages;
 renderMessages=function(){if(!state)return;const all=state.messages;try{state.messages=all.filter(m=>m.id>(state.settings.context_start_id||0));oldRenderMessages();if(!state.messages.length){const empty=el('div','apple-empty');empty.append(el('h2','','무엇부터 할까요'),button('오늘 일정',()=>showPage('tasks')),button('이전 대화 찾기',()=>openLauncher('@ ')),button('아이리에게 질문',()=>$('message').focus()));$('messages').append(empty);}}finally{state.messages=all;}};
 showPage=function(name){
  if(!pages[name]&&name!=='home')return;
  body.dataset.appleView=name;
  for(const [key,page] of Object.entries(pages))page.classList.toggle('active',key===name);
  for(const b of document.querySelectorAll('.rail-link')){const active=b.dataset.view===name;b.classList.toggle('selected',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
  if(name==='home'){if(drawer.open)drawer.close();homeComposer.append(composer);return;}
  if(drawer.open)drawer.close();drawer.show();
  $('drawer-title').textContent=labels[ui.language][name]||names[name]||'AIRI';
  if(name==='chat'){pages.chat.append(composer);renderMessages();}else homeComposer.append(composer);
  inspectorButton.hidden=name!=='chat';newButton.hidden=name!=='chat';
  if(name==='setup'){health().catch(()=>{});loadStatus();}
  $('drawer-body').scrollTop=0;
 };
 async function newConversation(){
  if(busy){toast('현재 응답을 먼저 멈춰 주세요');return;}
  try{await api('humanlike',{action:'new_conversation'});await refresh();showPage('chat');$('message').focus();toast('기록은 보관하고 새 문맥으로 시작합니다');}catch(e){toast(e.message);}
 }
 const stop=button('응답 멈추기',()=>{window.airiCancelChat?.();interruptSpeech();},'secondary');stop.hidden=true;$('chat-form').append(stop);
 window.addEventListener('airi-context',()=>{stop.hidden=false;});window.addEventListener('airi-chat-finished',()=>{stop.hidden=true;});
 $('message').addEventListener('input',()=>{const lines=Math.min(8,Math.max(1,$('message').value.split('\n').length));$('message').rows=lines;});
 window.addEventListener('airi-presence',()=>{if(document.hidden)return;const active=!!recorder;const text=active?'● 마이크 사용 중':'마이크 꺼짐';if(mic.textContent!==text)mic.textContent=text;mic.dataset.active=String(active);});
 // Settings keep original nodes and listeners, including camera/NAS/voice forms.
 const settings=pages.setup,oldGroups=[...settings.querySelectorAll('.settings-group')];
 const search=el('input','apple-search-settings');search.type='search';search.placeholder='설정 검색';search.setAttribute('aria-label','설정 검색');
 const settingLayout=el('div','apple-settings'),settingNav=el('nav','apple-settings-nav'),settingContent=el('div');settingNav.setAttribute('aria-label','설정 항목');settingLayout.append(settingNav,settingContent);settings.append(search,settingLayout);
 const groups={},tabs={};
 const groupList=[['general','일반'],['personality','인격'],['voice','음성'],['vision','비전'],['memory','기억'],['permissions','권한'],['si','SI'],['automation','자동화'],['connections','연결'],['system','시스템'],['about','정보']];
 for(const [key,title] of groupList){const pane=el('section','apple-settings-pane');pane.id='apple-settings-'+key;pane.setAttribute('aria-label',title);groups[key]=pane;settingContent.append(pane);const b=button(title,()=>selectSettings(key));b.setAttribute('role','tab');b.setAttribute('aria-controls',pane.id);tabs[key]=b;settingNav.append(b);}
 for(const group of oldGroups){for(const node of [...group.children]){const text=(node.querySelector('h2,summary')?.textContent||'');const dest=/카메라|비전|손|방문자/.test(text)?'vision':/음성|목소리|대화 성격/.test(text)?'voice':/NAS 투자|기억/.test(text)?'memory':/공간|움직임/.test(text)?'general':/워크플로|자동화/.test(text)?'automation':group.id==='settings-connections'?'connections':'system';groups[dest].append(node);}group.hidden=true;}
 // Camera controls are added after the legacy groups have been constructed.
 for(const node of [...settings.querySelectorAll(':scope > .camera-motion')])groups.vision.append(node);
 const objectCamera=$('product-camera-panel');if(objectCamera)groups.vision.prepend(objectCamera);
 const homeSetup=groups.vision.querySelector('.camera-setup');if(homeSetup){const detail=el('details','panel homecam-connection');detail.append(el('summary','','카메라 2 연결 상세 설정'));homeSetup.replaceWith(detail);detail.append(homeSetup);}
 const legacyEmpty=settings.querySelector(':scope > .settings-empty');if(legacyEmpty)legacyEmpty.hidden=true;
 function selectSettings(key){currentSettings=key;for(const [k,pane] of Object.entries(groups)){pane.hidden=k!==key;tabs[k].setAttribute('aria-selected',String(k===key));}search.value='';}
 search.oninput=()=>{const q=search.value.toLowerCase().trim();for(const [key,pane] of Object.entries(groups))pane.hidden=q?!pane.textContent.toLowerCase().includes(q):key!==currentSettings;};
 window.AIRISettings={open(category='connections'){showPage('setup');selectSettings(groups[category]?category:'connections');},homepod(){this.open('connections');const h=$('homepod-help');if(h){h.open=true;h.scrollIntoView({block:'nearest'});}}};
 const general=el('article','panel');general.append(el('h2','','표시와 접근성'));
 general.append(row('화면 모양',select('apple-appearance',[['system','시스템 설정'],['light','라이트'],['dark','다크']],ui.appearance,v=>{ui.appearance=v;apply();})),row('대화 글자 크기',select('apple-size',[['13','작게'],['15','기본'],['17','크게'],['20','아주 크게']],ui.size,v=>{ui.size=v;apply();})),row('탐색 언어',select('apple-language',[['ko','한국어'],['en','English'],['fr','Français']],ui.language,v=>{ui.language=v;apply();localize();}),'기존 연결 도구의 설명은 원래 언어로 표시'),row('동작 줄이기',toggle('apple-motion',ui.reduceMotion,v=>{ui.reduceMotion=v;apply();})),row('투명도 줄이기',toggle('apple-transparency',ui.reduceTransparency,v=>{ui.reduceTransparency=v;apply();})));
 groups.general.prepend(general);
 general.append(row('대비 높이기',toggle('apple-contrast',ui.highContrast,v=>{ui.highContrast=v;apply();})));
 const personality=el('article','panel');personality.append(el('h2','','아이리의 기본 말투'),el('p','','편한 반말, 자연스러운 농담과 거침없는 리액션. 손님이 있거나 진지한 상황에서는 수위를 조절합니다.'));
 const guest=toggle('apple-guest',false,async value=>{try{const result=await api('humanlike',{action:'guest',enabled:value});lastMind=result;guest.checked=result.guest_mode;}catch(e){guest.checked=!value;toast(e.message);}});personality.append(row('손님 모드',guest,'욕을 빼고 편한 반말로 대화'));
 const personalityStatus=el('p','apple-info','상태 확인 중');personality.append(personalityStatus);groups.personality.append(personality);
 const oldPersona=$('persona-mode');if(oldPersona){oldPersona.closest('label').hidden=true;const summary=$('persona-summary');if(summary)summary.textContent='아이리 기본 말투';}
 const mindMemory=el('article','panel');mindMemory.append(el('h2','','대화와 감정 기록'));
 const recallStatus=el('p','apple-info','대화 검색 색인은 직접 시작합니다');const indexButton=button('대화 검색 색인 만들기',async()=>{indexButton.disabled=true;try{const value=await api('si',{action:'index_chat'});recallStatus.textContent=value.added+'개 추가됨'+(value.more_possible?' · 한 번 더 실행하면 이어집니다':'');await loadStatus();}catch(e){toast(e.message);}finally{indexButton.disabled=false;}});
 const forget=button('감정 기록 지우기',()=>review('감정 기록 지우기','이 모듈의 감정 추정, 기준선, 전략, 농담과 제안을 삭제합니다. 기존 채팅 원문과 일반 기억은 유지됩니다.',async()=>{await api('humanlike',{action:'delete_emotion_records'});await loadStatus();toast('감정 기록과 파생 데이터를 지웠습니다');}),'destructive');mindMemory.append(recallStatus,indexButton,forget);groups.memory.prepend(mindMemory);
 const permission=el('article','panel');permission.append(el('h2','','실행 승인'),el('p','','요청의 대상과 내용을 확인한 뒤 실행합니다. 외부 실행은 기존 승인 절차를 유지합니다.'),button('승인 대기 보기',()=>showPage('automation')),button('활동 기록 보기',()=>showPage('activity')));groups.permissions.append(permission);
 const siPanel=el('article','panel'),siText=el('div');siPanel.append(el('h2','','Super Personal Intelligence'),siText,button('SI 작업 모두 정지',async()=>{try{lastSI=await api('si',{action:'stop'});await loadStatus();toast('SI 작업을 정지했습니다');}catch(e){toast(e.message);}}));groups.si.append(siPanel);
 groups.about.append(el('article','panel','개인용 AIRI · Humanlike Mind 1.3 기반. 현재 Python 서버와 WKWebView에 연결한 호환 UI입니다. Tauri 전환, 전역 단축키, 음성 감정 인식은 아직 적용되지 않았습니다.'));
 if(!groups.automation.children.length)groups.automation.append(button('예약 작업과 실행 결과 보기',()=>showPage('work')));
 if(!groups.vision.children.length)groups.vision.append(el('p','apple-info','카메라 설정은 기존 연결 화면에서 확인할 수 있습니다. 얼굴 감정 분석은 꺼져 있습니다.'),button('연결 설정 보기',()=>window.AIRISettings.open('connections')));
 selectSettings('general');
 async function loadStatus(){
  if(!token)return;
  try{const [mind,si]=await Promise.all([api('humanlike'),api('si')]);lastMind=mind;lastSI=si;guest.checked=mind.guest_mode;personalityStatus.textContent='로컬 모델 '+mind.model+' · 얼굴과 목소리 감정 분석 꺼짐';
   recallStatus.textContent='색인된 대화 '+si.recall.indexed_messages+'개 · BM25 검색';siText.replaceChildren();
   for(const [label,value] of [['자동 성장','정지'],['검증된 스킬',si.metrics.trusted_skills+'개'],['기억 검색 정확도','미측정'],['Deep Think 승률','미측정'],['성장 평가','아직 검증되지 않음']])siText.append(row(label,el('strong','',value)));
   siText.append(el('p','apple-info','기본 대화는 계속 동작합니다. 야간 학습과 자동 개선은 자원 및 평가 검증 후 활성화할 수 있습니다.'));
   if(inspectorMode==='state')inspectorBody.replaceChildren(el('p','','최근 전략: '+(mind.recent_strategies.map(x=>x.strategy).join(', ')||'기록 없음')),el('p','','감정 기준선: '+(mind.cold_start?'초기 수집 단계':'축적됨')),el('p','','사용자 감정의 단정이나 진단은 하지 않습니다'),el('p','','기억 출처는 검색 결과에서 확인할 수 있습니다'));
  }catch(e){personalityStatus.textContent='연결 확인 필요';}
 }
 const launcher=el('dialog','apple-floating apple-launcher');launcher.setAttribute('aria-label','빠른 검색과 명령');const launcherInput=el('input');launcherInput.placeholder='명령 검색 또는 아이리에게 질문';launcherInput.setAttribute('aria-label','명령 또는 질문');const results=el('div','apple-launcher-results');launcher.append(launcherInput,results);body.append(launcher);
 const commands=[['새 대화',newConversation],['오늘 일정',()=>showPage('tasks')],['채팅 열기',()=>showPage('chat')],['설정 열기',()=>window.AIRISettings.open('general')],['손님 모드',()=>window.AIRISettings.open('personality')],['기억 검색',()=>{launcherInput.value='@ ';launcherInput.focus();renderCommands();}],['SI 상태',()=>window.AIRISettings.open('si')],['카메라 설정',()=>window.AIRISettings.open('vision')]];
 let searchGeneration=0;
 async function renderCommands(){const gen=++searchGeneration,q=launcherInput.value.trim();results.replaceChildren();if(q.startsWith('@')){const term=q.slice(1).trim();if(term.length<2){results.append(el('p','apple-info','검색어를 두 글자 이상 입력하세요'));return;}try{const value=await api('si/search?q='+encodeURIComponent(term));if(gen!==searchGeneration)return;if(!value.results.length)results.append(el('p','apple-info','색인된 대화에서 결과를 찾지 못했습니다'));for(const result of value.results){const b=button(result.excerpt,()=>{launcher.close();showPage('chat');inspectorMode='source';inspector.classList.add('open');inspectorButton.setAttribute('aria-expanded','true');inspectorBody.replaceChildren(el('h2','','기억 출처'),el('p','apple-info',result.source_date+' · '+result.source_id),el('p','',result.excerpt));},'apple-source');results.append(b);}}catch(e){results.append(el('p','apple-info',e.message));}return;}
  for(const [name,action] of commands.filter(([name])=>!q||name.includes(q))){results.append(button(name,()=>{if(name!=='기억 검색')launcher.close();action();}));}
  if(q&&!q.startsWith('/'))results.append(button('아이리에게 묻기: '+q,()=>{launcher.close();showPage('chat');submitChat(q);}));}
 launcherInput.oninput=renderCommands;launcherInput.onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();results.querySelector('button')?.click();}if(e.key==='ArrowDown'){e.preventDefault();results.querySelector('button')?.focus();}};
 function openLauncher(value=''){launcherInput.value=value;renderCommands();launcher.showModal();launcherInput.focus();}
 launcher.addEventListener('click',e=>{if(e.target===launcher)launcher.close();});
 const controls=el('dialog','apple-floating');controls.setAttribute('aria-label','제어 센터');body.append(controls);
 async function openControls(){await loadStatus();controls.replaceChildren(el('h2','','AIRI'),el('p','apple-info',mic.textContent));const tiles=el('div','apple-tiles');
  tiles.append(button('마이크',()=>{controls.close();$('microphone').click();}),button(lastMind?.guest_mode?'손님 모드 켜짐':'손님 모드 꺼짐',async()=>{try{await api('humanlike',{action:'guest',enabled:!lastMind?.guest_mode});controls.close();await loadStatus();}catch(e){toast(e.message);}}),button('집중 모드',()=>{controls.close();document.querySelector('.power-button')?.click();}),button('SI 작업 정지',async()=>{await api('si',{action:'stop'});controls.close();await loadStatus();}),button('카메라',()=>{controls.close();window.AIRISettings.open('vision');}),button('설정',()=>{controls.close();window.AIRISettings.open('general');}));
  controls.append(tiles,button('닫기',()=>controls.close()));controls.showModal();}
 controls.addEventListener('click',e=>{if(e.target===controls)controls.close();});
 // The review sheet requires a deliberate hold for consequential actions.
 function review(title,description,action){const sheet=el('dialog','apple-floating apple-review'),titleNode=el('h2','',title),text=el('p','',description),hint=el('p','apple-info','실행하려면 승인 버튼을 0.6초 동안 누르세요. 키보드는 Space 또는 ⌘Enter를 길게 누르세요.');hint.setAttribute('role','status');const accept=button('길게 눌러 승인',()=>{},'primary apple-hold'),cancel=button('취소',()=>sheet.close());let finished=false;
  const hold=AIRIHold.create({onChange:active=>{accept.dataset.holding=String(active);},commit:async()=>{if(finished)return;finished=true;accept.disabled=true;cancel.disabled=true;try{await action();sheet.close();}catch(e){hint.textContent=e.message;finished=false;accept.disabled=false;cancel.disabled=false;}}});
  function clear(){hold.end();}function start(){if(!finished)hold.start();}
  accept.onpointerdown=e=>{if(e.button!==0)return;accept.setPointerCapture(e.pointerId);start();};for(const type of ['pointerup','pointercancel','pointerleave'])accept.addEventListener(type,clear);
  accept.onkeydown=e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat){e.preventDefault();start();}};accept.onkeyup=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();clear();}};
  sheet.onkeydown=e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();start();}};sheet.onkeyup=e=>{if(e.key==='Enter')clear();};sheet.addEventListener('close',()=>{hold.dispose();sheet.remove();});accept.addEventListener('blur',clear);sheet.append(titleNode,text,hint,el('div','apple-actions'));sheet.lastChild.append(cancel,accept);body.append(sheet);sheet.showModal();cancel.focus();}
 // Existing backend gate remains authoritative. This adds review before approval.
 document.addEventListener('click',e=>{const b=e.target.closest('#approval-list .approval-actions button.primary');if(!b||b.dataset.confirmed==='true')return;e.preventDefault();e.stopImmediatePropagation();const card=b.closest('.approval');review(card.querySelector('strong')?.textContent||'실행 승인',card.querySelector('p')?.textContent||'요청 내용을 확인해 주세요',async()=>{b.dataset.confirmed='true';try{await b.onclick();}finally{delete b.dataset.confirmed;}});},true);
 document.addEventListener('keydown',e=>{if(e.isComposing)return;const mod=e.metaKey||e.ctrlKey;if(mod&&e.key.toLowerCase()==='k'){e.preventDefault();openLauncher();}else if(mod&&e.key===','){e.preventDefault();window.AIRISettings.open('general');}else if(mod&&e.key.toLowerCase()==='n'){e.preventDefault();newConversation();}else if(mod&&e.key.toLowerCase()==='f'){e.preventDefault();openLauncher('@ ');}else if(mod&&e.altKey&&e.key.toLowerCase()==='i'){e.preventDefault();inspectorButton.click();}else if(e.altKey&&e.code==='Space'){e.preventDefault();openLauncher();}});
 function localize(){const dict=labels[ui.language];for(const b of document.querySelectorAll('.rail-link')){const value=dict[b.dataset.view];if(value){b.querySelector('.rail-label').textContent=value;b.title=value;b.setAttribute('aria-label',value);}}quickButton.textContent=dict.search;controlButton.textContent=dict.controls;inspectorButton.textContent=dict.inspector;newButton.textContent=dict.newChat;}
 localize();
 function start(attempt=0){if(!state||!token){if(attempt<30)setTimeout(()=>start(attempt+1),500);return;}showPage('home');loadStatus();}
 start();const statusTimer=setInterval(()=>{if(!document.hidden&&(body.dataset.appleView==='setup'||inspector.classList.contains('open')))loadStatus();},15000);window.addEventListener('pagehide',()=>clearInterval(statusTimer));
})();

/* Personal desktop UI. Existing DOM controls, API handlers and runtime stay authoritative. */
(()=>{
 'use strict';
 const body=document.body,root=document.querySelector('.companion-shell');
 if(!root||!window.AIRISettings)return;
 body.classList.add('studio-ui');body.dataset.uiBuild='20261003.2';
 const icons={home:'M3 10 12 3l9 7M5 9v11h5v-6h4v6h5V9',chat:'M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0ZM8 10h8M8 14h5',tasks:'M6 3v4m12-4v4M3 10h18M5 5h14a2 2 0 0 1 2 2v13H3V7a2 2 0 0 1 2-2ZM7 14h2m6 0h2',study:'M12 5v16M3 4c4-1 6-1 9 1 3-2 5-2 9-1v15c-4-1-6-1-9 2-3-3-5-3-9-2Z',markets:'M3 17l6-6 4 3 8-10M15 4h6v6M3 21h18',work:'M8 7V4h8v3M3 7h18v13H3ZM3 12c6 3 12 3 18 0M10 12v3h4v-3',files:'M3 6h6l2 2h10v12H3ZM3 8V4h7l2 2h8',setup:'M9 3h6l1 4 4 1 2 5-3 3v4l-5 2-3-3-4 1-3-5 2-3V7l4-1ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',activity:'M3 12h4l3-7 4 14 3-7h4',mic:'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 11v1a7 7 0 0 0 14 0v-1M12 19v3M8 22h8',camera:'M3 7h4l2-3h6l2 3h4v13H3ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',plus:'M12 5v14M5 12h14',send:'M12 20V4m-6 6 6-6 6 6',search:'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-2 5 6 6',cloud:'M7 17h11a4 4 0 0 0 0-8 6 6 0 0 0-11-1 4.5 4.5 0 0 0 0 9Z',chevron:'m7 10 5 5 5-5'};
 function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('studio-icon');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[name]||icons.activity);svg.append(path);return svg;}
 function button(text,action,name){const b=el('button','studio-button',text);b.type='button';b.onclick=action;if(name)b.prepend(icon(name));return b;}
 const labels={home:'홈',chat:'대화',tasks:'일정',study:'학습',markets:'시장',work:'작업',files:'파일',setup:'설정',activity:'활동',memory:'기억과 할 일',automation:'실행 승인'};
 const rail=document.querySelector('.companion-rail');
 for(const b of rail.querySelectorAll('.rail-link')){const name=b.dataset.view;if(icons[name])b.querySelector('.rail-symbol')?.replaceChildren(icon(name));if(labels[name]){b.querySelector('.rail-label').textContent=labels[name];b.title=labels[name];b.setAttribute('aria-label',labels[name]);}}
 const activity=button('활동',()=>showPage('activity'));activity.className='rail-link studio-activity';activity.dataset.view='activity';activity.setAttribute('aria-label','활동');const label=el('span','rail-label','활동'),symbol=el('span','rail-symbol');symbol.append(icon('activity'));activity.replaceChildren(symbol,label);rail.querySelector('[data-view=tasks]').after(activity);
 const brand=rail.querySelector('.rail-brand');brand.removeAttribute('href');brand.setAttribute('role','button');brand.tabIndex=0;brand.onclick=()=>showPage('home');brand.onkeydown=e=>{if(e.key==='Enter')showPage('home');};brand.title='아이리 홈';
 const header=document.querySelector('.console-header');header.setAttribute('aria-label','아이리 시스템 상태');
 const smallClock=button('',()=>showPage('home'));smallClock.id='studio-small-clock';header.prepend(smallClock);
 const status=document.querySelector('.presence-status');status.prepend(el('span','studio-status-title','AIRI'));
 for(const b of header.querySelectorAll('button')){if(b.textContent==='검색'){b.classList.add('studio-search');b.replaceChildren(icon('search'));b.setAttribute('aria-label','명령 검색');}if(b.textContent==='☰')b.hidden=true;}
 const left=el('aside','studio-left');left.setAttribute('aria-label','오늘의 정보');root.append(left);
 const clock=el('section','context-card studio-clock'),clockDate=$('console-date'),clockTime=$('console-clock'),greeting=el('p','studio-greeting');clock.append(clockDate,clockTime,greeting);left.append(clock);
 const weather=el('section','context-card studio-weather');weather.append(icon('cloud'),el('div','','설정한 지역 날씨'),el('span','wu-fine','날씨 가져오는 중…'));left.append(weather);
 // No fabricated temperature/forecast is shown without a connected observation feed.
 const news=el('section','context-card studio-news'),newsHead=el('div','context-heading'),newsList=el('div','studio-news-list'),newsTabs=el('div','studio-news-tabs');
 const compactNews=el('section','context-card studio-compact-news'),compactHead=el('div','context-heading'),compactNewsList=el('div','studio-news-list');compactHead.append(el('h2','','주요 소식'),button('전체',()=>showPage('markets')));compactNews.append(compactHead,compactNewsList);
 newsHead.append(el('h2','','주요 소식'),button('전체',()=>showPage('markets')));let newsMode='main';
 function compactFeed(){compactNewsList.replaceChildren(...[...newsList.children].slice(0,3).map(n=>n.cloneNode(true)));}
 for(const [key,text] of [['main','주요 뉴스'],['ai','AI · 기술']]){const b=button(text,()=>{newsMode=key;renderHomeNews();});b.dataset.news=key;newsTabs.append(b);}news.append(newsHead,newsTabs,newsList);left.append(news);
 function renderHomeNews(){
  for(const b of newsTabs.children)b.setAttribute('aria-pressed',String(b.dataset.news===newsMode));
  const kinds=newsMode==='ai'?['technology']:['canada','us','business'];const items=[],seen=new Set();
  for(const key of kinds)for(const item of newsData[key]?.items||[]){if(!item.published||Date.now()-Date.parse(item.published)>86400000||Date.parse(item.published)>Date.now())continue;const key=item.url||item.title;if(seen.has(key))continue;seen.add(key);items.push(item);}
  items.sort((a,b)=>Date.parse(b.published)-Date.parse(a.published));
  const signature=JSON.stringify([newsMode,items.slice(0,5),kinds.map(k=>newsErrors[k]||null),newsInitialized]);if(newsList.dataset.signature===signature)return;newsList.dataset.signature=signature;newsList.replaceChildren();
  if(!items.length){newsList.append(el('p','studio-empty',newsInitialized?'최근 24시간에 확인된 기사가 없어. 시장에서 출처 연결을 확인해 줘.':'최근 기사를 확인하는 중…'));compactFeed();return;}
  for(const item of items.slice(0,5)){const row=el('article','studio-news-item'),a=el('a','',item.title);try{const u=new URL(item.url);if(!['http:','https:'].includes(u.protocol))continue;a.href=u.href;}catch{continue;}a.target='_blank';a.rel='noopener noreferrer';const age=Math.max(0,Math.floor((Date.now()-Date.parse(item.published))/60000));const meta=el('small','',item.source+' · '+(age<60?age+'분 전':Math.floor(age/60)+'시간 전'));row.append(a,meta);newsList.append(row);}
  if(kinds.some(k=>newsErrors[k]||newsData[k]?.stale))newsList.append(el('small','studio-warning','일부 출처 연결 지연 · 확인된 기사만 표시'));compactFeed();
 }
 const oldNews=renderNews;renderNews=function(){oldNews();renderHomeNews();};renderHomeNews();
 const column=document.querySelector('.console-right');
 function statusDots(){for(const id of ['presence-nas','presence-mac1','presence-mac2']){const n=$(id);if(n)n.dataset.connection=/연결됨/.test(n.textContent)?'good':/오프라인|응답 없음|확인 불가/.test(n.textContent)?'offline':'pending';}}new MutationObserver(statusDots).observe(status,{childList:true,subtree:true,characterData:true});statusDots();
 function decorateCards(){
  column.append(compactNews);
  const study=column.querySelector('.learning-widget');if(study){left.querySelector('.learning-widget')?.remove();left.insertBefore(study,news.parentNode===left?news:null);}
  // Each original card is moved, never cloned; music/calendar listeners remain intact.
  for(const c of document.querySelectorAll('.studio-left>.context-card,.console-right>.context-card')){const h=c.querySelector('.context-heading');if(!h||h.querySelector('.studio-collapse'))continue;const toggle=button('',()=>{const collapsed=c.classList.toggle('studio-collapsed');toggle.setAttribute('aria-expanded',String(!collapsed));});toggle.classList.add('studio-collapse');toggle.setAttribute('aria-label',h.querySelector('h2').textContent+' 카드 접기');toggle.setAttribute('aria-expanded','true');toggle.append(icon('chevron'));h.append(toggle);}
 }
 // Retain one study card after an upstream data refresh.
 window.addEventListener('airi-home-cards',()=>{left.querySelector('.learning-widget')?.remove();decorateCards();});decorateCards();
 const dock=el('section','studio-dock');dock.setAttribute('aria-label','아이리 공통 입력창');const composer=document.querySelector('.composer-wrap');dock.append(composer);const quick=document.querySelector('.quick-actions');if(quick)dock.append(quick);body.append(dock);
 const output=document.querySelector('.voice-output-status');if(output)dock.prepend(output);
 const debug=$('chat-status');if(debug){const details=el('details','studio-diagnostics'),summary=el('summary','','최근 응답 시간');details.append(summary,debug);$('apple-settings-system')?.append(details);}
 $('microphone').replaceChildren(icon('mic'));$('microphone').classList.add('studio-mic');
 document.querySelector('.attach-button')?.replaceChildren(icon('plus'));
 $('send').replaceChildren(icon('send'));
 const chatButton=document.querySelector('.conversation-open');if(chatButton){chatButton.replaceChildren(icon('chat'));chatButton.setAttribute('aria-label','대화 보기');chatButton.title='대화 보기';}
 const camera=button('',()=>window.AIRISettings.open('vision'),'camera');camera.classList.add('studio-camera');camera.setAttribute('aria-label','카메라 열기');camera.title='카메라';$('message').before(camera);
 const stopSpeech=$('stop-speech');stopSpeech.hidden=true;window.addEventListener('airi-speech-state',e=>{stopSpeech.hidden=!(e.detail?.speaking||e.detail?.preparing);});window.addEventListener('airi-speech-finished',()=>{stopSpeech.hidden=true;});
 // Keep an unsent draft across reloads of this WKWebView session.
 const draftKey='airi-unsent-draft';try{if(!$('message').value)$('message').value=sessionStorage.getItem(draftKey)||'';}catch{}
 const saveDraft=()=>{try{sessionStorage.setItem(draftKey,$('message').value);}catch{}};$('message').addEventListener('input',saveDraft);window.addEventListener('pagehide',saveDraft);$('chat-form').addEventListener('submit',()=>queueMicrotask(saveDraft));
 const mini=button('',()=>showPage('home'));mini.className='studio-mini-avatar';mini.title='아이리 홈으로';mini.setAttribute('aria-label','아이리 홈으로');const face=el('img');face.src='/assets/airi/gestures/idle.png';face.alt='';mini.append(face);body.append(mini);
 window.addEventListener('airi-presence',()=>{const live=root.querySelector('.airi-gesture.is-active');if(live&&face.getAttribute('src')!==live.getAttribute('src'))face.src=live.getAttribute('src');});
 const oldTitle=$('drawer-title'),title=el('h1','','홈');title.id='drawer-title';oldTitle.replaceWith(title);
 const context=el('span','studio-page-context');dock.prepend(context);
 let followChat=true;function scrollChatBottom(){if(body.dataset.appleView==='chat'&&followChat)$('drawer-body').scrollTop=$('drawer-body').scrollHeight;}
 $('drawer-body').addEventListener('scroll',()=>{if(body.dataset.appleView==='chat'){const host=$('drawer-body');followChat=host.scrollHeight-host.scrollTop-host.clientHeight<140;}},{passive:true});
 let chatFrame=false;new MutationObserver(()=>{if(!chatFrame&&body.dataset.appleView==='chat'&&followChat){chatFrame=true;requestAnimationFrame(()=>{chatFrame=false;scrollChatBottom();});}}).observe($('messages'),{childList:true,subtree:true,characterData:true});
 const originalShow=showPage;showPage=function(name){originalShow(name);dock.insertBefore(composer,quick||null);body.dataset.studioPage=name;title.textContent=labels[name]||names[name]||'아이리';context.textContent=name==='home'?'':(labels[name]||'아이리')+'에서 아이리에게';$('message').placeholder=name==='home'?'아이리에게 말하거나 메시지를 남겨 줘…':(labels[name]||'이 화면')+'에 대해 아이리에게 물어봐…';for(const b of rail.querySelectorAll('[data-view]')){const active=b.dataset.view===name;b.classList.toggle('selected',active);active?b.setAttribute('aria-current','page'):b.removeAttribute('aria-current');}if(name==='chat'){followChat=true;requestAnimationFrame(scrollChatBottom);}};
 $('drawer-close').onclick=()=>showPage('home');drawer.addEventListener('cancel',e=>{e.preventDefault();showPage('home');});drawer.addEventListener('close',()=>{if(!drawer.open&&body.dataset.appleView!=='home')showPage('home');});
 document.addEventListener('keydown',e=>{if(e.isComposing)return;if(e.key==='Escape'&&!document.querySelector('dialog[open]:not(.console-drawer)')){showPage('home');return;}if((e.metaKey||e.ctrlKey)&&/^[1-7]$/.test(e.key)){e.preventDefault();showPage(['home','chat','tasks','study','markets','work','files'][Number(e.key)-1]);}});
 // Eight categories, keeping every existing live form and its own save action.
 const settings=pages.setup,layout=settings.querySelector('.apple-settings'),oldNav=layout.querySelector('.apple-settings-nav'),newNav=el('nav','studio-settings-nav'),content=el('div','studio-settings-content'),panes={};newNav.setAttribute('aria-label','설정 항목');
 const categories=[['general','일반'],['models','모델'],['devices','기기 분산'],['music','음악'],['vision','카메라'],['calendar','캘린더'],['sources','데이터 소스'],['advanced','고급']];
 for(const [key,text] of categories){const pane=el('section','studio-settings-pane');pane.id='studio-settings-'+key;pane.setAttribute('aria-label',text);panes[key]=pane;content.append(pane);const b=button(text,()=>selectSettings(key));b.dataset.category=key;b.setAttribute('aria-controls',pane.id);newNav.append(b);}
 let selected='general';function selectSettings(key){selected=panes[key]?key:'general';for(const [k,p] of Object.entries(panes))p.hidden=k!==selected;for(const b of newNav.children)b.setAttribute('aria-selected',String(b.dataset.category===selected));document.querySelector('.apple-search-settings').value='';$('drawer-body').scrollTop=0;}
 const groupMap={general:'general',personality:'general',voice:'general',vision:'vision',memory:'sources',permissions:'advanced',si:'advanced',automation:'advanced',connections:'sources',system:'advanced',about:'advanced'};
 for(const [key,dest] of Object.entries(groupMap)){const node=$('apple-settings-'+key);if(node){node.hidden=false;panes[dest].append(node);}}
 oldNav.replaceWith(newNav);layout.replaceChildren(newNav,content);
 const allPanels=()=>[...content.querySelectorAll('article.panel')];
 for(const panel of allPanels()){const h=panel.querySelector('h2')?.textContent||'';if(/M1.*分|M1.*작업 분산/.test(h))panes.devices.append(panel);else if(/FreeLLM/.test(h))panes.models.append(panel);}
 const spotify=document.querySelector('.spotify-setup');if(spotify){const p=el('article','panel');p.append(el('h2','','Spotify 연결'),spotify);panes.music.append(p);}
 const modelPanel=el('article','panel');modelPanel.append(el('h2','','대화 모델'),el('p','muted','현재 설치된 모델을 선택하면 기존 대화 설정에 저장돼.'));const modelLabel=$('model').closest('label');if(modelLabel){modelLabel.classList.add('studio-model-choice');modelPanel.append(modelLabel);}panes.models.prepend(modelPanel);
 const calendarPanel=el('article','panel');calendarPanel.append(el('h2','','일정과 알림'),el('p','muted','설정한 지역 현지 시각으로 일정을 확인하고 기존 알림 설정을 사용해.'),button('일정 열기',()=>showPage('tasks')));panes.calendar.append(calendarPanel);
 for(const id of ['schedule-reminders','notification-permission']){const n=$(id);if(n)calendarPanel.append(n.closest('label')||n);}
 if(!panes.devices.children.length)panes.devices.append(el('article','panel','기기 연결 상태는 상단 M6 · M1 표시에서 확인할 수 있어.'));
 const hint=el('p','studio-settings-hint','변경은 각 항목의 저장 버튼으로 적용돼. 표시·접근성 옵션은 즉시 반영돼.');layout.before(hint);
 const mapping={personality:'general',voice:'general',memory:'sources',connections:'sources',system:'advanced',about:'advanced',si:'advanced',permissions:'advanced',automation:'advanced'};
 window.AIRISettings={open(category='general'){showPage('setup');selectSettings(mapping[category]||category);},homepod(){this.open('music');const h=$('homepod-help');if(h){h.open=true;h.scrollIntoView({block:'nearest'});}}};
 settings.querySelector('.apple-search-settings').oninput=e=>{const q=e.target.value.toLocaleLowerCase().trim();for(const [key,pane] of Object.entries(panes))pane.hidden=q?!pane.textContent.toLocaleLowerCase().includes(q):key!==selected;};selectSettings('general');
 for(const h of pages.markets.querySelectorAll('h2')){if(h.textContent==='WATCHLIST')h.textContent='관심 종목';if(h.textContent==='NEWS')h.textContent='뉴스와 분석';}
 const marketLink=body.querySelector('a[href="/investment.html"]');if(marketLink){marketLink.removeAttribute('style');marketLink.className='studio-button studio-report-link';marketLink.textContent='세계 투자 보고서 ↗';pages.markets.prepend(marketLink);}
 const imageOpen=$('image-studio-open');if(imageOpen)pages.files.append(imageOpen);
 const studyArea=pages.study;studyArea.classList.add('studio-study');const goal=studyArea.querySelector('textarea');if(goal){goal.id='studio-study-goal';const description=studyArea.querySelector('p.muted');if(description)description.textContent='아이리와 한 문제씩 연습해. 목표는 이 앱의 학습 설정에 보관돼.';const h=el('h2','','어떤 걸 함께 공부할까?');goal.before(h);goal.placeholder='예: TCF 말하기 · 하루 20분';}
 function time(){const d=new Date();clockTime.textContent=d.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false});clockDate.textContent=d.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'});smallClock.textContent=clockTime.textContent;greeting.textContent=(d.getHours()<12?'좋은 아침이야':d.getHours()<17?'오늘도 같이 해보자':d.getHours()<21?'편안한 저녁이야':'조용히 쉬어 가자')+', User.';body.dataset.phase=root.dataset.environment||'night';}
 time();setInterval(time,30000);window.addEventListener('airi-environment',time);
 showPage('home');window.dispatchEvent(new CustomEvent('airi-layout'));
})();

/* Widget-first personal workspace. All existing action handlers remain live. */
(()=>{
 'use strict';
 const body=document.body,root=document.querySelector('.companion-shell');
 if(!root||!body.classList.contains('studio-ui'))return;
 body.classList.add('widget-ui');body.dataset.uiBuild='20261003.widgets2';
 const paths={plus:'M12 5v14M5 12h14',back:'m14 5-7 7 7 7',close:'m6 6 12 12M6 18 18 6',down:'m7 10 5 5 5-5',up:'m7 14 5-5 5 5',edit:'m15 4 5 5M4 20l5-1L21 7l-5-5L4 14Z',check:'m5 12 4 4L19 6',pause:'M9 5v14M15 5v14',play:'m8 5 11 7-11 7Z',settings:'M9 3h6l1 4 4 1 2 5-3 3v4l-5 2-3-3-4 1-3-5 2-3V7l4-1ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',calendar:'M6 3v4m12-4v4M3 10h18M5 5h14a2 2 0 0 1 2 2v13H3V7a2 2 0 0 1 2-2ZM7 14h2m6 0h2',study:'M12 5v16M3 4c4-1 6-1 9 1 3-2 5-2 9-1v15c-4-1-6-1-9 2-3-3-5-3-9-2Z',news:'M4 4h16v17H4ZM8 8h8M8 12h8M8 16h5',markets:'M3 17l6-6 4 3 8-10M15 4h6v6M3 21h18',music:'M9 18V5l11-2v13M9 8l11-2M9 18c0 4-6 4-6 0s6-4 6 0ZM20 16c0 4-6 4-6 0s6-4 6 0Z',files:'M3 6h6l2 2h10v12H3ZM3 8V4h7l2 2h8',work:'M8 7V4h8v3M3 7h18v13H3ZM3 12c6 3 12 3 18 0',chat:'M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0ZM8 10h8M8 14h5',activity:'M3 12h4l3-7 4 14 3-7h4',camera:'M3 7h4l2-3h6l2 3h4v13H3ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 6v6l4 2',weather:'M7 17h11a4 4 0 0 0 0-8 6 6 0 0 0-11-1 4.5 4.5 0 0 0 0 9Z',monitor:'M3 4h18v13H3ZM8 21h8M12 17v4',model:'M7 7h10v10H7ZM3 8h4M3 16h4M17 8h4M17 16h4M8 3v4M16 3v4M8 17v4M16 17v4',sources:'M20 6c0 4-16 4-16 0s16-4 16 0ZM4 6v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0',shield:'M12 3 3 6v6c0 5 9 9 9 9s9-4 9-9V6ZM8 12l3 3 5-6'};
 paths.search='M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z';paths.stock101=paths.markets;paths['mac-status']=paths.monitor;
 function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('wu-icon');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[name]||paths.plus);svg.append(p);return svg;}
 function btn(text,action,ic,cls=''){const b=el('button','wu-button '+cls);b.type='button';if(ic)b.append(icon(ic));if(text)b.append(document.createTextNode(text));b.onclick=action;return b;}
 function iconBtn(label,ic,fn){const b=btn('',fn,ic,'wu-icon-button');b.setAttribute('aria-label',label);b.title=label;return b;}
 function note(text){return el('p','wu-fine',text);}
 function chip(text,kind=''){return el('span','wu-chip '+kind,text);}
 function row(label,control,help=''){const r=el('div','wu-setting-row'),l=el('span','wu-setting-label',label),f=el('div','wu-setting-field');if(control)f.append(control);if(help)f.append(note(help));r.append(l,f);return r;}
 function card(title,cls=''){const c=el('article','wu-card '+cls),h=el('header','wu-card-head');h.append(el('h2','',title));c.append(h);return c;}
 function details(title,nodes){const d=el('details','wu-details');d.append(el('summary','',title));for(const n of nodes||[])if(n)d.append(n);return d;}
 function switchStyle(control,label){control.classList.add('wu-switch');control.setAttribute('aria-label',label);return control;}
 const definitions=[
  ['clock','시계','오늘의 시간과 인사','home','left'],
  ['weather','날씨','설정한 지역 현재 기온과 3일 예보','weather','left'],
  ['study','학습','목표와 함께 한 문제씩','study','left'],
  ['news','주요 소식','최신 기사와 AI 소식','markets','left'],
  ['calendar','일정','오늘의 약속과 달력','tasks','right'],
  ['markets','관심 종목','시세와 시장 분석','markets','right'],
  ['music','음악','Spotify와 소리 출력','music','right'],
  ['chat','대화','아이리와 이어서 이야기','chat','left'],
  ['work','작업','기억·스킬·작업 결과','work','left'],
  ['files','파일','NAS 자료와 생성 이미지','files','right'],
  ['activity','활동','실행 기록과 승인 대기','activity','right'],
  ['camera','카메라','사물 인식과 홈캠','camera','right'],
  ['settings','설정','말투·목소리·연결','setup','left'],
  ['stock101','Stock101','별도 시장 작업실 열기','stock101','right']
 ];
 let prefs={widgets:['clock','weather','study','news','calendar','markets','music'],collapsed:[],study_goal:'',study_language:'프랑스어'},ready=false,editing=false,saveChain=Promise.resolve();
 const cards=new Map(),parking=el('div','wu-parking');parking.hidden=true;root.append(parking);
 const workspace=el('section','wu-workspace'),left=el('div','wu-column wu-left'),right=el('div','wu-column wu-right');workspace.setAttribute('aria-label','내 위젯');workspace.append(left,right);root.append(workspace);
 const compactNews=document.querySelector('.studio-compact-news');
 function openView(page){if(page==='stock101')window.Stock101?.open();else if(page==='music')window.AIRISettings.open('music');else if(page==='camera')window.AIRISettings.open('vision');else if(page==='weather'){if(!prefs.widgets.includes('weather'))toggleWidget('weather');showPage('home');loadWeather();}else showPage(page);}
 let weatherData=null,weatherError='',weatherLoading=false;
 function drawWeather(c){
  if(!c)return;c.replaceChildren();
  const h=el('header','wu-card-head');h.append(el('h2','','설정한 지역'),iconBtn('날씨 새로고침','weather',loadWeather));c.append(h);
  if(!weatherData){const n=note(weatherError||'날씨 가져오는 중…');n.setAttribute('role','status');c.append(n);}
  else{
   const d=weatherData,main=el('div','wu-weather-now'),temp=el('strong','wu-temperature',Math.round(d.temp_c)+'°'),description=el('div','wu-weather-description');
   description.append(el('span','',d.condition),note('체감 '+Math.round(d.feels_c)+'°'));main.append(temp,description);c.append(main);
   const today=new Intl.DateTimeFormat('en-CA',{timeZone:d.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()),day=d.forecast.find(x=>x.date===today);
   if(day)c.append(el('p','wu-weather-range','최고 '+Math.round(day.high_c)+'° · 최저 '+Math.round(day.low_c)+'° · 강수 '+Math.round(day.rain_percent)+'%'));
   const forecast=el('div','wu-weather-forecast');for(const f of d.forecast){const line=el('div');line.append(el('span','',f.date.slice(5).replace('-','/')+' '+f.condition),el('span','',Math.round(f.low_c)+'° / '+Math.round(f.high_c)+'°'));forecast.append(line);}
   c.append(details('3일 예보', [forecast]));
   const stamp=new Intl.DateTimeFormat('ko-KR',{timeZone:d.timezone,month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(d.as_of));
   const source=el('a','wu-weather-source',d.source+' · '+stamp+' 기준');source.href=d.source_url;source.target='_blank';source.rel='noopener';c.append(source);
   if(d.data_kind==='기상 모델 추정')c.append(note(d.data_kind));
   if(d.stale||weatherError)c.append(note(weatherError||'갱신 지연 · 표시 시각의 날씨'));
  }
  decorateWidget('weather',c);
 }
 async function loadWeather(){
  if(weatherLoading||!token)return;weatherLoading=true;
  try{weatherData=await api('weather-widget');weatherError='';}catch(e){weatherError=e.message;}
  finally{weatherLoading=false;drawWeather(cards.get('weather'));}
 }
 function savePrefs(patch){const previous=JSON.parse(JSON.stringify(prefs));prefs={...prefs,...patch};arrange();if(!ready)return Promise.resolve(false);saveChain=saveChain.catch(()=>{}).then(async()=>{try{const saved=await api('ui-preferences',patch);if(patch.study_goal!==undefined)prefs.study_goal=saved.study_goal;return true;}catch(e){prefs=previous;arrange();toast('화면 설정을 저장하지 못했어. '+e.message);return false;}});return saveChain;}
 function toggleWidget(id){const next=prefs.widgets.includes(id)?prefs.widgets.filter(k=>k!==id):[...prefs.widgets,id];savePrefs({widgets:next});renderLibrary();}
 function decorateWidget(id,c){
  c.dataset.widget=id;c.classList.add('wu-home-card');
  if(!c.querySelector(':scope > .wu-edit-tools')){
   const edit=el('div','wu-edit-tools');
   edit.append(iconBtn('위젯 위로 이동','up',()=>moveWidget(id,-1)),iconBtn('위젯 아래로 이동','down',()=>moveWidget(id,1)),iconBtn('위젯 제거','close',()=>toggleWidget(id)));c.prepend(edit);
   c.addEventListener('dragstart',e=>{if(!editing){e.preventDefault();return;}e.dataTransfer.setData('text/plain',id);e.dataTransfer.effectAllowed='move';});
   c.addEventListener('dragover',e=>{if(editing)e.preventDefault();});
   c.addEventListener('drop',e=>{if(!editing)return;e.preventDefault();const from=e.dataTransfer.getData('text/plain');if(from===id||!prefs.widgets.includes(from))return;const next=prefs.widgets.filter(x=>x!==from);next.splice(next.indexOf(id),0,from);savePrefs({widgets:next});});
  }
  const h=c.querySelector('.context-heading,.wu-card-head');
  let collapse=h?.querySelector('.studio-collapse,.wu-collapse');
  if(h&&!collapse){collapse=iconBtn('위젯 접기','down',()=>{});collapse.classList.add('wu-collapse');h.append(collapse);}
  if(collapse){collapse.onclick=()=>{const next=prefs.collapsed.includes(id)?prefs.collapsed.filter(k=>k!==id):[...prefs.collapsed,id];savePrefs({collapsed:next});};collapse.setAttribute('aria-expanded',String(!prefs.collapsed.includes(id)));}
  c.draggable=editing;c.classList.toggle('wu-collapsed',prefs.collapsed.includes(id));c.classList.remove('studio-collapsed');
 }
 function moveWidget(id,d){const next=[...prefs.widgets],i=next.indexOf(id),side=definitions.find(x=>x[0]===id)?.[4],siblings=next.filter(x=>definitions.find(y=>y[0]===x)?.[4]===side),target=siblings[siblings.indexOf(id)+d];if(!target)return;const j=next.indexOf(target);[next[i],next[j]]=[next[j],next[i]];savePrefs({widgets:next});}
 function arrange(){
  for(const c of cards.values())parking.append(c);
  for(const id of prefs.widgets){const def=definitions.find(x=>x[0]===id),c=cards.get(id);if(!def||!c)continue;decorateWidget(id,c);(def[4]==='left'?left:right).append(c);}
  if(compactNews)parking.append(compactNews);
  body.classList.toggle('wu-editing',editing);editButton.textContent=editing?'완료':'편집';editButton.setAttribute('aria-pressed',String(editing));
  workspace.classList.toggle('wu-empty',!prefs.widgets.length);
  window.dispatchEvent(new CustomEvent('airi-widgets-changed'));
 }
 function collectCards(){
  for(const [id,selector] of [['clock','.studio-clock'],['weather','.studio-weather'],['study','.learning-widget'],['news','.studio-news'],['calendar','.today-widget'],['markets','.watch-widget'],['music','.music-widget']]){
   const found=[...root.querySelectorAll(selector)].find(n=>!parking.contains(n)&&!workspace.contains(n))||cards.get(id)||root.querySelector(selector);
   if(found&&found!==cards.get(id)){cards.get(id)?.remove();cards.set(id,found);if(id==='music')decorateMusic(found);if(id==='weather')drawWeather(found);}
  }arrange();
 }
 for(const [id,title,description,page] of definitions.filter(d=>['chat','work','files','activity','camera','settings','stock101'].includes(d[0]))){const c=card(title,'wu-launch-card'),content=el('div','wu-launch-body');content.append(icon(id==='stock101'?'markets':id),note(description),btn('열기',()=>openView(page),'back','wu-open'));c.append(content);cards.set(id,c);}
 document.querySelector('.companion-rail').hidden=true;
 const oldHeader=document.querySelector('.console-header'),oldPause=oldHeader.querySelector('.power-button'),oldControl=[...oldHeader.querySelectorAll('button')].find(b=>b.textContent==='제어 센터'),oldSearch=oldHeader.querySelector('.studio-search');
 oldHeader.hidden=true;
 const toolbar=el('header','wu-toolbar'),toolbarLeft=el('div','wu-toolbar-left'),toolbarRight=el('div','wu-toolbar-right');
 const home=btn('AIRI',()=>showPage('home'),'back','wu-home-button');home.setAttribute('aria-label','홈으로');
 const libraryButton=btn('위젯 추가',()=>openLibrary(),'plus'),editButton=btn('편집',()=>{editing=!editing;showPage('home');arrange();});
 toolbarLeft.append(home,libraryButton,editButton);
 const system=btn('',()=>openSystem(),'','wu-system'),pause=iconBtn('일시정지','pause',()=>oldPause.click()),search=iconBtn('명령 검색','search',()=>oldSearch.click()),settingsButton=iconBtn('설정','settings',()=>window.AIRISettings.open('general'));
 toolbarRight.append(system,pause,search,settingsButton);toolbar.append(toolbarLeft,toolbarRight);body.append(toolbar);
 const library=el('dialog','wu-sheet wu-library');library.setAttribute('aria-label','위젯 추가');const libraryHead=el('header','wu-sheet-head'),libraryList=el('div','wu-widget-library'),librarySearch=el('input','wu-field');librarySearch.type='search';librarySearch.placeholder='위젯 검색';librarySearch.setAttribute('aria-label','위젯 검색');libraryHead.append(el('div','', '위젯 추가'),iconBtn('위젯 창 닫기','close',()=>library.close()));library.append(libraryHead,note('필요한 것만 홈에. 카드를 추가하고 원하는 순서로 놓아 봐.'),librarySearch,libraryList);body.append(library);librarySearch.oninput=renderLibrary;
 function renderLibrary(){libraryList.replaceChildren();for(const [id,title,description,page] of definitions.filter(d=>(d[1]+' '+d[2]).includes(librarySearch.value.trim()))){const tile=card(title,'wu-library-card'),preview=el('div','wu-library-preview');preview.append(icon(id));tile.prepend(preview);tile.append(note(description));const actions=el('div','wu-actions'),on=prefs.widgets.includes(id);actions.append(btn(on?'추가됨':'추가',()=>toggleWidget(id),on?'check':'plus',on?'':'primary'),btn('열기',()=>{library.close();openView(page);}));tile.append(actions);tile.dataset.added=String(on);actions.firstChild.setAttribute('aria-label',title+' 위젯 '+(on?'제거':'추가'));actions.firstChild.setAttribute('aria-pressed',String(on));actions.firstChild.disabled=!ready;libraryList.append(tile);}}
 function openLibrary(){renderLibrary();if(!library.open)library.showModal();librarySearch.focus();}
 for(const dialog of [library]){dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});}
 const statusDialog=el('dialog','wu-sheet wu-status');statusDialog.setAttribute('aria-label','시스템 상태');body.append(statusDialog);
 function openSystem(){const n=window.airiNodeStatus||{};statusDialog.replaceChildren();const h=el('header','wu-sheet-head');h.append(el('h2','','시스템 상태'),iconBtn('닫기','close',()=>statusDialog.close()));statusDialog.append(h);for(const [label,value] of [['AIRI',$('presence-voice').textContent.replace('Voice · ','')],['이 Mac',n.node||'확인 중'],['M1',n.mac2?.connected?'연결됨':'확인 필요'],['NAS',n.nas?.connected?'연결됨':'확인 필요'],['현재 모델',state?.settings?.model||'확인 중']])statusDialog.append(row(label,el('span','',value)));const diagnostics=$('chat-status');if(diagnostics)statusDialog.append(details('응답 시간',[note(diagnostics.textContent)]));statusDialog.append(btn('연결 설정',()=>{statusDialog.close();window.AIRISettings.open('devices');}));if(!statusDialog.open)statusDialog.showModal();}
 function syncStatus(){system.replaceChildren();for(const [id,label] of [['presence-voice',''],['presence-nas','NAS'],['presence-mac1','M6'],['presence-mac2','M1']]){const source=$(id),s=el('span','wu-status-item'),good=id==='presence-voice'?source.dataset.active==='true':/연결됨/.test(source.textContent),pending=/확인 중|대기|휴식/.test(source.textContent);s.append(el('b','wu-dot '+(good?'good':pending?'':'warn')),document.createTextNode(label||source.textContent.replace('Voice · ','')));system.append(s);}system.setAttribute('aria-label','시스템 상태');pause.setAttribute('aria-label',oldPause.textContent);pause.replaceChildren(icon(window.airiFocus?'play':'pause'));}
 new MutationObserver(syncStatus).observe(oldHeader,{childList:true,subtree:true,characterData:true});syncStatus();
 // Match the review's page rhythm: one sticky heading, one body scroll, no rail.
 const head=document.querySelector('.drawer-head'),title=$('drawer-title'),titleGroup=el('div','wu-title-group'),subtitle=el('p','wu-page-description'),pageAction=btn('새 일정',()=>$('calendar-add').click(),'plus','primary');
 title.replaceWith(titleGroup);titleGroup.append(title,subtitle);head.append(pageAction);$('drawer-body').prepend(head);
 const descriptions={chat:'맥락은 이어지고, 말은 편하게.',tasks:'하루의 약속과 아이리에게 맡긴 일을 한곳에서.',study:'아이리와 같이, 내 속도에 맞춰.',markets:'가격에서 멈추지 않고, 이유와 내 자산의 영향을 봐.',work:'기억과 도구를 연결해, 끝까지 처리할 수 있게.',files:'보고서와 자료, 생성한 이미지를 한곳에서.',setup:'내 방식대로, 필요한 것만.',activity:'지금 하는 일, 기다리는 일, 내가 결정할 일.'};
 const show=showPage;showPage=function(name){show(name);subtitle.textContent=descriptions[name]||'';pageAction.hidden=name!=='tasks';findSettings.hidden=name!=='setup';home.classList.toggle('at-home',name==='home');editButton.hidden=name!=='home';$('message').placeholder='아이리에게 말하기';if(name==='tasks')renderAgenda();};
 const composer=$('chat-form'),message=$('message'),camera= composer.querySelector('.studio-camera'),attachment=composer.querySelector('.attach-button');
 if(camera&&attachment){message.after(camera,attachment);}
 const context=document.querySelector('.studio-page-context');if(context)context.hidden=true;
 // Calendar keeps its live month controls; selected-day agenda matches the review.
 const cal=$('console-calendar'),calPanel=cal.querySelector('.calendar-panel'),selected=$('calendar-date').parentElement,events=$('calendar-events'),add=$('calendar-add'),taskPage=pages.tasks;
 const agenda=card('','wu-agenda-card'),agendaTitle=agenda.querySelector('h2'),agendaContent=el('div','wu-agenda-content');agenda.append(agendaContent);
 selected.hidden=true;events.hidden=true;add.hidden=true;calPanel.querySelector('.eyebrow')?.remove();
 cal.prepend(el('h2','wu-calendar-label','달력'));
 const legend=el('div','wu-calendar-legend');for(const [label,kind] of [['개인','personal'],['학습','study'],['작업','work']]){const s=el('span');s.append(el('b','wu-dot '+kind),document.createTextNode(label));legend.append(s);}calPanel.append(legend);
 const oldOverview=$('console-tasks');oldOverview.hidden=true;taskPage.append(agenda);
 const knowledge=$('home-knowledge').closest('.home-storage');knowledge.firstElementChild.textContent='나의 지식';knowledge.classList.add('wu-knowledge');pages.work.prepend(knowledge);
 function category(t){return /학습|수업|연습|불어|프랑스/.test(t.title)?'study':t.action&&t.action!=='manual'?'work':'personal';}
 function agendaItem(t,past){const item=el('div','wu-task-row'+(past?' past':'')),check=el('input');check.type='checkbox';check.checked=!!t.done;check.disabled=t.action!=='manual';check.setAttribute('aria-label',t.title+' 완료');check.onchange=async()=>{check.disabled=true;try{await api('task-toggle',{id:t.id});await refresh();}catch(e){toast(e.message);renderAgenda();}};const info=el('div','wu-task-info');info.append(el('h3','',t.title),note(dueLabel(t)));const actions=el('div','wu-task-actions');actions.append(iconBtn(t.title+' 편집','edit',()=>editTask(t)),iconBtn(t.title+' 삭제','close',()=>removeTask(t)));if(t.result)actions.prepend(btn('결과',()=>showTaskResult(t)));item.append(el('b','wu-dot '+category(t)),check,info,chip(t.done?'완료':taskStatuses[t.status]||'개인'),actions);return item;}
 function renderAgenda(){if(!state)return;agendaTitle.textContent=new Date(selectedDate+'T12:00:00').toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'});agendaContent.replaceChildren();const today=localDate(new Date()),all=(state.tasks||[]).filter(t=>!['cancelled','expired'].includes(t.status)),chosen=all.filter(t=>t.due_date===selectedDate).sort((a,b)=>(a.due_time||'').localeCompare(b.due_time||'')),past=all.filter(t=>t.due_date&&t.due_date<selectedDate).sort((a,b)=>(b.due_date+(b.due_time||'')).localeCompare(a.due_date+(a.due_time||'')));
  agendaContent.append(el('p','wu-section-label',selectedDate<today?'선택한 날짜':'예정'));
  if(chosen.length)for(const t of chosen)agendaContent.append(agendaItem(t,t.done||selectedDate<today));
  else{const empty=el('div','wu-empty-state');empty.append(icon('calendar'),el('h3','','이날은 비워져 있어'),note('새 약속이나 아이리에게 맡길 일을 추가해 봐.'),btn('새 일정',()=>add.click(),'plus'));agendaContent.append(empty);}
  if(past.length){const section=el('section','wu-past-events');section.append(el('p','wu-section-label','지난 일정'));for(const t of past.slice(0,4))section.append(agendaItem(t,true));if(past.length>4)section.append(btn('지난 일정 더 보기',()=>{for(const t of past.slice(4))section.insertBefore(agendaItem(t,true),section.lastElementChild);section.lastElementChild.remove();}));agendaContent.append(section);}
 }
 const oldPlanner=renderPlanner;renderPlanner=function(){oldPlanner();const grid=$('calendar-grid'),y=calendarMonth.getFullYear(),m=calendarMonth.getMonth(),start=(new Date(y,m,1).getDay()+6)%7,days=new Date(y,m+1,0).getDate();grid.replaceChildren();document.querySelector('.calendar-weekdays').replaceChildren(...['월','화','수','목','금','토','일'].map(x=>el('span','',x)));const total=Math.ceil((start+days)/7)*7;for(let i=0;i<total;i++){const date=new Date(y,m,i-start+1),key=localDate(date),b=btn(String(date.getDate()),()=>{selectedDate=key;if(date.getMonth()!==m)calendarMonth=new Date(date.getFullYear(),date.getMonth(),1);renderPlanner();});b.className='calendar-day'+(date.getMonth()!==m?' outside':'')+(key===localDate(new Date())?' today':'')+(key===selectedDate?' selected':'');b.setAttribute('aria-label',key);b.setAttribute('aria-pressed',String(key===selectedDate));if(state.tasks.some(t=>t.due_date===key&&!t.done))b.append(el('span','calendar-dot'));grid.append(b);}renderAgenda();};
 // Reuse the real editor in a focused sheet, including validation and attachments.
 const taskForm=$('task-form'),taskHome=taskForm.parentElement,taskNext=taskForm.nextSibling,taskSheet=el('dialog','wu-sheet wu-task-sheet'),taskSheetHead=el('header','wu-sheet-head'),taskSheetTitle=el('h2','','새 일정');
 taskSheet.setAttribute('aria-label','일정 편집');taskSheetHead.append(taskSheetTitle,iconBtn('일정 창 닫기','close',()=>taskSheet.close()));taskSheet.append(taskSheetHead);body.append(taskSheet);
 const reminderOptions=taskForm.querySelector('.reminder-editor'),reminderDetail=details('알림 설정',[reminderOptions]);$('task-series-info').after(reminderDetail);
 const instructions=$('task-instructions'),instructionLabel=taskForm.querySelector('label[for="task-instructions"]'),instructionGroup=el('div','wu-task-instructions');instructionLabel.before(instructionGroup);instructionGroup.append(instructionLabel,instructions);
 const attachmentZone=taskForm.querySelector('.attachment-zone'),attachmentHelp=$('task-attachments').nextElementSibling,attachmentDetail=details('참고 자료 첨부');attachmentZone.before(attachmentDetail);attachmentDetail.append(attachmentZone,$('task-file-name'),$('task-attachments'),attachmentHelp);
 function syncTaskSheet(){instructionGroup.hidden=$('task-action').value==='manual';attachmentDetail.open=taskFiles.length>0;}
 const originalTaskAction=$('task-action').onchange;$('task-action').onchange=e=>{originalTaskAction(e);syncTaskSheet();};
 function openTaskSheet(label){taskSheetTitle.textContent=label;taskSheet.append(taskForm);syncTaskSheet();if(!taskSheet.open)taskSheet.showModal();$('task-input').focus();}
 taskSheet.addEventListener('close',()=>{taskHome.insertBefore(taskForm,taskNext);});
 function newTaskSheet(date=selectedDate){resetTask();$('task-date').value=date;openTaskSheet('새 일정');}
 add.onclick=()=>newTaskSheet();$('home-new-task').onclick=()=>newTaskSheet(localDate(new Date()));
 if(attachment)attachment.onclick=()=>{newTaskSheet(localDate(new Date()));attachmentDetail.open=true;$('task-file').click();};
 for(const b of document.querySelectorAll('.quick-action')){if(b.getAttribute('aria-label')==='새 일정')b.onclick=()=>newTaskSheet(localDate(new Date()));if(b.getAttribute('aria-label')==='데이터 분석')b.onclick=()=>{newTaskSheet(localDate(new Date()));taskSheetTitle.textContent='분석 작업';$('task-input').value='데이터 분석';$('task-action').value='ai';syncTaskSheet();instructions.focus();};}
 const previousEditTask=editTask;editTask=function(t){const page=body.dataset.appleView||'tasks';previousEditTask(t);showPage(page);openTaskSheet('일정 편집');};
 const previousSubmitTask=taskForm.onsubmit;taskForm.onsubmit=async e=>{await previousSubmitTask(e);if(taskSheet.open&&!$('task-input').value){taskSheet.close();renderPlanner();}};
 $('task-cancel').onclick=()=>{resetTask();if(taskSheet.open)taskSheet.close();};
 $('task-delete').onclick=async()=>{const t=state.tasks.find(t=>t.id===editingTask);if(t){await removeTask(t);if(taskSheet.open&&!state.tasks.some(x=>x.id===t.id))taskSheet.close();}};
 // Settings use the exact row proportions and glass surfaces of the review.
 const setup=pages.setup,nav=setup.querySelector('.studio-settings-nav'),panes=setup.querySelector('.studio-settings-content');
 const catIcons={general:'settings',models:'model',devices:'monitor',music:'music',vision:'camera',calendar:'calendar',sources:'sources',advanced:'shield'};
 for(const b of nav.children)b.prepend(icon(catIcons[b.dataset.category]));
 const searchSettings=setup.querySelector('.apple-search-settings');const findSettings=details('설정 검색',[searchSettings]);findSettings.classList.add('wu-settings-search');head.append(findSettings);
 setup.querySelector('.studio-settings-hint').hidden=true;setup.querySelector('.section-heading')?.setAttribute('hidden','');
 // Convert original labels in place, retaining handlers and form ancestry.
 function formRows(scope){for(const label of [...scope.querySelectorAll('label')]){if(label.closest('.wu-setting-row')||label.hidden||label.querySelector('input[type=file]'))continue;const field=label.querySelector('input,select,textarea');if(!field)continue;const title=[...label.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').trim()||label.querySelector('span')?.textContent||field.getAttribute('aria-label');if(!title)continue;const f=el('div','wu-setting-field'),r=el('div','wu-setting-row'),l=el('label','wu-setting-label',title);if(!field.id)field.id='wu-field-'+(++fieldId);l.htmlFor=field.id;label.replaceWith(r);f.append(field);for(const child of [...label.children])if(child!==field&&child.tagName!=='SPAN')f.append(child);if(field.type==='checkbox')switchStyle(field,title);r.append(l,f);}}
 let fieldId=0;
 for(const r of panes.querySelectorAll('.apple-row')){r.classList.add('wu-setting-row');r.firstElementChild?.classList.add('wu-setting-label');const control=r.lastElementChild;if(control?.type==='checkbox')switchStyle(control,r.firstElementChild.textContent);}
 // Camera 1: same simple rows as the reference; results and diagnostics unfold.
 const product=$('product-camera-panel'),productSelect=product.querySelector('select'),use=product.querySelector('input[aria-label="카메라 1 사용"]'),speak=product.querySelector('input[aria-label="자동 인식 결과 말하기"]'),productStatuses=[...product.querySelectorAll('[role=status]')],productActions=product.querySelector('.form-actions'),productButtons=[...productActions.children],auto=productButtons[2],results=product.querySelector('.product-camera-results'),preview=product.querySelector('.product-camera-preview');
 const statusBadge=chip('확인 중'),productHead=el('header','wu-setting-title');productHead.append(el('h2','','카메라 1 · 사물 인식'),statusBadge);
 product.replaceChildren(productHead,row('사용할 카메라',productSelect,'사물·라벨·바코드를 이 Mac에서 확인해.'),row('상시 인식',auto,'새 물건이 보일 때 확인'),row('결과 읽어주기',switchStyle(speak,'자동 인식 결과 말하기'),'반복 안내는 잠시 쉬어'),row('웹에서 판매처 찾기',chip('제품명·바코드만 외부 전송','warn'),'사진 자체는 검색 서비스에 보내지 않아.'));
 auto.className='wu-auto-switch';auto.setAttribute('role','switch');
 const syncAuto=()=>auto.setAttribute('aria-checked',auto.getAttribute('aria-pressed')||'false');new MutationObserver(syncAuto).observe(auto,{attributes:true,attributeFilter:['aria-pressed']});syncAuto();
 productButtons[0].textContent='화면 확인';productButtons[1].textContent='제품 확인';productButtons[1].className='secondary';
 const productTools=el('div','wu-actions');productTools.append(productButtons[0],productButtons[1]);product.append(productTools,details('인식 결과와 상태',[...productStatuses,preview,results]));
 const cameraPower=el('div','wu-danger');cameraPower.append(row('카메라 사용',switchStyle(use,'카메라 1 사용'),'끄면 사물 인식도 사용할 수 없어.'));product.append(cameraPower);
 const changeCamera=use.onchange;use.onchange=async e=>{if(!use.checked&&!confirm('카메라 1을 끌까? 사물 인식도 멈춰.')){use.checked=true;return;}await changeCamera(e);};
 new MutationObserver(()=>{const text=productStatuses[0].textContent,good=/연결됨|완료|촬영 화면/.test(text);statusBadge.textContent=good?'연결됨':/확인 중|가져오는 중/.test(text)?'확인 중':'확인 필요';statusBadge.classList.toggle('good',good);statusBadge.classList.toggle('warn',!good);}).observe(productStatuses[0],{subtree:true,childList:true,characterData:true});
 // Home camera's existing enrollment/movement/settings remain reachable.
 const vision=$('studio-settings-vision'),homePanels=[...vision.querySelectorAll('.camera-motion')],motion=homePanels.find(p=>p.querySelector('h2')?.textContent.includes('움직임')),presence=homePanels.find(p=>p.querySelector('h2')?.textContent.includes('얼굴 등록'));
 if(presence){const stat=presence.querySelector('[role=status]'),badge=chip('확인 중'),controls=presence.querySelector('.home-guard-controls'),oldChildren=[...presence.children];const h=el('header','wu-setting-title');h.append(el('h2','','카메라 2 · 홈캠'),badge);presence.replaceChildren(h,row('사용할 카메라',el('strong','','Tapo C200'),'감시를 켠 동안만 방문자를 확인해.'),row('방문자 감시',controls,'미등록 얼굴은 경고·대화, 등록된 가족은 지정한 호칭으로 인사해.'),details('가족 얼굴 등록과 감시 상태',oldChildren.filter(n=>n.tagName!=='H2'&&n!==controls)));new MutationObserver(()=>{const active=stat.dataset.guard==='active';badge.textContent=active?'감시 중':stat.dataset.guard==='off'?'감시 꺼짐':'연결 확인 / 준비 중';badge.classList.toggle('good',active);badge.classList.toggle('warn',!active&&stat.dataset.guard!=='off');}).observe(stat,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['data-guard']});vision.prepend(product,presence);}
 if(motion){const detail=details('카메라 이동·손 추적',[motion]);vision.append(detail);}
 const connection=vision.querySelector('.homecam-connection');if(connection)vision.append(connection);
 // Two-machine roles show real connection status, with advanced routing below.
 const device=$('studio-settings-devices').querySelector('article'),deviceNodes=[...device.children],deviceState=device.querySelector('p'),deviceForm=device.querySelector('form'),deviceRefresh=[...deviceForm.querySelectorAll('button')].find(b=>b.textContent==='연결 확인');
 const mainBadge=chip('확인 중'),m1Badge=chip('확인 중'),deviceTitle=el('header','wu-setting-title');deviceTitle.append(el('h2','','역할을 나눠 쓰기'));
 device.replaceChildren(deviceTitle,row('M6 · 주 기기',mainBadge,'실시간 대화·음성·카메라, 이미지·영상 생성을 담당해.'),row('M1 · 백그라운드 작업',m1Badge,'문서 요약·번역·정리, 보고서 분석, 영상 기획·스크립트를 맡아.'),deviceRefresh,details('작업 배정과 연결 상세',deviceNodes.filter(n=>n.tagName!=='H2')));deviceRefresh.className='secondary';
 function machineBadges(){for(const [badge,id] of [[mainBadge,'presence-mac1'],[m1Badge,'presence-mac2']]){const good=/연결됨/.test($(id).textContent);badge.textContent=good?'연결됨':'확인 필요';badge.classList.toggle('good',good);badge.classList.toggle('warn',!good);}}new MutationObserver(machineBadges).observe(oldHeader,{childList:true,subtree:true,characterData:true});machineBadges();
 // Keep nonessential technical prose behind disclosure rows across all settings.
 formRows(panes);
 for(const pane of panes.querySelectorAll('.studio-settings-pane'))for(const p of [...pane.querySelectorAll(':scope > .panel,:scope > .apple-settings-pane > .panel,:scope > .apple-settings-pane > .voice-preferences')]){p.classList.add('wu-settings-card');if([product,presence,device].includes(p))continue;const paragraphs=[...p.children].filter(n=>n.matches('p.footnote,p.muted,pre')&&!n.hasAttribute('role'));if(paragraphs.length)p.append(details('자세히',paragraphs));}
 const calendar=$('studio-settings-calendar').querySelector('article'),calReminder=$('schedule-reminders'),calNotification=$('notification-permission');calendar.replaceChildren(el('header','wu-setting-title'));calendar.firstChild.append(el('h2','','캘린더'));calendar.append(row('연결 상태',chip('이 Mac의 일정','good')),row('일정 알림',switchStyle(calReminder,'일정 알림'),'등록한 시간에 아이리가 알려줘.'),row('등록된 일정',btn('일정 열기',()=>showPage('tasks'),'calendar')));if(calNotification)calendar.append(row('Mac 알림',calNotification));
 // General/voice sections are compact, with advanced art controls disclosed.
 const art=[...panes.querySelectorAll('article')].find(p=>p.querySelector('h2')?.textContent==='AIRI · 공간과 움직임');if(art){const wrapper=details('캐릭터·배경 자세히',[art]);$('studio-settings-general').append(wrapper);}
 const voice=$('voice-profile-panel');if(voice){const wrapper=details('목소리 테스트',[voice]);$('studio-settings-general').append(wrapper);}
 for(const input of panes.querySelectorAll('#spotify-client-id,#camera-username,#api-key,#telegram-token')){if(input.type!=='password')input.type='password';input.autocomplete='off';const reveal=iconBtn('입력값 표시 또는 가리기','check',()=>{input.type=input.type==='password'?'text':'password';});input.after(reveal);}
 // Study presets write to SQLite and start the existing chat workflow only on click.
 const study=pages.study,goal=$('studio-study-goal'),studyStart=[...study.querySelectorAll('button')].find(b=>b.classList.contains('primary')),skillsButton=[...study.querySelectorAll('button')].find(b=>b!==studyStart),language=el('div','wu-choice-row'),presets=el('div','wu-choice-row'),studyIntro=el('div','wu-study-intro'),studyFooter=el('div','wu-study-footer');
 for(const lang of ['한국어','영어','프랑스어']){const b=btn(lang,()=>{savePrefs({study_language:lang,study_goal:goal.value});syncStudy();});b.dataset.language=lang;language.append(b);}
 for(const text of ['TCF 말하기 · 하루 20분','자유 대화 · 하루 10분'])presets.append(btn(text,()=>{goal.value=text;goal.dispatchEvent(new Event('input',{bubbles:true}));}));
 studyIntro.append(icon('study'),el('h2','','오늘부터 뭘 같이 배울까?'),note('목표는 짧고 구체적일수록 좋아. 연습할 언어와 매일 쓸 시간을 정해보자.'));
 goal.onchange=()=>{savePrefs({study_goal:goal.value});};
 studyStart.onclick=async()=>{const text=goal.value.trim();if(await savePrefs({study_goal:text})){showPage('chat');submitChat(prefs.study_language+'로 '+(text||'자유 대화')+' 연습을 도와줘. 한 문제씩 진행해줘.');}};
 studyFooter.append(note('목표는 이 Mac에 저장돼.'),studyStart);study.replaceChildren(studyIntro,row('연습할 언어',language),row('이런 목표도 좋아',presets),row('나의 학습 목표',goal),studyFooter,skillsButton);
 function syncStudy(){goal.value=prefs.study_goal;for(const b of language.children)b.classList.toggle('selected',b.dataset.language===prefs.study_language);}
 // Files retain NAS actions, with an explicit image tab linked to the live gallery.
 $('image-studio-open').textContent='이미지 작업실 열기';
 const files=pages.files,fileNodes=[...files.children].filter(n=>!n.matches('.detail-title')),fileTabs=el('nav','wu-segments'),fileContent=el('div','wu-files-content'),imageTab=card('생성한 이미지','wu-image-intro');fileContent.append(...fileNodes.filter(n=>n.id!=='image-studio-open'));imageTab.append(note('만든 이미지와 프롬프트를 이미지 작업실에서 이어서 확인해.'),$('image-studio-open'));imageTab.hidden=true;for(const [id,text] of [['nas','내 자료'],['image','생성한 이미지']]){const b=btn(text,()=>{fileContent.hidden=id!=='nas';imageTab.hidden=id!=='image';for(const x of fileTabs.children)x.classList.toggle('selected',x===b);});if(id==='nas')b.classList.add('selected');fileTabs.append(b);}files.replaceChildren(fileTabs,fileContent,imageTab);
 function decorateMusic(c){const controls=c.querySelector('.spotify-device-controls'),bluetooth=c.querySelector('.homepod-open');if(!controls)return;const d=details('소리 출력',[controls,bluetooth]);c.append(d);}
 window.addEventListener('airi-home-cards',collectCards);
 collectCards();if(state)renderPlanner();
 const boot=setInterval(async()=>{if(!token)return;clearInterval(boot);try{prefs=await api('ui-preferences');ready=true;syncStudy();arrange();}catch(e){toast('위젯 설정 연결을 확인해 줘. '+e.message);}renderLibrary();loadWeather();},400);
 const weatherTimer=setInterval(()=>{if(prefs.widgets.includes('weather'))loadWeather();},600000);
 window.AIRIWidgetHost={
  install(def,node){const i=definitions.findIndex(d=>d[0]===def[0]);if(i<0)definitions.push(def);else definitions[i]=def;cards.get(def[0])?.remove();cards.set(def[0],node);arrange();renderLibrary();},
  decorate:decorateWidget,
  visible(id){return ready&&prefs.widgets.includes(id)&&!document.hidden&&body.dataset.appleView==='home'&&!prefs.collapsed.includes(id);},
  settings(category){window.AIRISettings.open(category);}
 };
 window.addEventListener('pagehide',()=>{clearInterval(boot);clearInterval(weatherTimer);});
 showPage('home');window.dispatchEvent(new CustomEvent('airi-layout'));
})();
