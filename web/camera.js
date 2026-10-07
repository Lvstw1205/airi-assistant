/* Uses AIRI's authenticated API and existing settings panel conventions. */
(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel camera-setup'),form=el('form'),fields={};
 panel.append(el('h2','','카메라 2 · Tapo 홈캠 연결'),el('p','muted','평소에는 AIRI가 영상을 읽지 않습니다. 텔레그램 영상 요청 또는 감시를 켠 동안만 확인해요. 요청한 영상은 텔레그램 전송 후 Mac에서 지우며, 전송 실패 시 최대 10분 후 지웁니다. 아래 사용 체크는 연결 허용이며 상시 감시 스위치가 아닙니다.'));
 const status=el('p','muted','카메라 상태 확인 중…');status.setAttribute('role','status');panel.append(status);
 function field(key,label,type='text',value=''){
  const row=el('label','',label),input=el('input');input.type=type;input.name=key;input.value=value;input.id='camera-'+key;row.htmlFor=input.id;row.append(input);form.append(row);fields[key]=input;return input;
 }
 field('enabled','Camera enabled · 카메라 사용','checkbox');
 field('name','Camera name','text','tapo-c200').maxLength=80;
 field('host','Camera LAN IP (Tapo 앱에서 확인)').placeholder='192.168.x.x';
 const port=field('port','RTSP port','number','554');port.min=1;port.max=65535;
 field('username','Tapo Camera Account username').autocomplete='off';
 const password=field('password','Camera password · 비워두면 기존 비밀번호 유지','password');password.autocomplete='new-password';
 field('clear_password','저장한 비밀번호 삭제','checkbox');
 const stream=el('select');stream.id='camera-stream';for(const [value,label] of [['stream1','High quality · stream1'],['stream2','Low quality · stream2']]){const option=el('option','',label);option.value=value;stream.append(option);}const streamLabel=el('label','','Stream quality');streamLabel.htmlFor=stream.id;streamLabel.append(stream);form.append(streamLabel);fields.stream=stream;
 field('vision_model','Vision model · 비워두면 현재 대화 모델 사용').placeholder='Installed image-capable Ollama model or openai:auto';
 const timeout=field('timeout','Capture timeout per attempt (seconds)','number','10');timeout.min=2;timeout.max=30;
 const retries=field('retries','Reconnect retries','number','1');retries.min=0;retries.max=2;
 const actions=el('div','form-actions'),save=el('button','primary','Save camera settings'),test=el('button','secondary','Test Camera'),look=el('button','secondary','Test camera_look'),disable=el('button','secondary','Disable camera');
 save.type='submit';for(const b of [test,look,disable])b.type='button';actions.append(save,test,look,disable);form.append(actions);panel.append(form);page.append(panel);
 const indicator=el('span','pill','Camera: checking');indicator.setAttribute('role','status');(document.querySelector('.console-footer')||page).append(indicator);
 let loaded=false,busy=false;
 function showState(s,fill=false){
  indicator.textContent=s.active?'Camera: capturing / analyzing':s.enabled?'Camera: enabled · on demand':'Camera: disabled';
  status.textContent=`${s.enabled?'Enabled · 요청 시 촬영':'Disabled'} · ${s.ffmpeg_available?'FFmpeg ready':'FFmpeg 설치 필요'}${s.last_capture?' · Last capture '+new Date(s.last_capture).toLocaleTimeString():''}`;
  if(fill){for(const key of ['enabled','name','host','port','username','stream','vision_model','timeout','retries']){if(fields[key].type==='checkbox')fields[key].checked=s[key];else fields[key].value=s[key];}password.value='';password.placeholder=s.has_password?'Saved · 저장됨':'';fields.clear_password.checked=false;loaded=true;}
 }
 async function load(fill=false){if(!token||busy)return;try{showState(await api('camera'),fill||!loaded);}catch(e){status.textContent=e.message;indicator.textContent='Camera: unavailable';}}
 async function run(action){busy=true;for(const b of [save,test,look])b.disabled=true;status.textContent='카메라 작업 중…';try{const result=await action();return result;}catch(e){status.textContent=e.message;return null;}finally{busy=false;for(const b of [save,test,look])b.disabled=false;}}
 form.onsubmit=async e=>{e.preventDefault();const data={action:'save'};for(const [key,input] of Object.entries(fields))data[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;const result=await run(()=>api('camera',data));if(result)showState(result,true);password.value='';};
 test.onclick=async()=>{const r=await run(()=>api('camera',{action:'test'}));if(r)status.textContent=r.message;};
 look.onclick=async()=>{const r=await run(()=>api('camera',{action:'camera_look'}));if(r)status.textContent=r.description;};
 disable.onclick=async()=>{try{showState(await api('camera',{action:'save',enabled:false}),true);}catch(e){status.textContent=e.message;}};
 // Status refresh updates the persistent indicator without overwriting edited fields/results.
 setInterval(async()=>{if(document.hidden||!token)return;try{const s=await api('camera');indicator.textContent=s.active?'Camera: capturing / analyzing':s.enabled?'Camera: enabled · on demand':'Camera: disabled';if(!loaded&&!busy)showState(s,true);}catch{indicator.textContent='Camera: unavailable';}},2500);
 setTimeout(()=>load(true),1000);
})();
