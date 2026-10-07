// One animation clock for the portrait and optional rigged VRM character.
(()=>{
  const host=document.querySelector('.face-frame'),portrait=document.querySelector('.face-motion');
  const runtime=window.AIRICharacterRuntime?.create({host});window.airiCharacterRuntime=runtime;
  const base=portrait.querySelector('img'),closed=portrait.querySelector('.face-blink'),talk=portrait.querySelector('.face-talk');
  const canvas=document.createElement('canvas');canvas.className='portrait-rig';canvas.setAttribute('role','img');canvas.setAttribute('aria-label','AIRI 애니메이션 캐릭터');canvas.width=canvas.height=900;portrait.append(canvas);
  const ctx=canvas.getContext('2d');let ready=false;
  Promise.all([base,closed,talk].map(img=>img.decode())).then(()=>{ready=true;portrait.classList.add('rig-ready');}).catch(()=>{});
  const motion={mouth:0,blink:0,pitch:0,yaw:0,roll:0,breathe:0,smile:0};
  let speaking=false,targetMouth=0,lastAudio=0,nextBlink=performance.now()+1800,blinkStart=0,previous=performance.now(),vrm=null,mode='body',previewUntil=0,pointerX=0,pointerY=0;
  const body=el('div','character-body character-runtime-layer');body.setAttribute('role','img');body.setAttribute('aria-label','AIRI 캐릭터 런타임');
  const referenceRoot='/assets/airi-reference-hd/';
  const referenceFrames={
    neutral:'01_neutral.png',smile:'02_smile.png',laugh:'03_laugh.png',wink:'04_wink.png',serious:'05_serious.png',thinking:'06_thinking.png',side_look:'07_side_look.png',down_look:'08_down_look.png',surprised:'09_surprised.png',sleepy:'10_sleepy.png',
    happy_excited:'17_happy_excited.png',sad:'18_sad.png',confused:'19_confused.png',angry:'20_angry.png',embarrassed:'21_embarrassed.png',teary:'22_teary.png',working_laptop:'23_working_laptop.png',typing:'24_typing.png',reading:'25_reading.png',drinking_mug:'26_drinking_mug.png',chewing_gum:'27_chewing_gum.png',using_phone:'28_using_phone.png',gaming:'29_gaming.png',listening_music:'30_listening_music.png',stretching:'31_stretching.png',yawning:'32_yawning.png',resting_head:'33_resting_head.png',lean_forward:'34_lean_forward.png',lean_back:'35_lean_back.png',head_tilt_L:'36_head_tilt_L.png',head_tilt_R:'37_head_tilt_R.png',hand_on_cheek:'38_hand_on_cheek.png',both_hands:'39_both_hands.png',peace_sign:'40_peace_sign.png',pointing:'41_pointing.png',reaching:'42_reaching.png',side_pose:'43_side_pose.png',back_pose:'44_back_pose.png'
  };
  const emotionPose={happy:'smile',excited:'happy_excited',sad:'sad',confused:'confused',angry:'angry',embarrassed:'embarrassed',teary:'teary',serious:'serious',surprised:'surprised',sleepy:'sleepy',thinking:'thinking'};
  const poseA=el('img','character-pose character-pose-a'),poseB=el('img','character-pose character-pose-b');
  for(const image of [poseA,poseB]){image.alt='';image.setAttribute('aria-hidden','true');image.decoding='async';}
  poseA.src=referenceRoot+referenceFrames.neutral;poseB.src=referenceRoot+referenceFrames.neutral;poseA.classList.add('is-active');
  const faceLayer=el('div','character-face-layer face');body.append(poseA,poseB,faceLayer);
  const eyesLayer=el('div','character-eyes eyes'),mouthLayer=el('div','character-mouth mouth');faceLayer.append(eyesLayer,mouthLayer);
  const leftEye=el('span','character-eyelid character-eyelid-left'),rightEye=el('span','character-eyelid character-eyelid-right'),mouthShape=el('span','character-mouth-shape');
  eyesLayer.append(leftEye,rightEye);mouthLayer.append(mouthShape);host.append(body);
  const resizeBody=()=>{const h=host.clientHeight,w=host.clientWidth;const height=Math.min(h,w*178/150);body.style.width=(height*150/178)+'px';body.style.height=height+'px';};new ResizeObserver(resizeBody).observe(host);resizeBody();
  let activePose=0,poseRequest=0,currentPose='neutral',mesh=null;
  poseA.decode().then(()=>{mesh=window.AIRICharacterMesh?.create(body,poseA);}).catch(()=>{});
  body.dataset.pose='neutral';
  // Reference poses guide continuous gestures; never replace whole frames at runtime.
  let gesture='neutral',gestureUntil=0;
  function setPose(name){gesture=referenceFrames[name]?name:'neutral';gestureUntil=performance.now()+4500;}
  window.airiReferencePose={set:setPose,list:Object.keys(referenceFrames)};
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  window.addEventListener('airi-speech-start',()=>{speaking=true;targetMouth=.18;lastAudio=performance.now();runtime?.setVoice(true,.18);});
  window.addEventListener('airi-speech-finished',()=>{speaking=false;targetMouth=0;motion.mouth=0;previewUntil=0;lastAudio=performance.now();runtime?.setVoice(false,0);if(ready)draw();});
  window.addEventListener('airi-speech-state',e=>{
    speaking=!!e.detail.speaking;targetMouth=e.detail.level||0;
    if(speaking)lastAudio=performance.now();runtime?.setVoice(speaking,targetMouth,e.detail);
  });
  window.addEventListener('airi-presence',e=>{const state=e.detail?.state;if(state)runtime?.setState(state);});
  window.addEventListener('airi-emotion',e=>{runtime?.setEmotion(e.detail?.name,e.detail?.intensity);const emotion=emotionPose[e.detail?.name];if(emotion)setPose(emotion);});
  window.addEventListener('airi-visemes',e=>runtime?.setTimeline(e.detail.id,e.detail.cues));
  host.addEventListener('pointermove',e=>{const r=host.getBoundingClientRect();pointerX=((e.clientX-r.left)/r.width-.5)*2;pointerY=((e.clientY-r.top)/r.height-.5)*2;});
  host.addEventListener('pointerleave',()=>{pointerX=pointerY=0;});
  function patch(image,x,y,w,h,scaleY=1){
    const dy=y+h/2-h*scaleY/2;ctx.drawImage(image,x*image.naturalWidth,y*image.naturalHeight,w*image.naturalWidth,h*image.naturalHeight,x*900,dy*900,w*900,h*900*scaleY);
  }
  function draw(){
    ctx.clearRect(0,0,900,900);ctx.drawImage(base,0,0,900,900);
    if(motion.blink>.001){
      for(const x of [.265,.56]){
        patch(closed,x,.50,.175,.105);
        if(motion.blink<.96)patch(base,x,.50,.175,.105,1-motion.blink);
      }
    }
    if(motion.mouth>.018)patch(talk,.443,.73,.114,.055,.10+motion.mouth*.90);
  }
  function frame(now){
    requestAnimationFrame(frame);runtime?.tick();if(document.hidden)return;
    const delta=Math.min(.08,(now-previous)/1000);if(delta<1/28)return;previous=now;
    const demo=now<previewUntil;if(demo){targetMouth=.45+.4*Math.sin(now*.017);speaking=true;}
    else if(now-lastAudio>600){speaking=false;targetMouth=0;}
    const goal=speaking?targetMouth:0;motion.mouth+=(goal-motion.mouth)*(1-Math.exp(-delta*(goal>motion.mouth?22:13)));
    if(now>nextBlink&&!blinkStart){blinkStart=now;nextBlink=now+2600+Math.random()*4600;}
    if(blinkStart){const phase=(now-blinkStart)/190;motion.blink=phase<.4?Math.sin(phase/.4*Math.PI/2):phase<1?Math.cos((phase-.4)/.6*Math.PI/2):0;if(phase>=1)blinkStart=0;}
    const amount=reduced.matches?0:1;
    motion.blink*=amount;motion.breathe=Math.sin(now*.0011)*amount;
    motion.yaw+=(pointerX*.08-motion.yaw)*.08;motion.pitch=(pointerY*.035+Math.sin(now*.0015)*.01)*amount;
    motion.roll=(Math.sin(now*.0007)*.012+(speaking?Math.sin(now*.0023)*.012:0))*amount;
    body.classList.toggle('character-speaking',speaking);
    body.classList.toggle('character-blinking',!!blinkStart);
    eyesLayer.style.setProperty('--blink-amount',String(motion.blink));
    mouthLayer.style.setProperty('--mouth-amount',String(motion.mouth));
    const presence=window.airiPresence;
    if(presence){
      if(presence.state==='THINKING'){motion.pitch+=.02*amount;motion.roll+=.025*amount;}
      if(presence.state==='WORKING')motion.pitch+=.04*amount;
      if(presence.state==='LISTENING')motion.yaw*=.5;
      if(presence.state==='SLEEPY'){motion.pitch+=.025*amount;motion.breathe*=.5;}
    }
    body.dataset.state=presence?.state||'IDLE';
    motion.smile=presence?.emotion==='happy'?presence.intensity:0;
    const statePose={LISTENING:'side_look',THINKING:'thinking',WORKING:'working_laptop',STUDYING:'reading',RELAXING:'listening_music',SLEEPY:'sleepy'}[presence?.state||''];
    const directedPose=now<gestureUntil?gesture:statePose||emotionPose[presence?.emotion]||'neutral';
    const tilt={thinking:-.025,head_tilt_L:-.045,head_tilt_R:.045,side_look:.02,reading:.012,sleepy:.018,smile:.012}[directedPose]||0;
    mesh?.update({angle:(motion.roll*.85+motion.yaw*.25+tilt)*amount,nod:(motion.pitch*.07+(speaking?Math.sin(now*.003)*.0015:0))*amount,breath:motion.breathe*.0025,hair:Math.sin(now*.0013)*.018*amount,torso:(Math.sin(now*.00065)*.009+(directedPose==='thinking'?-.012:0))*amount,lean:Math.sin(now*.00047)*.007*amount,shoulder:(.5+.5*Math.sin(now*.0011))*.004*amount,arm:Math.sin(now*(presence?.state==='WORKING'?.006:.0008))*(presence?.state==='WORKING'?.005:.0025)*amount});
    if(mesh){for(const [element,x,y] of [[leftEye,.34,.469],[rightEye,.555,.394],[mouthShape,.52,.545]]){const point=mesh.project(x,y);element.style.marginLeft=((point[0]-x)*body.clientWidth)+'px';element.style.marginTop=((point[1]-y)*body.clientHeight)+'px';}}

    portrait.style.transform=`translate3d(${motion.yaw*12*amount}px,${motion.breathe*1.5}px,0) rotate(${motion.roll*57.3}deg) scale(1.012)`;
    if(mode==='vrm'&&vrm)vrm.update(delta,motion);else if(mode==='portrait'&&ready)draw();
  }
  requestAnimationFrame(frame);
  const panel=el('article','panel avatar-panel'),heading=el('h2','','아이리 · 캐릭터'),note=el('p','footnote','제공된 AIRI 캐릭터 한 장에 연속적인 고개·상체·머리카락 움직임을 적용합니다. 눈과 입은 별도 레이어입니다. 레퍼런스의 복잡한 손동작까지 재현하는 관절 리깅은 아직 포함되지 않았습니다. 리깅된 VRM 파일을 등록하면 관절·얼굴·입 모양까지 확장할 수 있습니다.');
  const fileLabel=el('label','','3D 캐릭터 파일 (.vrm, 최대 40MB)'),file=el('input');file.type='file';file.accept='.vrm';fileLabel.append(file);
  const switcher=el('select');switcher.setAttribute('aria-label','캐릭터 표시');for(const [value,label]of [['body','AIRI · 연속 모션'],['portrait','이전 얼굴 · 미리보기'],['vrm','등록한 3D 캐릭터']]){const option=el('option','',label);option.value=value;switcher.append(option);}
  const demo=el('button','secondary','움직임 미리보기'),status=el('p','muted');demo.type='button';demo.onclick=()=>{previewUntil=performance.now()+3500;nextBlink=performance.now()+350;status.textContent=mode==='body'?'눈 깜박임·말하기·호흡 동작을 미리 재생합니다.':'눈·입·고개 동작 미리보기 · 소리는 재생하지 않습니다.';document.querySelector('.console-drawer[open]')?.close();host.scrollIntoView({behavior:'smooth',block:'center'});};
  panel.append(heading,note,fileLabel,switcher,demo,status);$('page-setup').append(panel);
  const placeholder=el('div','character-placeholder');placeholder.setAttribute('role','img');placeholder.setAttribute('aria-label','AIRI 캐릭터 연결 대기');
  placeholder.innerHTML='<div class="presence-mark" aria-hidden="true"><span>A</span><i></i><i></i><i></i><i></i><i></i></div><strong>AIRI</strong><small>캐릭터 연결 대기</small><p class="placeholder-state" role="status">대기</p>';
  host.append(placeholder);
  const stateLabels={IDLE:'함께 있어요',LISTENING:'듣고 있어요',THINKING:'생각하고 있어요',SPEAKING:'말하고 있어요',WORKING:'작업 중',STUDYING:'학습 중',GAMING:'게임 중',RELAXING:'쉬는 중',SLEEPY:'조용히 대기'};
  function setMode(value){
    mode=value;switcher.value=value;body.hidden=value!=='body';document.querySelector('.airi-console').classList.toggle('seated-character',value==='body');host.classList.toggle('body-active',value==='body');host.classList.toggle('vrm-active',value==='vrm');host.classList.toggle('placeholder-active',value==='placeholder');
    runtime?.attach({name:value,update(v){placeholder.querySelector('.placeholder-state').textContent=stateLabels[v.state]||v.state;host.style.setProperty('--voice-energy',String(v.level));targetMouth=v.viseme==='sil'?0:v.level;},dispose(){}});
  }
  setMode('body');
  async function load(buffer){const module=await import('/avatar-vrm.bundle.js');const candidate=await module.createAvatar(buffer,host);vrm?.dispose();vrm=candidate;setMode('vrm');return candidate;}
  async function getFile(){const response=await fetch('/api/avatar/file',{headers:{'X-AIRI-Token':token}});if(!response.ok)throw Error('캐릭터 파일을 불러오지 못했습니다.');return response.arrayBuffer();}
  file.onchange=async()=>{
    if(!file.files[0])return;file.disabled=true;const selected=file.files[0];
    try{if(!/\.vrm$/i.test(selected.name)||selected.size>40*1024*1024)throw Error('40MB 이하의 .vrm 파일을 선택하세요.');const buffer=await selected.arrayBuffer();await load(buffer);
      const response=await fetch('/api/avatar/upload',{method:'POST',headers:{'X-AIRI-Token':token,'X-AIRI-Filename':encodeURIComponent(selected.name),'Content-Type':'model/gltf-binary'},body:buffer});const result=await response.json();if(!response.ok)throw Error(result.error);status.textContent=selected.name+' · 3D 캐릭터 저장됨';
    }catch(e){setMode('body');status.textContent=e.message;}finally{file.disabled=false;file.value='';}
  };
  switcher.onchange=async()=>{switcher.disabled=true;try{if(switcher.value==='vrm'&&!vrm)await load(await getFile());const result=await api('avatar',{mode:switcher.value});setMode(result.mode);status.textContent=result.mode==='vrm'?result.name+' · 3D 표시 중':result.mode==='portrait'?'이전 얼굴 미리보기':result.mode==='body'?'AIRI 레퍼런스 포즈 표시 중':'심볼 표시 중';}catch(e){setMode('body');status.textContent=e.message;}finally{switcher.disabled=false;}};
  const init=setInterval(async()=>{if(!token)return;clearInterval(init);try{const data=await api('avatar');status.textContent=data.mode==='vrm'?data.name:'AIRI 연속 모션 런타임';if(data.mode==='vrm')await load(await getFile());else setMode(['portrait','placeholder','body'].includes(data.mode)?data.mode:'body');}catch(e){status.textContent=e.message;}},1000);
  window.addEventListener('pagehide',e=>{if(!e.persisted){runtime?.dispose();vrm?.dispose();}});
})();
