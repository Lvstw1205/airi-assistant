/* Explicit home guard, local face enrollment and bounded visitor conversation. */
(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel camera-motion'),status=el('p','muted','홈캠 감시 상태 확인 중…'),last=el('p','muted','');status.setAttribute('role','status');
 panel.id='homecam-presence-panel';panel.append(el('h2','','카메라 2 · 얼굴 등록과 방문자 경고'),status,last);
 const controls=el('div','form-actions home-guard-controls'),on=el('button','primary','감시 켜기'),off=el('button','secondary','감시 끄기'),test=el('button','secondary','연결 확인');controls.append(on,off,test);panel.append(controls);
 panel.append(el('p','','미등록 얼굴 확인 → “너 시발 누구야, 너의 정체를 말해라” → 홈캠 마이크로 대답 듣기 → Mac 스피커로 응답'));
 panel.append(el('p','muted','AIRI 채팅·텔레그램의 “홈캠 감시 켜 / 꺼” 또는 위 버튼으로 시작·중지해. 선명한 얼굴을 3번 확인하고, 입장마다 한 번 인사해. 방문자 대화는 최대 3번, 한 번에 15초 동안 대답을 기다려.'));
 const dialogue=el('p','muted');dialogue.setAttribute('role','status');panel.append(dialogue);
 const form=el('div','home-family-form'),kind=el('select'),name=el('input'),title=el('input');
 for(const [v,t] of [['owner','User 얼굴'],['family','가족 얼굴']]){const option=el('option','',t);option.value=v;kind.append(option);}
 kind.setAttribute('aria-label','얼굴 등록 대상');name.setAttribute('aria-label','가족 이름');name.placeholder='가족 이름 · 예: 엄마';name.maxLength=24;title.setAttribute('aria-label','인사할 호칭');title.placeholder='부를 호칭 · 예: 애미';title.maxLength=24;
 form.append(kind,name,title);panel.append(form);name.hidden=title.hidden=true;kind.onchange=()=>{name.hidden=title.hidden=kind.value!=='family';};
 const buttons=el('div','form-actions'),enroll=el('button','secondary','얼굴 등록 시작'),sample=el('button','primary','정면 얼굴 등록'),cancel=el('button','secondary','등록 취소'),forget=el('button','secondary','User 얼굴 삭제');sample.hidden=cancel.hidden=true;
 buttons.append(enroll,sample,cancel,forget);panel.append(buttons);
 const family=el('div','home-family-list');family.setAttribute('aria-label','등록된 가족');panel.append(family);
 panel.append(el('p','muted','등록할 사람 혼자 정면·왼쪽·오른쪽 얼굴을 보여 줘. 가족 이름·호칭은 직접 지정해. 얼굴 특징값은 이 Mac에만 저장하고, 가족 등록이나 말로 한 자기소개는 기기 제어 권한을 주지 않아.'));
 page.append(panel);let busy=false;
 function show(s){
  forget.disabled=!s.registered;
  const enrolling=s.enrolling===true;sample.hidden=cancel.hidden=!enrolling;enroll.disabled=kind.disabled=name.disabled=title.disabled=enrolling;
  if(enrolling){kind.value=s.enrollment_target?'family':'owner';if(s.enrollment_target){name.value=s.enrollment_target.name;title.value=s.enrollment_target.greeting_name;}sample.textContent=s.pending_samples===1?'살짝 왼쪽 얼굴 등록 (2/3)':s.pending_samples===2?'살짝 오른쪽 얼굴 등록 (3/3)':'정면 얼굴 등록 (1/3)';}
  name.hidden=title.hidden=kind.value!=='family';
  const rows=[];for(const p of s.family||[]){const row=el('div','form-actions'),label=el('span','',p.name+' → “안녕하세요, '+p.greeting_name+'”'),remove=el('button','secondary','등록 삭제');remove.type='button';remove.onclick=async()=>{if(!confirm(p.name+'의 얼굴 등록을 삭제할까? 다음부터 미등록 방문자로 확인될 수 있어.'))return;try{show(await api('camera-presence',{action:'forget_family',id:p.id}));}catch(e){last.textContent=e.message;}};row.append(label,remove);rows.push(row);}
  family.replaceChildren(...rows);if(!rows.length)family.append(el('p','muted','등록된 가족이 없어. 가족 얼굴과 인사할 호칭을 추가해.'));
 }
 async function load(){if(!token||busy)return;try{const s=await api('camera-automation');show(s);status.dataset.guard=s.home_active?'active':s.home_armed?'pending':'off';status.textContent=(s.home_active?'감시 중':s.home_armed?'감시 준비 / 연결 확인':'감시 꺼짐')+' · '+s.home_state+' · User '+(s.registered?'등록됨':'등록 필요');
  on.disabled=s.home_armed;off.disabled=!s.home_armed;const v=s.visitor_dialogue||{};dialogue.textContent='경고 음성 '+(v.warning_ready?'준비됨':'준비 전')+' · '+(v.state||'대기')+(v.error?' · '+v.error:'')+(v.last_heard?'\n방문자: '+v.last_heard:'')+(v.last_reply?'\n아이리: '+v.last_reply:'');
 }catch(e){status.dataset.guard='error';status.textContent=e.message;}}
 async function arm(enabled){busy=true;on.disabled=off.disabled=true;try{await api('camera-automation',{action:'home_guard',enabled});last.textContent=enabled?'첫 영상과 경고 목소리를 준비 중이야. 실제 연결 상태는 위에 표시돼.':'홈캠 감시와 방문자 대화를 중지했어.';}catch(e){last.textContent=e.message;}finally{busy=false;await load();}}
 on.onclick=()=>arm(true);off.onclick=()=>arm(false);
 test.onclick=async()=>{test.disabled=true;try{const r=await api('camera-automation',{action:'test'});last.textContent=r.message+(r.fresh?' · 새 영상 확인':' · 첫 연결 준비 중');}catch(e){last.textContent=e.message;}finally{test.disabled=false;}};
 enroll.onclick=async()=>{try{await window.AIRICameraMotion?.stop();show(await api('camera-presence',{action:'enroll_begin',kind:kind.value,name:name.value,greeting_name:title.value}));sample.hidden=cancel.hidden=false;sample.textContent='정면 얼굴 등록 (1/3)';last.textContent='등록할 사람 혼자 홈캠 앞에 가까이 서 줘. 등록 중에는 방문자 경고를 잠시 멈춰.';}catch(e){last.textContent=e.message;}};
 sample.onclick=async()=>{sample.disabled=true;try{const s=await api('camera-presence',{action:'enroll_sample'});show(s);if(!s.enrolling){sample.hidden=cancel.hidden=true;last.textContent='얼굴 등록 완료. 감시를 켜면 다음 입장부터 등록한 호칭으로 인사해.';}else{sample.textContent=s.pending_samples===1?'살짝 왼쪽 얼굴 등록 (2/3)':'살짝 오른쪽 얼굴 등록 (3/3)';last.textContent='같은 사람의 얼굴을 다른 각도에서 보여 줘.';}}catch(e){last.textContent=e.message;}finally{sample.disabled=false;}};
 cancel.onclick=async()=>{try{show(await api('camera-presence',{action:'enroll_cancel'}));sample.hidden=cancel.hidden=true;last.textContent='얼굴 등록을 취소했어.';}catch(e){last.textContent=e.message;}};
 forget.onclick=async()=>{if(!confirm('User 얼굴 등록을 삭제할까? 감시는 중지되고 다시 등록해야 해.'))return;try{await api('camera-automation',{action:'home_guard',enabled:false});show(await api('camera-presence',{action:'forget'}));await load();}catch(e){last.textContent=e.message;}};
 setTimeout(load,1200);setInterval(()=>{if(!document.hidden&&panel.getClientRects().length)load();},1500);
})();
