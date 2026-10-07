(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel'),status=el('p','muted','영상 작업자 확인 중…'),form=el('form'),input=el('textarea'),button=el('button','primary','30초 이상 시험 영상 제작');
 input.placeholder='원하는 이야기나 스타일을 적어 주세요. 소재를 비워 두면 독창적인 이야기를 기획합니다.';input.maxLength=3000;
 button.type='submit';form.append(input,button);panel.append(el('h2','','영상 제작팀'),status,el('p','muted','M1 기획 → 6개 장면 생성 → 30초 이상 편집 → NAS 검토본 저장. 현재 로컬 무료 모델만 사용하며, 매일 3편 예약은 첫 결과 품질 확인 전까지 꺼져 있습니다.'),form);page.append(panel);
 const feedback=el('textarea'),accept=el('button','secondary','최근 영상 승인'),reject=el('button','secondary','최근 영상 반려'),learning=el('p','muted');feedback.placeholder='좋았던 점 또는 수정할 점을 구체적으로 적어 주세요.';feedback.maxLength=2000;accept.type=reject.type='button';panel.append(feedback,accept,reject,learning);let latestId=null;
 async function review(accepted){if(!latestId)return;try{const r=await api('video-production',{action:'review',id:latestId,accepted,feedback:feedback.value});learning.textContent=r.message;await refresh();}catch(e){learning.textContent=e.message;}}accept.onclick=()=>review(true);reject.onclick=()=>review(false);
 async function refresh(){if(!token)return;try{const s=await api('video-production');const j=s.jobs[0];latestId=j?.id;accept.disabled=reject.disabled=!j||!['awaiting_review','accepted','rejected'].includes(j.state);learning.textContent='피드백 '+s.learning.feedback_records+'건 · 다음 기획에 참고 · 모델 가중치 훈련은 미실행';status.textContent=(s.worker_online?'영상 작업자 연결됨':'영상 작업자 최초 설정 필요')+(j?' · '+j.title+' · '+j.state+' · 장면 '+j.scene+'/6'+(j.error?' · '+j.error:'')+(j.result?' · 파일: '+j.result:''):' · 작업 없음');}catch(e){status.textContent=e.message;}}
 form.onsubmit=async e=>{e.preventDefault();button.disabled=true;try{await api('video-production',{brief:input.value.trim()||'Create an original vivid visual story with a meaningful payoff. Avoid cats and copying reference videos.'});await refresh();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
 const initial=setInterval(()=>{if(token){clearInterval(initial);refresh();}},500);setInterval(()=>{if(!document.hidden)refresh();},10000);
})();
