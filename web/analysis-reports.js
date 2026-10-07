/* NAS reports: saved PDFs, one reader across tabs, sentence-sized voice playback. */
(()=>{
 'use strict';
 const owner=crypto.randomUUID();let current=null,polling=false,stopped=false,heartbeat=null,lastSignature='';
 const host=el('section','console-panel'),heading=el('h3','','분석 보고서 · PDF'),list=el('div'),status=el('p','subtle','NAS 저장 후 자동으로 읽어줄게.');
 const dashboard=el('section','console-panel');dashboard.id='airi-research-dashboard';
 const deskLink=el('a','secondary','Research Desk · 근거·논지 승인');deskLink.href='/research-desk/';deskLink.target='_blank';deskLink.rel='noopener';heading.append(deskLink);
 host.id='airi-analysis-reports';host.append(heading,status,dashboard,list);($('console-news')?.parentElement||document.body).append(host);
 const interrupt=()=>{if(current){stopped=true;status.textContent='낭독을 멈추는 중…';}};
 window.addEventListener('airi-report-interrupt',interrupt);
 function idle(){return !busy&&!transcribing&&!voiceStarting&&!window.airiFocus&&!window.airiBrowserSpeech&&!(recorder&&!wakeWaiting)&&!(typeof newsBriefingBusy!=='undefined'&&newsBriefingBusy)&&!(typeof reminderPolling!=='undefined'&&reminderPolling)&&(!document.hidden||window.airiDesktop);}
 async function download(item){
  const response=await fetch(item.url,{headers:{'X-AIRI-Token':token}});
  if(!response.ok){const r=await response.json();throw Error(r.error||'PDF를 열지 못했어.');}
  const url=URL.createObjectURL(await response.blob()),a=el('a');a.href=url;a.download=item.filename;a.textContent=item.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
 }
 let dashboardSignature='';
 function showDashboard(data){
  const signature=JSON.stringify(data);if(signature===dashboardSignature)return;dashboardSignature=signature;dashboard.replaceChildren();if(!data)return;
  const synthesis=data.synthesis;
  dashboard.append(el('h3','',data.company?'COMPANY EXECUTIVE DASHBOARD · '+data.company:'AIRI MARKET INTELLIGENCE'));
  dashboard.append(el('p','',(data.company?'':synthesis?'Daily move: '+synthesis.daily_move.classification+' · ':data.market_character+' · ')+data.signal+' · Confidence '+data.confidence));
  if(synthesis){
   dashboard.append(el('h4','','BROADER MARKET REGIME'));
   for(const [name,value] of Object.entries(synthesis.market_regime))dashboard.append(el('p','',name+': '+value.classification+' · '+value.confidence.level));
  }
  const grid=el('div');grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px';
  const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:2}):'Not Available';
  for(const k of (data.company?data.kpis:data.market)){
   const card=el('div','item');card.style.cssText='display:block;padding:10px;border:1px solid #8293a655;border-radius:10px';
   card.append(el('strong','',k.metric||k.label),el('p','',number(k.value??k.current)+' '+(k.unit||k.currency||'')));
   card.append(el('small','',data.company?(k.period_end||'미확보')+' '+(k.frequency||''): 'Daily '+number(k.daily_change)+(k.change_unit||'%')+' · 5D '+number(k.change_5d)+' · 20D '+number(k.change_20d)));
   if(k.observed_at)card.append(el('small','',k.observed_at+(k.stale?' · stale':'')));grid.append(card);
  }
  dashboard.append(grid,el('h4','',synthesis?'WHAT ACTUALLY MATTERS TODAY':'TOP 3 THINGS TO KNOW'));
  if(synthesis){
   for(const d of synthesis.top_developments){dashboard.append(el('strong','',d.title+' · '+d.status),el('p','',d.evidence_summary||d.text),el('p','',d.why_it_matters),el('small','','관점 변경 조건: '+d.invalidation));}
   dashboard.append(el('p','','주요 위험: '+synthesis.primary_risk.text));
   const c=synthesis.next_catalysts[0];dashboard.append(el('p','','다음 일정: '+(c?c.date+' '+(c.time||'시각 미확인')+' '+c.event:'Date Not Verified')));
  }else for(const text of data.top3||[])dashboard.append(el('p','',text));
  if(!data.top3?.length)dashboard.append(el('p','subtle','검증된 핵심 판단이 부족해. PDF의 데이터와 미확보 항목을 확인해 줘.'));
  const c=data.article_counts;dashboard.append(el('small','',`기사 검토 ${c.reviewed_articles} = 수록 ${c.included_articles} + 제외 ${c.excluded_articles} · 기사 출처 ${c.source_count} · 데이터셋 ${data.dataset_count??0} · 검증 ${data.validation.ok?'통과':'실패'}`));
 }
 function show(rows){
  const signature=JSON.stringify(rows.map(r=>[r.id,r.state,r.position]));if(signature===lastSignature)return;lastSignature=signature;list.replaceChildren();
  for(const item of rows.slice(0,6)){
   const row=el('div','item'),body=el('div','item-content');body.append(el('strong','',item.filename),el('p','',item.title));
   body.append(el('small','',({'pending':'낭독 대기','reading':'읽는 중','paused':'일시 정지','done':'낭독 완료'}[item.state]||item.state)+' · '+item.position+'/'+item.total+' 문장'));
   const open=el('button','secondary','PDF 열기');open.onclick=()=>download(item).catch(e=>toast(e.message));body.append(open);
   const read=el('button','secondary',item.state==='done'?'다시 읽기':'이어 읽기');read.disabled=!!current||item.state==='reading';read.onclick=async()=>{try{await window.AIRIVoicePlayer?.unlock();await readReport(item.id,true);}catch(e){toast(e.message);}};body.append(read);row.append(body);list.append(row);
  }
 }
 const stop=el('button','secondary','보고서 낭독 정지');stop.hidden=true;stop.onclick=()=>interruptSpeech();host.append(stop);
 async function readReport(id,manual=false){
  if(current||!idle()||(!manual&&!$('auto-speak').checked))return;
  const claimed=await api('reports',{action:'claim',owner,...(id?{id}:{})});if(!claimed.report)return;
  current={id:claimed.report.id,lease:claimed.lease};window.airiReportReading=true;stopped=false;stop.hidden=false;
  const credentials=()=>({owner,...current});let done=false,resume=false;
  try{
   resume=!!recorder&&wakeWaiting;if(resume)await stopListening(false);
   heartbeat=setInterval(()=>{if(current)api('reports',{action:'heartbeat',...credentials()}).catch(()=>{stopped=true;window.AIRIVoicePlayer?.stop();});},30000);
   while(!stopped){
    if(busy||transcribing||window.airiFocus||(!manual&&!$('auto-speak').checked)||(document.hidden&&!window.airiDesktop))break;
    const chunk=await api('reports',{action:'chunk',...credentials()});if(stopped)break;
    status.textContent=claimed.report.filename+' · '+(chunk.position+1)+'/'+chunk.total+' 문장 읽는 중';
    if(chunk.text){const result=await api('speak',{text:chunk.text,reportNarration:true});if(stopped||result.cancelled)break;}
    const progress=await api('reports',{action:'advance',position:chunk.position,...credentials()});if(progress.done){done=true;status.textContent=claimed.report.filename+' · 전부 읽었어.';break;}
   }
  }catch(e){status.textContent='낭독 일시 정지 · '+e.message;}
  finally{
   clearInterval(heartbeat);
   if(!done){await api('reports',{action:'pause',...credentials()}).catch(()=>{});if(stopped)status.textContent='낭독을 멈췄어. 이어 읽기를 누르면 계속할게.';}
   current=null;window.airiReportReading=false;stop.hidden=true;
   if(resume&&!recorder&&!busy&&!transcribing&&voiceSession)startListening(true);
   await update(false);
  }
 }
 async function update(auto=true){
  if(polling||!token||(document.hidden&&!window.airiDesktop))return;polling=true;
  try{const data=await api('reports');show(data.reports);showDashboard(data.dashboard);if(auto&&!current&&data.reports.some(r=>r.state==='pending'))setTimeout(()=>readReport().catch(e=>{status.textContent=e.message;}),0);}
  catch(e){status.textContent='보고서 연결 확인 중 · '+e.message;}finally{polling=false;}
 }
 window.addEventListener('airi-chat-finished',()=>update());
 window.addEventListener('pagehide',()=>{stopped=true;});
 setInterval(update,8000);update();
})();
