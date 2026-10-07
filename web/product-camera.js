/* Camera 1 product discovery. Existing home-camera controls stay on camera 2. */
(()=>{
 const page=$('page-setup');if(!page)return;
 function link(title,url){const a=el('a','product-link',title);try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password)return el('span','',title);a.href=u.href;}catch{return el('span','',title);}a.target='_blank';a.rel='noopener noreferrer';return a;}
 function renderResult(host,r){
  host.replaceChildren();host.append(el('p','',r.text||r.message||''));
  if(r.searched_at)host.append(el('small','muted','조회 '+new Date(r.searched_at).toLocaleString()+' · 캐나다 판매처 기준'));
  if(r.offers?.length){const wrap=el('div','product-table-scroll'),table=el('table','product-price-table'),head=el('tr');
   for(const name of ['판매처·상품','표시 가격','일치 근거','재고·상태'])head.append(el('th','',name));table.append(head);
   for(const o of r.offers){const row=el('tr'),name=el('td');name.append(link(o.seller,o.url),el('small','',o.title));row.append(name,el('td','',o.price+' '+o.currency),el('td','',o.match_basis==='same_barcode'?'바코드 일치':'이름·모델 일치 / 옵션 미확인'),el('td','',(o.availability||'unknown')+' · '+(o.condition||'unknown')));table.append(row);}wrap.append(table);host.append(wrap);
  }
  const sources=el('div','product-links');
  for(const s of r.sources||[])sources.append(link(s.title+(s.page_read?'':' · 본문 미확인'),s.url));
  for(const s of r.links||[])sources.append(link(s.title,s.url));host.append(sources);
  if(r.offers?.length)host.append(el('small','muted',r.price_policy));
 }
 window.AIRIProductResults={render:renderResult};
 let voiceLeaseAt=0;
 window.addEventListener('airi-speech-state',e=>{if(!token||!(e.detail?.speaking||e.detail?.preparing)||Date.now()-voiceLeaseAt<1800)return;voiceLeaseAt=Date.now();fetch('/api/camera-automation',{method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify({action:'voice_busy'})}).catch(()=>{});});
 const panel=el('article','panel product-camera');panel.id='product-camera-panel';
 panel.append(el('h2','','카메라 1 · PS5 사물 찾기'),el('p','muted','보여준 물건의 라벨·모델·바코드를 확인하고 판매처를 찾아요. 사진은 로컬에서 처리하고, 검색에는 제품명이나 바코드만 보냅니다.'));
 const status=el('p','muted','카메라 확인 중…');status.setAttribute('role','status');panel.append(status);
 const row=el('div','product-camera-options'),select=el('select');select.setAttribute('aria-label','제품 확인에 사용할 카메라');
 for(const [value,label] of [['1','카메라 1 · PS5 HD Camera'],['2','카메라 2 · Tapo 홈캠']]){const o=el('option','',label);o.value=value;select.append(o);}row.append(select);
 const useLabel=el('label','product-toggle'),enabled=el('input');enabled.type='checkbox';enabled.setAttribute('aria-label','카메라 1 사용');useLabel.append(enabled,document.createTextNode('카메라 1 사용'));row.append(useLabel);panel.append(row);
 const actions=el('div','form-actions'),previewButton=el('button','secondary','화면 한 장 확인'),searchButton=el('button','primary','보여준 물건·가격 찾기'),auto=el('button','secondary','상시 인식 상태 확인 중');
 for(const b of [previewButton,searchButton,auto])b.type='button';actions.append(previewButton,searchButton,auto);panel.append(actions);
 panel.append(el('p','muted','카메라 1은 AIRI 서비스가 실행 중이면 상시 켜집니다. 새 물건이 중앙에서 잠시 멈추면 인식하고 Mac 스피커로 말해요. 같은 제품 안내는 5분 동안 반복하지 않습니다. 바코드나 라벨을 밝게, 가까이 보여 주세요.'));
 const preview=el('img','product-camera-preview');preview.alt='선택한 카메라의 마지막 촬영 화면';preview.hidden=true;panel.append(preview);
 const results=el('section','product-camera-results');results.setAttribute('aria-label','제품 식별·판매처 결과');panel.append(results);page.append(panel);
 let busy=false,running=false,epoch=0,previewUrl=null,timer=null,latest=0;
 const speechLabel=el('label','product-toggle'),speak=el('input');speak.type='checkbox';speak.setAttribute('aria-label','자동 인식 결과 말하기');speechLabel.append(speak,document.createTextNode('인식한 물건 말하기'));row.append(speechLabel);
 const liveStatus=el('p','muted');liveStatus.setAttribute('role','status');panel.insertBefore(liveStatus,actions);
 function stopAuto(){epoch++;clearTimeout(timer);}
 function visible(){return !document.hidden&&panel.getClientRects().length>0;}
 function availability(on){busy=on;previewButton.disabled=on;searchButton.disabled=on;select.disabled=on;auto.disabled=on&&!running;}
 async function load(){if(!token)return;try{const r=await api('cameras');const c=r.cameras.find(c=>c.id===1);enabled.checked=c.enabled;status.textContent=c.connected?'카메라 1 연결됨 · 1920×1080 · 카메라 2는 홈캠 회전·손 추적 유지':'카메라 1 연결 확인 필요 · USB를 확인해 주세요';}catch(e){status.textContent=e.message;}}
 enabled.onchange=async()=>{stopAuto();try{await api('cameras',{action:'save',camera_id:1,enabled:enabled.checked});await load();}catch(e){status.textContent=e.message;await load();}};
 async function search(automatic=false){if(automatic&&!visible()){stopAuto();return;}if(busy)return;availability(true);const turn=epoch;status.textContent='사진의 제품명과 라벨을 읽고 판매 페이지를 확인 중…';
  try{const r=await api('cameras',{action:'product_search',camera_id:Number(select.value),automatic});if(automatic&&(!running||turn!==epoch))return;renderResult(results,r);status.textContent=r.repeated?'같은 제품 · 최근 3분 내 조회 결과':r.status==='offers_found'?'판매 페이지 확인 완료':r.status==='need_label'?'제품 라벨 확인 필요':r.status==='search_unavailable'?'검색 연결 확인 필요':'판매처 링크 확인 완료 · 가격은 미확인';}
  catch(e){status.textContent=e.message;}finally{availability(false);if(automatic&&running){if(visible())timer=setTimeout(()=>search(true),20000);else stopAuto();}}
 }
 searchButton.onclick=()=>{stopAuto();search();};
 previewButton.onclick=async()=>{stopAuto();availability(true);status.textContent='자동 노출이 안정된 화면을 가져오는 중…';try{const response=await fetch('/api/cameras',{method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify({action:'frame',camera_id:Number(select.value)})});if(!response.ok){const r=await response.json();throw new Error(r.error||'촬영 실패');}const blob=await response.blob();if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(blob);preview.src=previewUrl;preview.hidden=false;status.textContent='마지막 촬영 화면 · 제품 라벨을 중앙에 크게 보여 주세요.';}catch(e){status.textContent=e.message;}finally{availability(false);}};
 async function autoStatus(){if(!token)return;try{const s=await api('camera-automation');running=s.camera1_auto;auto.textContent=running?'상시 인식 끄기':'상시 인식 켜기';auto.setAttribute('aria-pressed',String(running));speak.checked=s.camera1_speak;liveStatus.textContent=s.camera1_state+(s.voice_error?' · '+s.voice_error:'');if(s.last_result&&s.result_id!==latest){latest=s.result_id;renderResult(results,s.last_result);if(!document.hidden&&typeof toast==='function')toast(s.last_result.text.slice(0,200));}}catch(e){liveStatus.textContent=e.message;}}
 auto.onclick=async()=>{try{await api('camera-automation',{action:'settings',camera1_auto:!running});await autoStatus();}catch(e){status.textContent=e.message;}};
 speak.onchange=async()=>{try{await api('camera-automation',{action:'settings',camera1_speak:speak.checked});}catch(e){status.textContent=e.message;}await autoStatus();};
 setTimeout(autoStatus,1400);setInterval(()=>{if(!document.hidden)autoStatus();},4000);
 select.onchange=()=>{stopAuto();preview.hidden=true;};
 // The server owns continuous recognition; navigation does not stop the camera.
 window.addEventListener('pagehide',()=>{stopAuto();if(previewUrl)URL.revokeObjectURL(previewUrl);});
 setTimeout(load,1200);
})();
