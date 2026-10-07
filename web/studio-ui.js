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
 const weather=el('section','context-card studio-weather');weather.append(icon('cloud'),el('div','','설정한 지역 날씨'),button('날씨 물어보기',()=>submitChat('설정한 지역 현재 날씨와 오늘 외출할 때 알아둘 점을 알려줘.')));left.append(weather);
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
  const study=column.querySelector('.learning-widget');if(study){left.querySelector('.learning-widget')?.remove();left.insertBefore(study,news);}
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
 let selected='general';function selectSettings(key){selected=panes[key]?key:'general';for(const [k,p] of Object.entries(panes))p.hidden=k!==selected;for(const b of newNav.children)b.setAttribute('aria-selected',String(b.dataset.category===selected));settings.querySelector('.apple-search-settings').value='';$('drawer-body').scrollTop=0;}
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
