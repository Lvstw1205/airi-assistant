/* One computer is the default. Extra compute devices are explicitly paired. */
(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel devices-panel');panel.id='device-connections';
 const head=el('div','device-heading'),title=el('div');
 title.append(el('h2','','기기 연결 · 메인 자동 선택'),el('p','muted','컴퓨터 한 대로 시작하세요. 더 필요할 때 기기만 추가하면 됩니다.'));
 const add=el('button','primary','＋ 기기 추가');add.type='button';head.append(title,add);
 const summary=el('div','device-main','기기를 확인하고 있어요…');summary.setAttribute('role','status');
 const list=el('div','device-list'),refreshButton=el('button','secondary','연결 다시 확인');refreshButton.type='button';
 const detail=el('p','muted','대화와 AI 작업의 메인 기기는 자동으로 선택됩니다. 화면·기록·카메라·파일 작업은 AIRI를 실행한 이 컴퓨터에 남습니다.');
 const form=el('form','device-pair-form');form.hidden=true;
 const guide=el('ol');for(const text of ['추가할 컴퓨터에 AIRI와 Ollama를 설치하고 같은 로컬 모델을 준비하세요.','추가할 컴퓨터에서 아래 명령을 실행하세요. Mac은 Start Worker.command를 열어도 됩니다.','나오는 연결 코드를 아래에 붙여넣으세요. 등록한 기기로 대화 내용이 암호화되어 전달됩니다.'])guide.append(el('li','',text));
 const command=el('code','','python run.py --device-worker'),nameLabel=el('label','','기기 이름 · 선택'),name=el('input');name.maxLength=60;name.placeholder='예: 작업용 PC';nameLabel.append(name);
 const codeLabel=el('label','','연결 코드'),code=el('textarea');code.rows=3;code.maxLength=4096;code.required=true;code.autocomplete='off';code.spellcheck=false;code.placeholder='airi-device-v1:…';codeLabel.append(code);
 const actions=el('div','device-actions'),submit=el('button','primary','연결하고 자동으로 사용'),cancel=el('button','secondary','취소');submit.type='submit';cancel.type='button';actions.append(submit,cancel);
 const message=el('p','muted');message.setAttribute('role','status');
 form.append(el('h3','','추가 컴퓨터 연결'),guide,command,nameLabel,codeLabel,actions,message);
 const modelsButton=el('button','secondary','대화 모델 선택');modelsButton.type='button';modelsButton.onclick=()=>window.AIRISettings?.open('models');
 panel.append(head,summary,list,refreshButton,modelsButton,detail,form);page.prepend(panel);
 let pending=false;
 function show(s){
  summary.replaceChildren(el('strong','',s.external_model?'선택한 외부 API 모델 사용 중':s.main?'자동 선택된 메인 · '+s.main.name:'사용할 로컬 모델을 기다리는 중'),el('small','',s.selected_model+' · '+s.reason));
  const ready=s.devices.filter(d=>d.online&&d.enabled).length;
  if($('presence-mac2')){$('presence-mac2').textContent=s.main?'AI 메인 · '+s.main.name:'AI 기기 · 설정 확인';$('presence-mac2').title=ready+'대 연결됨 · 기기 설정 열기';$('presence-mac2').onclick=()=>{window.AIRISettings?.open('devices');panel.scrollIntoView({block:'start'});};}
  list.replaceChildren();
  for(const d of s.devices){
   const row=el('article','device-row'),info=el('div');
   const label=!d.enabled?'사용 안 함':d.cooldown?'연결 재확인 중':!d.online?'오프라인':d.state==='no_models'?'모델 설치 필요':d.main?'메인 · 사용 중':d.eligible?'대기 · 자동 전환 가능':'선택한 모델·가중치 없음';
   info.append(el('strong','',d.name+(d.local?' · 기본 기기':'')),el('span','device-state',label));
   const hw=d.hardware||{};info.append(el('small','',d.online?`${hw.system||''} · ${hw.memory_gb||0} GB RAM · ${hw.cpu_count||0} CPU · 응답 ${d.latency_ms} ms`:d.error||'연결을 켜면 자동으로 확인합니다.'));
   const inventory=el('details');inventory.append(el('summary','','설치 모델 '+(d.models||[]).length+'개'),el('small','',(d.models||[]).map(m=>m.name).join(', ')||'설치 모델을 확인하지 못했습니다.'));info.append(inventory);
   row.append(info);
   if(!d.local){const buttons=el('div','device-actions');for(const [text,payload] of [[d.enabled?'잠시 사용 안 함':'다시 사용',{action:'toggle',id:d.id,enabled:!d.enabled}],['연결 해제',{action:'remove',id:d.id}]]){const b=el('button','secondary',text);b.type='button';b.onclick=()=>run(async()=>show(await api('devices',payload)));buttons.append(b);}row.append(buttons);}
   list.append(row);
  }
 }
 async function run(fn){if(pending)return;pending=true;panel.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn();}catch(e){message.textContent=e.message;toast(e.message);}finally{pending=false;panel.querySelectorAll('button').forEach(b=>b.disabled=false);}}
 add.onclick=()=>{form.hidden=false;message.textContent='연결 코드는 암호처럼 보관하세요. 이 기기에만 저장됩니다.';code.focus();};
 cancel.onclick=()=>{form.hidden=true;code.value='';};
 form.onsubmit=e=>{e.preventDefault();run(async()=>{message.textContent='기기와 모델을 확인하고 있어요…';const s=await api('devices',{action:'add',code:code.value.trim(),name:name.value.trim()});code.value='';name.value='';form.hidden=true;show(s);await health();toast('기기를 연결했습니다. 메인은 자동으로 선택됩니다.');});};
 refreshButton.onclick=()=>run(async()=>{show(await api('devices',{action:'refresh'}));await health();});
 const initial=setInterval(()=>{if(!token)return;clearInterval(initial);run(async()=>show(await api('devices')));},500);
 setInterval(()=>{if(token&&!pending&&!document.hidden)run(async()=>show(await api('devices')));},15000);
})();
