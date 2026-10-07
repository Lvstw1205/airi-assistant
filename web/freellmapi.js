/* FreeLLMAPI is one backend. AIRI keeps personality, memory and tools. */
(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel'),form=el('form'),fields={};
 panel.append(el('h2','','FreeLLMAPI 연결'),el('p','muted','고정 모델 또는 auto 라우팅을 선택하세요. AIRI의 성격·기억은 유지됩니다. auto의 실제 모델은 게이트웨이 설정에 따라 달라집니다.'));
 const status=el('p','muted','설정 확인 중…');status.setAttribute('role','status');panel.append(status);
 function field(key,label,type='text'){
  const row=el('label','',label),input=el('input');input.type=type;input.id='freellm-'+key;row.htmlFor=input.id;row.append(input);form.append(row);fields[key]=input;return input;
 }
 field('enabled','FreeLLMAPI 사용','checkbox');
 field('base_url','Base URL').placeholder='http://127.0.0.1:3001/v1';
 const password=field('api_key','통합 API 키 · 비워두면 기존 키 유지','password');password.autocomplete='new-password';
 field('clear_key','저장된 키 삭제','checkbox');
 const model=field('model','모델 ID · 직접 입력 또는 목록에서 선택');model.setAttribute('list','freellm-models');model.maxLength=256;
 const list=el('datalist');list.id='freellm-models';form.append(list);
 field('auto','Auto 라우팅 사용 (켜면 모델 ID를 auto로 변경)','checkbox');
 fields.auto.onchange=()=>{if(fields.auto.checked)model.value='auto';else if(model.value==='auto')model.value='';};
 model.oninput=()=>{fields.auto.checked=model.value==='auto'||model.value.startsWith('auto:');};
 const timeout=field('timeout','응답 제한 시간 (초)','number');timeout.min=5;timeout.max=180;
 const actions=el('div','form-actions'),save=el('button','primary','설정 저장'),refresh=el('button','secondary','모델 목록'),test=el('button','secondary','연결·스트리밍·도구 테스트'),use=el('button','secondary','이 모델로 대화');
 save.type='submit';for(const b of [refresh,test,use])b.type='button';actions.append(save,refresh,test,use);form.append(actions);panel.append(form,page.ownerDocument.createElement('hr'),el('p','muted','테스트는 저장된 설정으로 짧은 요청을 보냅니다. 도구 검증은 안전한 로컬 테스트 코드만 반환합니다. 결과는 선택 모델의 검사 시점에만 해당하며 auto의 모든 모델을 보장하지 않습니다. 비전 입력은 미검증이며 기존 카메라 Vision 설정을 사용합니다.'));
 page.append(panel);
 const names={verified:'검증됨',failed:'실패 · 미검증',untested:'미검증',accepted:'허용됨',rejected:'거부됨'};
 function report(r){status.textContent=['모델: '+(r.model||model.value),'연결: '+(r.reachable?'응답 있음':'미확인'),...['authentication','models','chat','streaming','tools','vision'].map(k=>k+': '+(names[r[k]]||r[k]||'미검증')),...Object.entries(r.errors||{}).map(([k,v])=>k+': '+v)].join(' · ');}
 function options(models){list.replaceChildren();for(const m of [...new Set(['auto',...models])]){const o=el('option');o.value=m;list.append(o);}}
 function fill(s){for(const k of ['enabled','base_url','model','timeout']){if(fields[k].type==='checkbox')fields[k].checked=s[k];else fields[k].value=s[k];}fields.auto.checked=s.model==='auto'||s.model.startsWith('auto:');password.value='';password.placeholder=s.has_key?'키 저장됨':'';fields.clear_key.checked=false;options(s.models);report(s.report);}
 async function run(fn){for(const b of [save,refresh,test,use])b.disabled=true;status.textContent='작업 중…';try{return await fn();}catch(e){status.textContent=e.message;return null;}finally{for(const b of [save,refresh,test,use])b.disabled=false;}}
 function payload(){return {action:'save',enabled:fields.enabled.checked,base_url:fields.base_url.value.trim(),api_key:password.value,clear_key:fields.clear_key.checked,model:model.value.trim(),timeout:Number(timeout.value)};}
 form.onsubmit=async e=>{e.preventDefault();const s=await run(()=>api('freellmapi',payload()));password.value='';if(s){fill(s);status.textContent='저장됨. 연결 테스트 후 이 모델로 대화를 선택하세요.';await health();}};
 refresh.onclick=async()=>{const r=await run(()=>api('freellmapi',{action:'models'}));if(r){options(r.models);status.textContent=r.models.length+'개 모델 · 목록에 없어도 ID를 직접 입력할 수 있습니다.';}};
 test.onclick=async()=>{const r=await run(()=>api('freellmapi',{action:'test'}));if(r)report(r);};
 use.onclick=async()=>{await run(async()=>{const s=await api('freellmapi');await api('settings',{model:'freellmapi:'+s.model});state.settings.model='freellmapi:'+s.model;await health();status.textContent='대화 모델: FreeLLMAPI · '+s.model;});};
 const timer=setInterval(async()=>{if(!token)return;clearInterval(timer);const s=await run(()=>api('freellmapi'));if(s)fill(s);},500);
})();
