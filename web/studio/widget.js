(()=>{'use strict';
 const researchStates={queued:'리포트 배정 대기',collecting:'리포트 자료 조사',drafting:'리포트 본문 작성',reviewing:'리포트 검수',awaiting_approval:'리포트 논지 승인 대기',awaiting_continue:'리포트 이어쓰기 대기',waiting_storage:'리포트 NAS 저장 대기',needs_sources:'리포트 근거 보완 필요',failed:'리포트 처리 실패',complete:'리포트 완료',limited:'리포트 완료 · 자료 제한',cancelled:'리포트 취소'};
 const researchStages={desk_topic:'검색 주제 정리',desk_extract:'원문 근거 추출',desk_notes:'핵심 근거 초안',desk_notes_review:'수치·출처 검수',desk_plan:'핵심 논지·목차 작성',desk_plan_review:'논지·추정 가정 검수',desk_draft:'보고서 본문 작성',desk_review:'본문 근거 검수',desk_holistic:'전체 논리 검수'};
 const ongoingResearch=new Set(['queued','collecting','drafting','reviewing','awaiting_approval','awaiting_continue','waiting_storage']);
 const runningResearch=new Set(['collecting','drafting','reviewing']);
 const stamp=v=>Number.isFinite(Date.parse(v))?Date.parse(v)/1000:0;
 function researchTitle(r){const text=String(r.options?.query||'투자 리포트');return (text.match(/주제:\s*([\s\S]*?)(?:\s*Report type:|$)/i)?.[1]||text).replace(/\s+/g,' ').slice(0,220);}
 function projectResearch(company,research,now=Date.now()/1000){
  // Merge independent, authenticated execution records; never start jobs here.
  const out=JSON.parse(JSON.stringify(company||{staff:[],counts:{}}));
  out.staff=out.staff||[];out.active_missions=out.active_missions||[];
  if(!Array.isArray(research?.workflows)){out.research_warning='리포트 실행 상태를 확인하지 못했어.';return out;}
  const reports=research.workflows.filter(r=>/^[a-f0-9]{32}$/.test(r.id)).sort((a,b)=>stamp(b.updated)-stamp(a.updated));
  const active=reports.filter(r=>ongoingResearch.has(r.state));
  out.research_as_of=now;out.research_warning=null;
  out.research_summary=active.length?(researchStates[active[0].state]||'리포트 상태 확인')+(active.length>1?' · '+active.length+'건':''):(researchStates[reports[0]?.state]||'');
  const ids=new Set(reports.map(r=>r.id));
  out.active_missions=out.active_missions.filter(m=>!ids.has(m.research_id)&&!ids.has(m.id));
  for(const r of active)out.active_missions.push({id:r.id,research_id:r.id,goal:researchTitle(r),status:r.state,label:researchStates[r.state],url:'/research-desk/?id='+r.id});
  for(const staff of out.staff){
   const node=['writer','ECON-M01'].includes(staff.id)?'M1':['research','ECON-M03'].includes(staff.id)?'M6':null;if(!node)continue;
   if(reports.some(r=>String(staff.current_task?.id||'').startsWith('research-'+r.id+'-'))){
    staff.current_task=null;staff.state=out.stale?'unknown':out.nodes?.some(n=>n.id===staff.node&&n.online)?'idle':'offline';
   }
   const assigned=reports.filter(r=>runningResearch.has(r.state)&&r.active_node===node);
   const r=assigned[0];
   if(r){const stage=String(r.progress||'').split(' · ').pop();
    const task={id:'research-'+r.id+'-active',research_id:r.id,role_id:staff.id,node:node.toLowerCase(),kind:'research',status:'running',title:researchTitle(r),created:stamp(r.created),progress:researchStages[stage]||researchStates[r.state],url:'/research-desk/?id='+r.id,result:'',error:''};
    // A live inference call is direct evidence of work, even if the separate office heartbeat is stale.
    if(staff.current_task&&staff.current_task.kind!=='research')staff.other_task=staff.current_task;
    staff.state='working';staff.current_task=task;staff.last_task=task;
   }else{
    const recent=reports.find(r=>(r.model_calls||[]).some(c=>(c.node==='M1'?'M1':'M6')===node));
    if(recent&&!staff.current_task&&stamp(recent.updated)>=(staff.last_task?.finished||staff.last_task?.created||0)){
     const call=[...recent.model_calls].reverse().find(c=>(c.node==='M1'?'M1':'M6')===node);
     staff.last_task={id:'research-'+recent.id+'-call',research_id:recent.id,kind:'research',title:researchTitle(recent),status:'completed',created:stamp(recent.created),result:(researchStages[call.stage]||call.stage)+' 완료 · '+String(call.actual_model||'로컬 모델')+' · '+String(call.seconds)+'초',url:'/research-desk/?id='+recent.id};
    }
   }
  }
  out.counts=Object.fromEntries(['working','queued','idle','offline','unknown'].map(key=>[key,out.staff.filter(s=>s.state===key).length]));
  return out;
 }
 if(typeof module!=='undefined'&&module.exports){module.exports={projectResearch};return;}
 const host=window.AIRIWidgetHost;if(!host)return;
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
 const names={working:'작업 중',queued:'배정 대기',idle:'대기',offline:'연결 끊김',unknown:'확인 필요'};
 const jobs={queued:'배정 대기',running:'작업 중',completed:'완료',failed:'실패',interrupted:'중단',cancelled:'취소'};
 const sprite={secretary:[1,0],research:[1,2],writer:[0,1],youtube:[0,2],business:[1,1],instagram:[1,3],designer:[2,0],developer:[2,1],editor:[2,2],strategy:[2,3]};
 const boxes=[[[165,349,127,315],[1241,360,179,290]],[[163,679,131,328],[1252,699,174,300]]];
 const extra=[[[136,13,140,298],[992,18,194,292]],[[133,320,141,305],[998,327,197,298]],[[128,634,136,304],[1003,638,198,298]],[[135,942,160,305],[987,947,209,287]]];
 const company=[[[97,11,156,293],[1016,15,145,289]],[[100,318,146,302],[1017,323,163,288]],[[96,632,153,300],[1019,633,150,298]],[[98,942,142,303],[1022,942,161,295]]];
 let data=null,companyData=null,inflight=false,disposed=false,sheet=null,selected=null,images=[],gridKey='',detailKey='';
 const card=make('article','wu-card dw-card tw-card'),head=make('header','wu-card-head'),title=make('h2','','AIRI Studio'),detail=make('button','dw-link','상세보기'),grid=make('div','tw-staff-grid'),line=make('p','tw-summary','직원 상태 확인 중'),foot=make('p','dw-fine');
 detail.type='button';detail.onclick=()=>openDetails();head.append(title,detail);card.append(head,line,grid,foot);
 function portrait(staff,large=false){const cv=make('canvas','tw-avatar');cv.width=large?160:96;cv.height=large?180:108;cv.setAttribute('aria-hidden','true');cv.dataset.role=staff.id;cv.dataset.state=staff.state;draw(cv);return cv;}
 function draw(cv){const key=cv.dataset.role;const fallback=Object.values(sprite)[[...key].reduce((n,c)=>n+c.charCodeAt(0),0)%10];const spec=sprite[key]||fallback;if(!spec)return;const [index,row]=spec,img=images[index];if(!img?.complete||!img.naturalWidth)return;const frame=cv.dataset.state==='working'?1:0,b=index===0?boxes[row-1]?.[frame]:index===1?extra[row][frame]:company[row][frame];if(!b)return;const ctx=cv.getContext('2d'),height=cv.height-6,width=height*b[2]/b[3];ctx.clearRect(0,0,cv.width,cv.height);ctx.imageSmoothingEnabled=true;ctx.drawImage(img,...b,(cv.width-width)/2,3,width,height);}
 function ensureImages(){if(images.length)return;images=['team-atlas-v1.png','team-extra-v1.png','team-company-v1.png'].map(name=>{const image=new Image();image.onload=()=>document.querySelectorAll('.tw-avatar').forEach(draw);image.src='/studio/'+name;return image;});}
 const time=v=>v?new Date(v*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'기록 없음';
 function widgetStaff(staff){if(staff.length<=10)return staff;const rank={working:0,queued:1,idle:2,offline:3,unknown:4};const active=[...staff].sort((a,b)=>(rank[a.state]??2)-(rank[b.state]??2));return active.slice(0,10);}
 function render(){
  if(data?.staff?.length)ensureImages();
  title.textContent=data?.name||'AIRI Studio';
  line.textContent=!data?.available?'직원 상태 확인 중':`총 ${data.staff?.length||0}명 · 작업 중 ${data.counts.working??0} · 배정 대기 ${data.counts.queued??0} · 대기 ${data.counts.idle??0}`+(data.stale?' · 회사 연결 지연':'');
  const key=JSON.stringify(data?.staff||[]);if(key!==gridKey){gridKey=key;grid.replaceChildren();for(const staff of widgetStaff(data?.staff||[])){const b=make('button','tw-person');b.type='button';b.dataset.state=staff.state;b.setAttribute('aria-label',staff.name+' · '+staff.node.toUpperCase()+' · '+names[staff.state]+' · '+staff.role);b.title=staff.current_task?.title||staff.role;b.append(portrait(staff),make('strong','',staff.name),make('small','',staff.node.toUpperCase()+' · '+names[staff.state]));b.onclick=()=>openDetails(staff.id);grid.append(b);}}
  foot.textContent=[data?.research_summary,data?.research_warning,data?.error].filter(Boolean).join(' · ')||(data?.available?'실제 실행 기록 · '+time(data.research_as_of||data.as_of)+' 기준':'AIRI Studio의 실제 업무 기록을 읽고 있어.');
  if(sheet?.open)renderDetails();
 }
 function renderDetails(){const key=JSON.stringify([selected,data?.staff,data?.stale,data?.active_missions]);if(key===detailKey)return;detailKey=key;const scroll=sheet.scrollTop,content=sheet.querySelector('.tw-detail-body');content.replaceChildren();
  content.append(make('p','tw-detail-note',data?.stale?'연결을 확인할 수 없어. 아래 내용은 마지막으로 받은 기록이야.':'AIRI Studio에서 확인한 실제 배정과 실행 결과야. 직원들은 각 Mac의 실행 자원을 나눠 써.'));
  for(const mission of data?.active_missions||[]){const p=make('p','tw-mission',(mission.label?mission.label+': ':mission.status==='planning'?'AIRI 목표 분배 중: ':mission.status==='reviewing'?'최종 검토 중: ':'진행 중인 회사 목표: ')+mission.goal);if(mission.url){const a=make('a','dw-link','진행 보기');a.href=mission.url;p.append(' ',a);}content.append(p);}
  for(const s of (data?.staff||[]).filter(s=>!selected||s.id===selected)){
   const a=make('article','tw-detail-person'),h=make('div','tw-detail-heading'),intro=make('div');intro.append(make('h3','',s.name+' · '+s.role),make('p','',s.node.toUpperCase()+' · '+names[s.state]));h.append(portrait(s,true),intro);a.append(h);
   if(s.current_task)a.append(make('p','tw-current','현재 업무: '+s.current_task.title),make('p','tw-detail-note',s.current_task.progress||''));
   if(s.other_task)a.append(make('p','tw-detail-note','별도 회사 업무: '+s.other_task.title));
   const task=s.current_task||s.last_task;if(task){a.append(make('p','tw-detail-note',(s.current_task?'작업':'최근 기록')+' · '+(jobs[task.status]||task.status)+' · '+time(task.finished||task.started||task.created)),make('p','',task.title));if(task.error)a.append(make('p','tw-error','실패·중단 이유: '+task.error));if(task.result){const result=make('pre','tw-result',task.result);a.append(result);}else if(!s.current_task)a.append(make('p','tw-detail-note','저장된 결과 본문은 없어.'));}else a.append(make('p','tw-detail-note','아직 배정된 업무 기록이 없어.'));content.append(a);
  }sheet.scrollTop=scroll;
 }
 function openDetails(id=null){selected=id;detailKey='';sheet?.remove();sheet=make('dialog','wu-sheet dw-dialog tw-dialog');const h=make('header','wu-sheet-head'),close=make('button','wu-button','닫기'),all=make('button','wu-button','전체 직원');close.type=all.type='button';close.onclick=()=>sheet.close();all.onclick=()=>{selected=null;renderDetails();};const research=make('a','wu-button','투자 리서치');research.href='/research-desk/';h.append(make('h2','','AIRI Studio · 직원 상황'),research,all,close);sheet.append(h,make('div','tw-detail-body'));const current=sheet;sheet.addEventListener('close',()=>{current.remove();if(sheet===current)sheet=null;},{once:true});document.body.append(sheet);renderDetails();sheet.showModal();poll(true);}
 async function poll(force=false){if(inflight||disposed||typeof token==='undefined'||!token||document.hidden||(!force&&!host.visible('studio')&&!sheet?.open))return;inflight=true;
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),7000);
  try{const read=async url=>{const response=await fetch(url,{headers:{'X-AIRI-Token':token},signal:abort.signal});if(!response.ok)throw Error();return response.json();};
   const [company,research]=await Promise.allSettled([read('/api/studio'),read('/api/research-desk')]);
   if(company.status==='fulfilled')companyData=company.value;
   else{companyData=JSON.parse(JSON.stringify(companyData||{staff:[],counts:{}}));companyData.stale=true;companyData.error='AIRI Studio 회사 연결 지연';companyData.staff=(companyData.staff||[]).map(s=>({...s,state:'unknown',current_task:null}));}
   data=projectResearch(companyData,research.status==='fulfilled'?research.value:null);
  }
  catch{data={...(companyData||{}),stale:true,error:'AIRI Studio 연결 지연 · 마지막 기록'};data.staff=(data.staff||[]).map(s=>({...s,state:'unknown',current_task:null}));}
  finally{clearTimeout(timeout);inflight=false;render();}
 }
 host.install(['studio','AIRI Studio','직원 아바타·현재 업무·최근 결과','home','right'],card);
 render();const timer=setInterval(()=>poll(),5000);document.addEventListener('visibilitychange',()=>poll());window.addEventListener('airi-widgets-changed',()=>poll());window.addEventListener('pagehide',()=>{disposed=true;clearInterval(timer);});poll();
})();
