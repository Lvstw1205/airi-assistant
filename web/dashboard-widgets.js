(()=>{
 'use strict';
 const host=window.AIRIWidgetHost,policy=window.AIRIDashboardPolicy;if(!host||!policy)return;
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,cls='')=>{const n=make('button','wu-button '+cls,label);n.type='button';n.onclick=fn;return n;};
 const fine=text=>make('p','dw-fine',text);
 const numeric=v=>v===null||v===undefined||v===''||!Number.isFinite(Number(v))?null:Number(v);
 const percent=v=>numeric(v)===null?'—':numeric(v).toFixed(1)+'%';
 const temp=v=>numeric(v)===null?'—':numeric(v).toFixed(1)+'°C';
 const gb=v=>numeric(v)===null?'—':(numeric(v)/1073741824).toFixed(1);
 const money=v=>numeric(v)===null?'—':numeric(v).toLocaleString('en-CA',{minimumFractionDigits:2,maximumFractionDigits:2});
 const stamp=v=>numeric(v)===null?'측정 전':new Date(v*1000).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
 const statusNames={ready:'연결됨',loading:'확인 중',stale:'갱신 중',offline:'연결 끊김',unavailable:'조회 불가',setup_required:'측정 프로그램 미설치'};
 const pressureNames={nominal:'정상',fair:'약간 높음',serious:'높음',critical:'매우 높음',unknown:'측정 불가'};
 function card(title,id){const c=make('article','wu-card dw-card'),h=make('header','wu-card-head'),content=make('div','dw-content');h.append(make('h2','',title));c.append(h,content);return {c,h,content,id};}
 const mac=card('내 Mac','mac-status'),stock=card('Stock101','stock101');
 let metrics=null,trading=null,macError='',stockError='',tradeBusy=false,macFlight=null,stockFlight=null,disposed=false,dialog=null;
 function detailsLink(mode){const a=make('a','dw-link','상세보기 ↗');a.href='/stock101'+(mode?'#'+mode:'');a.target='_blank';a.rel='noopener';a.setAttribute('aria-label',mode==='live'?'실제매매 상세보기':mode==='overview'?'모의매매 상세보기':'Stock101 상세보기');return a;}
 mac.h.append(button('새로고침',()=>loadMac(true),'dw-refresh'));
 stock.h.append(detailsLink());
 function meter(value,label){const m=make('meter','dw-meter');m.min=0;m.max=100;m.value=numeric(value)??0;m.setAttribute('aria-label',label);if(numeric(value)===null){m.classList.add('dw-unknown');m.setAttribute('aria-hidden','true');}return m;}
 function usage(label,value){const box=make('div','dw-usage');box.append(make('span','dw-label',label),make('strong','dw-value',percent(value)),meter(value,label+' 사용률'));return box;}
 function macNode(d){
  const shownState=macError?'unavailable':d.stale&&d.state==='ready'?'stale':d.state;
  const box=make('section','dw-mac-node'+(d.stale||macError?' dw-stale':'')+(!d.cpu?' dw-no-sample':'')),head=make('div','dw-node-head'),badge=make('span','dw-badge',statusNames[shownState]||'확인 중');badge.dataset.state=shownState;
  const title=make('h3','',d.node);head.append(title,badge);box.append(head);
  const stats=make('div','dw-mac-grid');stats.append(usage('CPU',d.cpu?.used_percent),usage('GPU',d.gpu?.used_percent));box.append(stats);
  const ram=make('div','dw-memory'),r=d.ram||{};ram.append(make('span','dw-label','RAM'),make('strong','',r.total_bytes?gb(r.used_bytes)+' / '+gb(r.total_bytes)+' GB':'—'),make('span','dw-fine',percent(r.used_percent)));box.append(ram,meter(r.used_percent,d.node+' RAM 사용률'));
  const temperatures=make('div','dw-temperatures');temperatures.append(make('span','','CPU '+temp(d.temperature?.cpu_c)),make('span','','GPU '+temp(d.temperature?.gpu_c)));box.append(temperatures);
  if(d.state==='setup_required')box.append(fine('CPU·RAM·온도 측정 프로그램 설치 대기'));
  else box.append(fine((d.stale||macError?'마지막 측정 · ':'')+stamp(d.sampled_at)+' · 열 상태 '+(pressureNames[d.thermal_pressure]||'측정 불가')));
  if(d.node==='M1'){const w=metrics?.worker;box.append(fine(!w?'작업자 확인 중':w.stale?'작업자 상태 재확인 중':!w.connected?'작업자 연결 끊김':w.active_job?.node?'실행 중 · '+w.active_job.purpose:'작업자 연결됨 · 현재 대기'));}
  return box;
 }
 function renderMac(){mac.content.replaceChildren();for(const name of ['M6','M1'])mac.content.append(macNode(metrics?.nodes?.find(n=>n.node===name)||{node:name,state:macError?'unavailable':'loading',stale:true}));
  const foot=make('div','dw-foot');foot.append(fine(macError||'10초마다 갱신 · 온도는 센서 평균'),button('작업실 ↗',()=>window.open('/worker-office.html','_blank','noopener')),button('측정 기준',()=>{const d=newDialog('Mac 측정 기준');d.append(fine(metrics?.source_note||'전체 코어 CPU 평균, GPU 드라이버 사용률과 통합 메모리를 표시해. 측정할 수 없는 값은 —로 표시해.'),fine('화면에 위젯이 보일 때만 갱신해. 연결이 끊기면 지난 측정값임을 표시하고 0으로 바꾸지 않아.'));}));mac.content.append(foot);}
 const reasons={USER_STOP:'직접 중지됨',STARTUP_CONFIRMATION_REQUIRED:'시작 확인 필요',STARTUP_RECONCILIATION_REQUIRED:'재시작 후 확인 중',STOP_AND_RECONCILE_LIVE_FIRST:'실제매매 중지·주문 확인 필요',LOSS_LIMIT:'손실 한도 도달',RISK_CALCULATION_FAILED:'위험 계산 확인 필요',LIVE_REQUIREMENTS_NOT_MET:'실제매매 설정·잔액 확인 필요',LOCAL_LIVE_CONFIRMATION_REQUIRED:'실제 자금 사용 확인 필요'};
 function reason(text){return reasons[text]||(text?'상세보기에서 상태 확인':'');}
 function renderStock(){
  stock.content.replaceChildren();
  for(const mode of ['paper','live']){
   const n=trading?.[mode],box=make('section','dw-trade-node'),head=make('div','dw-node-head'),title=make('div');title.append(make('h3','',mode==='paper'?'모의매매':'실제매매'),make('span','dw-fine',mode==='paper'?'가상 자금':'내 Coinbase 자금'));
   const control=make('input','wu-switch');control.type='checkbox';control.checked=!!n?.enabled;control.disabled=tradeBusy||!n?.available||!!stockError;control.setAttribute('role','switch');control.setAttribute('aria-label',(mode==='paper'?'모의매매':'실제매매')+' 켜기·끄기');control.onchange=()=>requestTrade(mode,control.checked);head.append(title,control);box.append(head);
   const label=stockError?'확인 불가':!n?.available?'확인 중':n.running?'실행 중':n.enabled?'복구 대기':'꺼짐';const badge=make('span','dw-badge',label);badge.dataset.state=stockError?'unavailable':n?.running?'ready':n?.enabled?'loading':'stopped';box.append(badge);
   const m=n?.money||{},pnl=make('div','dw-pnl');pnl.append(make('span','dw-label','계좌 전체 평가손익'),make('strong',numeric(m.pnl_cad)>0?'dw-positive':numeric(m.pnl_cad)<0?'dw-negative':'',money(m.pnl_cad)+(m.pnl_cad!=null?' CAD':'')),make('span','dw-fine',m.pnl_percent!=null?percent(m.pnl_percent):'평가 기록 대기'));box.append(pnl);
   const line=make('div','dw-value-line');line.append(make('span','dw-label','총 '+(mode==='paper'?'가상 ':'')+'평가액'),make('span','',money(m.equity_cad)+(m.equity_cad!=null?' CAD':'')));box.append(line);
   if(n?.last_product)box.append(fine('최근 판단 · '+n.last_product+' · '+stamp(n.last_assessment_at)));
   const why=mode==='live'&&n?.available&&!n.configured?'계정·예산 연결 설정 필요':reason(n?.reason);if(why&&!n?.running)box.append(fine(why));
   const foot=make('div','dw-foot');foot.append(fine(m.as_of?'장부 평가 '+stamp(m.as_of):'평가 기록 없음'),detailsLink(mode==='paper'?'overview':'live'));box.append(foot);stock.content.append(box);
  }
  const info=make('div','dw-foot');info.append(fine(stockError||'10초마다 상태 확인 · 평가는 표시 시각 기준'),button('새로고침',()=>loadStock(true),'dw-refresh'));stock.content.append(info);
 }
 async function request(path){const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),12000);try{const r=await fetch('/api/'+path,{headers:{'X-AIRI-Token':token},signal:ctrl.signal});const data=await r.json();if(!r.ok)throw Error(data.error||'연결 확인 필요');return data;}finally{clearTimeout(timer);}}
 async function loadMac(force=false){if(macFlight)return macFlight;if(!token||disposed||(!force&&!host.visible(mac.id)))return;macFlight=(async()=>{try{metrics=await request('mac-metrics');macError='';}catch{macError='연결 지연 · 마지막 측정값';}finally{renderMac();macFlight=null;}})();return macFlight;}
 async function loadStock(force=false){if(stockFlight)return stockFlight;if(!token||disposed||(!force&&!host.visible(stock.id)))return;stockFlight=(async()=>{try{trading=await request('stock101-widget');stockError='';}catch{stockError='상태 연결 지연 · 제어 잠김';}finally{renderStock();stockFlight=null;}})();return stockFlight;}
 function newDialog(title){dialog?.remove();dialog=make('dialog','wu-sheet dw-dialog');const h=make('header','wu-sheet-head');h.append(make('h2','',title),button('닫기',()=>dialog.close()));dialog.append(h);const opened=dialog;dialog.addEventListener('close',()=>opened.remove(),{once:true});document.body.append(dialog);dialog.showModal();return dialog;}
 function liveConfirm(){
  const d=newDialog('실제 자동매매 켜기'),n=trading.live;
  d.append(fine('시작하면 모의매매를 중지하고, 기존 설정에 따라 실제 Coinbase 자금으로 자동 주문해.'),fine('총 예산 한도 '+money(n.budget_cap_cad)+' CAD · 거래 통화 '+(n.quote||'설정 필요')));
  if(!n.configured){d.append(fine('계정과 예산 설정을 먼저 완료해 줘.'),detailsLink('live'));return;}
  const limits=n.risk_limits||{},risk=make('div','dw-risk');
  for(const [key,label] of [['single_order','주문당 최대'],['daily_loss','하루 손실 중지'],['drawdown','최대 낙폭 중지'],['cash_reserve','최소 현금']]){const v=numeric(limits[key]);if(v!==null)risk.append(fine(label+' '+percent(v*100)));}
  d.append(risk,detailsLink('live'));const agree=make('label','dw-agree'),check=make('input');check.type='checkbox';agree.append(check,document.createTextNode('실제 돈으로 주문하며 손실 가능성과 기존 예산·비용·위험 한도를 확인했어.'));d.append(agree);
  const label=make('label','dw-phrase','아래 문구를 직접 입력해 줘'),field=make('input','wu-field');field.autocomplete='off';field.placeholder=policy.phrase;label.append(field);d.append(label);let submitting=false;const error=fine(''),start=button('실제매매 시작',async()=>{if(submitting)return;submitting=true;tradeBusy=true;start.disabled=true;renderStock();try{await performTrade('live',true,{confirmed:check.checked,confirmation:field.value});d.close();}catch(e){error.textContent=reasons[e.message]||e.message;}finally{submitting=false;tradeBusy=false;renderStock();start.disabled=!(check.checked&&field.value===policy.phrase);}},'primary');start.disabled=true;
  const changed=()=>{start.disabled=submitting||!(check.checked&&field.value===policy.phrase);};check.onchange=changed;field.oninput=changed;d.append(error,start,button('취소',()=>d.close()));
 }
 async function performTrade(mode,desired,confirmation={}){
  const fresh=await request('stock101-widget');trading=fresh;
  const action=policy.tradeAction(mode,desired,fresh,confirmation);if(action)await api('stock101',{action,...confirmation});
  await loadStock(true);
 }
 async function requestTrade(mode,desired){
  if(tradeBusy)return;tradeBusy=true;renderStock();
  try{if(mode==='live'&&desired){trading=await request('stock101-widget');if(!trading.live.available)throw Error('실제매매 상태를 확인할 수 없어.');liveConfirm();}else await performTrade(mode,desired);}
  catch(e){toast(reasons[e.message]||e.message);}
  finally{tradeBusy=false;renderStock();}
 }
 host.install(['mac-status','내 Mac','M6·M1 CPU·GPU·RAM과 온도','home','left'],mac.c);
 host.install(['stock101','Stock101','모의·실제매매 상태와 켜기·끄기','stock101','right'],stock.c);
 renderMac();renderStock();
 const poll=()=>{loadMac();loadStock();};
 const timer=setInterval(poll,10000);
 document.addEventListener('visibilitychange',poll);window.addEventListener('airi-widgets-changed',poll);
 new MutationObserver(poll).observe(document.body,{attributes:true,attributeFilter:['data-apple-view']});
 window.addEventListener('pagehide',()=>{disposed=true;clearInterval(timer);});
 poll();
})();

/* Fit the user's home widgets into the desktop viewport without changing preferences. */
(()=>{
 'use strict';
 const body=document.body,space=document.querySelector('.wu-workspace');if(!space)return;
 let queued=false,reset=true;
 const columns=()=>[...space.querySelectorAll('.wu-column')];
 const tooTall=()=>columns().some(c=>{
  const cards=[...c.children].filter(n=>n.classList.contains('wu-home-card'));
  if(!cards.length)return false;
  return cards.at(-1).getBoundingClientRect().bottom>space.getBoundingClientRect().bottom+1;
 });
 function fit(){
  queued=false;if(document.hidden||body.dataset.appleView!=='home')return;
  if(reset){delete body.dataset.widgetDensity;reset=false;}
  if(tooTall()&&!body.dataset.widgetDensity)body.dataset.widgetDensity='compact';
  if(tooTall())body.dataset.widgetDensity='tight';
 }
 function schedule(startOver=false){reset=reset||startOver;if(!queued){queued=true;requestAnimationFrame(fit);}}
 const changes=new MutationObserver(()=>schedule());changes.observe(space,{childList:true,subtree:true,characterData:true});
 const view=new MutationObserver(()=>schedule(true));view.observe(body,{attributes:true,attributeFilter:['data-apple-view']});
 window.addEventListener('resize',()=>schedule(true));window.addEventListener('airi-widgets-changed',()=>schedule(true));document.addEventListener('visibilitychange',()=>schedule(true));
 // Expanded weather/audio controls open above the desktop instead of pushing cards below it.
 space.addEventListener('click',event=>{
  const summary=event.target.closest('details.wu-details > summary');if(!summary||!body.dataset.widgetDensity)return;
  const original=summary.parentElement;event.preventDefault();
  const sheet=document.createElement('dialog');sheet.className='wu-sheet dw-dialog';
  const header=document.createElement('header');header.className='wu-sheet-head';
  const title=document.createElement('h2');title.textContent=summary.textContent;
  const close=document.createElement('button');close.className='wu-button';close.textContent='닫기';close.onclick=()=>sheet.close();header.append(title,close);sheet.append(header);
  const nodes=[...original.children].filter(n=>n!==summary);sheet.append(...nodes);
  sheet.addEventListener('close',()=>{original.append(...nodes);sheet.remove();},{once:true});document.body.append(sheet);sheet.showModal();
 });
 window.addEventListener('pagehide',()=>{changes.disconnect();view.disconnect();});schedule(true);
})();
