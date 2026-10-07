(() => {
  const button=el('button','secondary','이미지');button.id='image-studio-open';document.querySelector('.console-shortcuts').append(button);
  const results=el('div','image-results');results.id='console-image-results';results.hidden=true;$('console-response').after(results);
  const dialog=el('dialog','image-studio'),header=el('div','drawer-head'),close=el('button','secondary','닫기');header.append(el('h2','','이미지 작업실'),close);dialog.append(header);document.body.append(dialog);close.onclick=()=>dialog.close();
  const description=el('p','muted','설명만 적으면 새 이미지를 만들고, 사진을 첨부하면 참고 이미지로 편집합니다. OpenAI API에 프롬프트와 선택한 이미지를 전송하며 API 사용 요금이 발생합니다. 키에는 이미지 요청 권한(api.model.images.request)이 필요합니다.');
  const form=el('form'),promptLabel=el('label','','만들거나 수정할 이미지 · 최대 12,000자'),prompt=el('textarea');prompt.required=true;prompt.maxLength=12000;prompt.rows=6;prompt.placeholder='장면·구도·조명·색감·제외할 요소를 자세히 적어 주세요.';promptLabel.append(prompt);
  const uploadLabel=el('label','','참고 이미지 · 선택 사항'),upload=el('input');upload.type='file';upload.accept='image/png,image/jpeg,image/webp';upload.multiple=true;uploadLabel.append(upload);const preview=el('div','image-previews'),settings=el('div','image-options');
  function select(label,options){const container=el('label','',label),node=el('select');for(const [value,text] of options){const option=el('option','',text);option.value=value;node.append(option);}container.append(node);settings.append(container);return node;}
  const model=select('모델',[['gpt-image-2.5-flare','GPT Image 2.5 · Flare'],['gpt-image-2.5-sunburst','GPT Image 2.5 · Sunburst'],['gpt-image-1.5','GPT Image 1.5'],['gpt-image-1','GPT Image 1']]);
  const size=select('비율',[['1024x1024','정사각형'],['1536x1024','가로'],['1024x1536','세로']]);
  const quality=select('품질',[['medium','표준'],['low','빠른 초안'],['high','고품질']]);const submit=el('button','primary','이미지 생성'),status=el('p','muted'),gallery=el('div','image-gallery');status.setAttribute('role','status');
  form.append(promptLabel,uploadLabel,preview,el('p','footnote','PNG·JPEG·WebP · 최대 4장 · 각 20MB / 1600만 화소'),settings,submit);dialog.append(description,form,status,el('h3','','최근 이미지'),gallery);
  let refs=[],urls=[],previewUrls=[],signature='',working=false,loading=false,requestId=null,viewKey=0;
  const resultCards=new Map(),lastStates=new Map();let initialized=false;
  const labels={queued:'대기 중',running:'생성 중 · 창을 닫아도 계속 진행합니다',completed:'완료',failed:'실패',unknown:'결과 확인 필요'};
  function clearPreviews(){for(const url of previewUrls)URL.revokeObjectURL(url);previewUrls=[];refs=[];upload.value='';preview.replaceChildren();submit.textContent='이미지 생성';requestId=null;}
  async function blobUrl(id,preview=false){const r=await fetch('/api/images/file/'+id,{headers:{'X-AIRI-Token':token}});if(!r.ok)throw new Error('이미지를 불러오지 못했습니다.');const url=URL.createObjectURL(await r.blob());(preview?previewUrls:urls).push(url);return url;}
  async function renderResults(jobs){
    const visible=jobs.slice(0,3),ids=new Set(visible.map(j=>j.id));results.hidden=!visible.length;
    for(const [id,item] of resultCards){if(!ids.has(id)){item.card.remove();if(item.url)URL.revokeObjectURL(item.url);resultCards.delete(id);}}
    for(const job of visible){
      let item=resultCards.get(job.id);
      if(!item){const card=el('article','image-card'),title=el('strong','',job.prompt),stateText=el('p','muted'),body=el('div');card.dataset.imageId=job.id;stateText.setAttribute('role','status');card.append(title,stateText,body);item={card,stateText,body,url:null};resultCards.set(job.id,item);}
      results.append(item.card);item.stateText.textContent='#'+job.task_id+' · '+(labels[job.state]||job.state);
      if(job.state==='completed'&&!item.url){
        try{const response=await fetch('/api/images/file/'+job.id,{headers:{'X-AIRI-Token':token}});if(!response.ok)throw Error('이미지 파일을 불러오지 못했습니다. 다시 확인 중입니다.');item.url=URL.createObjectURL(await response.blob());const img=el('img');img.src=item.url;img.alt=job.prompt;const download=el('a','secondary','PNG 다운로드');download.href=item.url;download.download='AIRI-'+job.id+'.png';const open=el('button','quiet','크게 보기 · 편집');open.type='button';open.onclick=()=>button.click();item.body.replaceChildren(img,download,open);}catch(e){item.body.replaceChildren(el('p','footnote',e.message));}
      }else if(job.state!=='completed')item.body.replaceChildren(el('p','footnote',job.result||(job.state==='running'?'이미지를 만드는 중이에요. 완성되면 여기에 표시됩니다.':'이미지 생성 순서를 기다리고 있어요.')));
      const previous=lastStates.get(job.id);
      if(initialized&&previous&&previous!==job.state&&['completed','failed','unknown'].includes(job.state))toast(job.state==='completed'?'이미지가 완성됐어요. 대화 아래에서 확인하세요.':'이미지 생성 결과를 확인해 주세요: '+job.result,()=>results.scrollIntoView({behavior:'smooth',block:'nearest'}));
      lastStates.set(job.id,job.state);
    }
    initialized=true;
  }
  async function load(){if(!token||loading)return;loading=true;try{const data=await api('images');await renderResults(data.jobs);if(!data.has_key)status.textContent='연결·설정에 OpenAI API 키를 등록하세요.';else if(data.jobs[0])status.textContent='#'+data.jobs[0].task_id+' · '+(labels[data.jobs[0].state]||data.jobs[0].state);if(!dialog.open)return;const key=JSON.stringify(data.jobs);if(key===signature)return;signature=key;const current=++viewKey;for(const url of urls)URL.revokeObjectURL(url);urls=[];gallery.replaceChildren();if(!data.jobs.length)gallery.append(el('p','muted','아직 생성한 이미지가 없습니다.'));for(const job of data.jobs){const card=el('article','image-card');card.append(el('strong','',job.prompt),el('p','muted','#'+job.task_id+' · '+(labels[job.state]||job.state)+' · '+job.model));if(job.result)card.append(el('p','footnote',job.result));gallery.append(card);if(job.state==='completed'){try{const url=await blobUrl(job.id);if(current!==viewKey)continue;const img=el('img');img.src=url;img.alt=job.prompt;img.loading='lazy';const download=el('a','secondary','PNG 다운로드');download.href=url;download.download='AIRI-'+job.id+'.png';const edit=el('button','secondary','이 이미지로 편집');edit.onclick=async()=>{clearPreviews();refs=[job.id];const thumb=el('img');try{thumb.src=await blobUrl(job.id,true);}catch(e){clearPreviews();status.textContent=e.message;return;}thumb.alt='선택한 참고 이미지';preview.append(thumb);submit.textContent='이미지 편집';prompt.focus();};card.append(img,download,edit);}catch(e){card.append(el('p','muted',e.message));signature='';}}}}catch(e){status.textContent=e.message;}finally{loading=false;}}
  button.onclick=()=>{dialog.showModal();load();};
  upload.onchange=async()=>{requestId=null;const files=[...upload.files];if(files.length>4||files.some(f=>f.size>20*1024**2)){status.textContent='최대 4장, 각 20MB 이하의 이미지를 선택하세요.';upload.value='';return;}working=true;submit.disabled=true;status.textContent='참고 이미지를 확인하고 있어요…';clearPreviews();try{for(const file of files){const r=await fetch('/api/images/upload',{method:'POST',headers:{'X-AIRI-Token':token,'Content-Type':'application/octet-stream'},body:file});const data=await r.json();if(!r.ok)throw new Error(data.error);refs.push(data.id);const img=el('img');img.src=await blobUrl(data.id,true);img.alt=file.name;preview.append(img);}submit.textContent=refs.length?'이미지 편집':'이미지 생성';status.textContent='참고 이미지 '+refs.length+'장 준비됨';}catch(e){clearPreviews();status.textContent=e.message;}finally{working=false;submit.disabled=false;}};
  const clear=el('button','quiet','참고 이미지 제거');clear.type='button';clear.onclick=clearPreviews;uploadLabel.append(clear);
  form.oninput=()=>requestId=null;
  form.onsubmit=async event=>{event.preventDefault();if(working)return;working=true;submit.disabled=true;upload.disabled=true;requestId=requestId||crypto.randomUUID().replaceAll('-','');status.textContent='요청을 저장하고 있어요…';try{const job=await api('images',{prompt:prompt.value,model:model.value,size:size.value,quality:quality.value,inputs:refs,request_id:requestId});status.textContent='작업 #'+job.task_id+' 접수 완료. 완성되면 아래에 표시됩니다.';requestId=null;await load();await refresh();}catch(e){status.textContent=e.message;}finally{working=false;submit.disabled=false;upload.disabled=false;}};
  window.addEventListener('airi-image-job',()=>load());
  const boot=setInterval(()=>{if(token){clearInterval(boot);load();}},500);
  setInterval(()=>{if(!document.hidden&&!working)load();},3000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
})();
