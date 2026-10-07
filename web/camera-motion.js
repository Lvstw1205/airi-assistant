/* Local-only hand landmark inference; camera movement is a bounded pulse. */
(()=>{
 const page=$('page-setup');if(!page)return;
 const panel=el('article','panel camera-motion'),status=el('p','muted','방향 버튼이나 “카메라 왼쪽으로 돌려”로 이동할 수 있습니다.');status.setAttribute('role','status');
 panel.append(el('h2','','카메라 2 · 홈캠 움직임 · 카메라 이동'),status);
 const buttons=el('div','form-actions');
 const lastAction=el('p','muted','아직 이동 요청 없음');panel.append(lastAction);
 let running=false,detector=null,gate=createGate(),abort=null,epoch=0,turnGate=createTurnGate();
 async function move(direction,source='버튼',pulse=.65){
  const prefix=new Date().toLocaleTimeString()+' · '+source+' · ';
  lastAction.textContent=prefix+'이동 요청 중';
  try{const r=await api('camera',{action:'move',direction,speed:Number(speed.value),pulse});lastAction.textContent=prefix+r.message;return r;}
  catch(e){lastAction.textContent=prefix+'실패: '+e.message;throw e;}
 }
 for(const [d,label] of [['left','← 왼쪽'],['right','오른쪽 →'],['up','↑ 위'],['down','↓ 아래'],['stop','정지']]){
  const b=el('button',d==='stop'?'primary':'secondary',label);b.type='button';b.onclick=async()=>{window.dispatchEvent(new CustomEvent('airi-camera-manual'));try{if(d==='stop')await stop();else{if(running)await stop();await move(d);}}catch(e){status.textContent=e.message;}};buttons.append(b);
 }
 const toggle=el('button','secondary','손 따라가기 켜기');toggle.type='button';buttons.append(toggle);
 const speed=el('select');speed.setAttribute('aria-label','카메라 이동 속도');
 for(const [value,label] of [['0.35','느리게'],['0.7','빠르게'],['1','최대 속도']]){const option=el('option','',label);option.value=value;speed.append(option);}speed.value='0.7';buttons.append(speed);panel.append(buttons);
 panel.append(el('p','muted','손 전체를 보여 주고 화면 가장자리 쪽으로 옮기세요. 가장 크게 보이는 손을 넓은 중앙 사각형으로 따라갑니다. 검지·중지만 펴서 V 모양을 2초 유지하면 가능한 방향으로 약 180도 회전합니다. 같은 동작은 손을 내린 뒤 30초 후 다시 가능합니다. 정지 버튼으로 중단합니다. 탭을 숨기면 추적이 꺼집니다.'));
 const preview=el('canvas');preview.width=640;preview.height=360;preview.hidden=true;preview.setAttribute('aria-label','손 제스처 카메라 미리보기');panel.append(preview);page.append(panel);
 const ctx=preview.getContext('2d');
 async function stop(){turnGate.stale();running=false;epoch++;abort?.abort();gate=createGate();toggle.textContent='손 따라가기 켜기';preview.hidden=true;status.textContent='손 따라가기 꺼짐';try{await move('stop');}catch(e){lastAction.textContent=e.message;}try{await api('camera',{action:'tracking_stop'});}catch{}}
 function follow(hands){
  const valid=hands.filter(p=>p.length===21&&p.every(v=>Number.isFinite(v.x)&&Number.isFinite(v.y)));
  if(!valid.length)return {direction:'stop'};
  const area=p=>(Math.max(...p.map(v=>v.x))-Math.min(...p.map(v=>v.x)))*(Math.max(...p.map(v=>v.y))-Math.min(...p.map(v=>v.y)));
  const p=valid.reduce((a,b)=>area(a)>=area(b)?a:b);
  const palm=[0,5,9,13,17],x=palm.reduce((s,i)=>s+p[i].x,0)/5,y=palm.reduce((s,i)=>s+p[i].y,0)/5;
  const dx=x-.5,dy=y-.5;
  if(Math.abs(dx)<=.22&&Math.abs(dy)<=.25)return {direction:'stop',x,y};
  const horizontal=Math.abs(dx)/.22>=Math.abs(dy)/.25;
  return {x,y,direction:horizontal?(dx<0?'left':'right'):(dy<0?'up':'down'),pulse:Math.min(.35,.15+Math.max(Math.abs(dx),Math.abs(dy))*.4)};
 }
 window.AIRIHandFollow=follow;
 window.AIRICameraMotion={get active(){return running;},stop};
 function twoFingers(hands){
  if(hands.length!==1||hands[0].length!==21)return false;
  const p=hands[0],dist=(a,b)=>Math.hypot((p[a].x-p[b].x)*16/9,p[a].y-p[b].y,((p[a].z||0)-(p[b].z||0))*16/9);
  const extended=tip=>{const n=dist(tip-3,tip-2)+dist(tip-2,tip-1)+dist(tip-1,tip);return n>.025&&dist(tip-3,tip)/n>.82&&dist(tip-3,tip)>dist(tip-3,tip-2)*1.35;};
  return extended(8)&&extended(12)&&!extended(16)&&!extended(20);
 }
 function createTurnGate(){let since=null,last=null,latched=false,neutral=0;return {
  sample(pose,now){if(!pose){since=null;if(++neutral>=3)latched=false;return false;}neutral=0;if(since===null)since=now;if(!latched&&(last===null||now-last>=30000)&&now-since>=2000){latched=true;last=now;return true;}return false;},
  stale(){since=null;neutral=0;}
 };}
 window.AIRITwoFingers=twoFingers;window.AIRITurnGate=createTurnGate;
 function handDirection(p,details){
  if(!p||p.length!==21)return 'stop';
  // Measure each finger against its own joints, not the wrist. Wrist distance
  // misclassifies a side-pointing index when the palm is rotated.
  const distance=(a,b)=>Math.hypot((p[a].x-p[b].x)*16/9,p[a].y-p[b].y,((p[a].z||0)-(p[b].z||0))*16/9);
  const ratios=[];
  const ext=(tip)=>{
   const length=distance(tip-3,tip-2)+distance(tip-2,tip-1)+distance(tip-1,tip);
   ratios.push(length?distance(tip-3,tip)/length:0);
   return length>.025&&distance(tip-3,tip)/length>.82&&distance(tip-3,tip)>distance(tip-3,tip-2)*1.35;
  };
  const fingers=[ext(8),ext(12),ext(16),ext(20)];
  if(details)details.push('검지/중지/약지/소지 '+fingers.map((v,i)=>(v?'펴짐':'굽힘')+' '+ratios[i].toFixed(2)).join(' · '));
  if(fingers.every(Boolean)||fingers.every(x=>!x))return 'stop';
  if(!fingers[0]||fingers.slice(1).some(Boolean))return 'stop';
  const dx=(p[8].x-p[5].x)*16/9,dy=p[8].y-p[5].y;
  if(Math.hypot(dx,dy)<.025)return 'stop';
  return Math.abs(dx)>Math.abs(dy)?(dx<0?'left':'right'):(dy<0?'up':'down');
 }
 function gesture(hands){
  const pointing=hands.map(p=>handDirection(p)).filter(d=>d!=='stop');
  // A resting second hand must not veto the intentional pointing hand.
  return pointing.length===1?pointing[0]:'stop';
 }
 function createGate(){
  let recent=[],neutral=0,latched=false;
  return {
   sample(direction,now){
    recent=recent.filter(s=>now-s.at<12000);
    if(direction==='stop'){
     neutral++;if(neutral>=3){latched=false;recent=[];}
    }else{neutral=0;}
    recent.push({direction,at:now});recent=recent.slice(-3);
    const count=recent.filter(s=>s.direction===direction).length;
    return {request:direction!=='stop'&&!latched&&count>=2&&recent.every(s=>s.direction==='stop'||s.direction===direction),count,latched,ready:neutral>=3};
   },
   // Even an uncertain movement result requires rearming: never retry physical motion blindly.
   attempted(){latched=true;recent=[];},
   clearEvidence(){recent=[];neutral=0;}
  };
 }
 // Exposed for deterministic geometry tests, not a camera or movement permission.
 window.AIRIHandDirection=gesture;
 window.AIRIHandGate=createGate;
 async function frame(run){
  if(!running||document.hidden||run!==epoch)return;
  try{
   abort=new AbortController();const started=performance.now();
   const response=await fetch('/api/camera',{method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify({action:'tracking_frame'}),signal:abort.signal});
   if(!response.ok){const e=await response.json();throw Error(e.error||'Camera frame unavailable');}
   const bitmap=await createImageBitmap(await response.blob());
   if(!running||run!==epoch){bitmap.close();return;}
   ctx.drawImage(bitmap,0,0,preview.width,preview.height);
   let found;try{found=detector.detect(bitmap);}finally{bitmap.close();}
   const hands=found.landmarks||[],elapsed=performance.now()-started;
   ctx.fillStyle='#39ff88';
   for(const hand of hands)for(const point of hand){ctx.beginPath();ctx.arc(point.x*640,point.y*360,3,0,Math.PI*2);ctx.fill();}
   ctx.strokeStyle='#39ff88';ctx.lineWidth=2;ctx.strokeRect(.28*640,.25*360,.44*640,.50*360);
   if(elapsed>1500){gate.clearEvidence();turnGate.stale();status.textContent='영상 준비/지연 '+(elapsed/1000).toFixed(1)+'초 · 새 영상 대기';return;}
   const v=twoFingers(hands),turn=turnGate.sample(v,performance.now());
   if(v){
    gate.clearEvidence();status.textContent='두 손가락 V · 2초 유지하면 약 180도 회전 · 손을 내린 뒤 30초 후 재실행';
    if(turn){lastAction.textContent='두 손가락 · 약 180도 회전 중';window.dispatchEvent(new CustomEvent('airi-camera-manual'));try{const r=await api('camera',{action:'half_turn'});if(running&&run===epoch)lastAction.textContent='두 손가락 · '+r.message;}catch(e){lastAction.textContent='두 손가락 · '+e.message;}}
    return;
   }
   const target=follow(hands),decision=gate.sample(target.direction,performance.now());
   if(target.direction==='stop')gate.clearEvidence();
   status.textContent='손 '+hands.length+'개 · '+(target.direction==='stop'?(hands.length?'중앙 · 정지':'손 대기'):target.direction+' 따라가기')+' · 영상 '+Math.round(elapsed)+'ms';
   if(decision.request){
    gate.clearEvidence();const result=await move(target.direction,'손 따라가기',target.pulse);
    if(!result.ok){await stop();status.textContent='추적 중지 · 위치 변화를 확인하지 못했습니다. 버튼으로 방향과 회전 한계를 확인하세요.';}
   }
  }catch(e){if(running&&run===epoch){gate.clearEvidence();turnGate.stale();status.textContent='영상/이동 확인 실패 · 재확인 중: '+e.message;}}
  finally{if(running&&run===epoch)setTimeout(()=>frame(run),120);}
 }
 toggle.onclick=async()=>{
  if(running){await stop();return;}
  toggle.disabled=true;status.textContent='로컬 손 인식 모델을 불러오는 중…';
  try{
   await api('camera',{action:'ptz_status'});
   if(!detector){const {FilesetResolver,HandLandmarker}=await import('/hand-assets/vision_bundle.mjs');const files=await FilesetResolver.forVisionTasks('/hand-assets/wasm');detector=await HandLandmarker.createFromOptions(files,{baseOptions:{modelAssetPath:'/hand-assets/hand_landmarker.task',delegate:'CPU'},runningMode:'IMAGE',numHands:2,minHandDetectionConfidence:.7,minHandPresenceConfidence:.7,minTrackingConfidence:.7});}
   running=true;preview.hidden=false;toggle.textContent='손 따라가기 끄기';gate=createGate();frame(++epoch);
  }catch(e){status.textContent='손 제스처를 켜지 못했습니다: '+e.message;}finally{toggle.disabled=false;}
 };
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)stop();});
 window.addEventListener('pagehide',()=>{running=false;abort?.abort();});
})();
