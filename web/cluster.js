(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel'),status=el('p','muted','M1 작업자 확인 중…'),form=el('form');
 panel.append(el('h2','','M1 / 새 Mac 작업 분산 연결'),status,el('p','muted','M1은 문서 요약·번역·정리, 예약 글쓰기, 동일 모델이 있는 보고서 분석, 작업실 기획·검수를 맡아. 이 Mac은 실시간 대화·음성·카메라와 이미지·영상 생성을 맡아. 보고서는 기존 분석 모델과 같은 가중치가 M1에 있을 때 넘기고, 결과 검증과 PDF 저장은 이 Mac에서 해. M1 연결이 끊기면 같은 모델로 이 Mac에서 처리하되 대화·음성이 먼저야.'));
 const label=el('label','','M1에 백그라운드 작업 배정'),enabled=el('input');enabled.type='checkbox';label.prepend(enabled);
 const modelLabel=el('label','','예약 글쓰기 모델 · 보고서는 기존 분석 모델 유지'),model=el('select');modelLabel.append(model);
 const save=el('button','primary','분산 설정 저장'),test=el('button','secondary','M1 왕복 추론 테스트'),refresh=el('button','secondary','연결 확인');save.type='submit';test.type=refresh.type='button';form.append(label,modelLabel,save,test,refresh);panel.append(form);const office=el('a','secondary','M1 작업실 열기 ↗');office.href='/worker-office.html';office.target='_blank';office.rel='noopener';panel.append(office);page.append(panel);
 let loaded=false,busy=false;
 function show(s,fill=false){
  const state=s.connected?(s.state==='ollama_offline'?'SSH 연결됨 · M1 Ollama 실행 필요':'인증된 M1 작업자 연결됨'):s.state==='unconfigured'?'M1 페어링 필요':s.state==='checking'?'확인 중…':'M1 작업자 응답 없음';
  const job=s.active_job?.node?s.active_job:s.last_job;
  status.textContent=state+' · '+(s.hardware||'M1')+' · '+(s.routing.enabled?'분산 켜짐':'분산 꺼짐')+(job?.node?' · '+(s.active_job?.node?'현재 처리':'최근 작업')+': '+job.node+' / '+(job.purpose||'글쓰기')+' / '+job.model+(job.seconds!==undefined?' · '+job.seconds+'초':'')+(job.state&&job.state!=='completed'?' · '+job.state:'')+(job.fallback?' (이 Mac에서 처리)':''):'');
  if(fill||!loaded){enabled.checked=s.routing.enabled;model.replaceChildren();for(const name of [...new Set([s.routing.model,...(s.matching_models||[])])]){const o=el('option','',name);o.value=name;model.append(o);}model.value=s.routing.model;loaded=true;}
 }
 async function run(fn){busy=true;for(const b of [save,test,refresh])b.disabled=true;try{return await fn();}catch(e){status.textContent=e.message;return null;}finally{busy=false;for(const b of [save,test,refresh])b.disabled=false;}}
 form.onsubmit=async e=>{e.preventDefault();const r=await run(()=>api('cluster',{action:'save',enabled:enabled.checked,model:model.value}));if(r)show(r,true);};
 refresh.onclick=async()=>{const r=await run(()=>api('cluster',{action:'refresh'}));if(r)show(r,true);};
 test.onclick=async()=>{status.textContent='M1에서 테스트 응답을 기다리는 중…';const r=await run(()=>api('cluster',{action:'test'}));if(r)status.textContent=r.message+' · '+r.hardware+' · '+r.model;};
 const timer=setInterval(async()=>{if(!token)return;clearInterval(timer);const r=await run(()=>api('cluster'));if(r)show(r,true);},500);
 setInterval(async()=>{if(!token||busy||document.hidden)return;try{show(await api('cluster'));}catch{}},15000);
})();
