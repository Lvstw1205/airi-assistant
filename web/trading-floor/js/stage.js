import {STAFF} from './brain.js';
import {drawSprite} from './sprites.js';

export function stage(bus) {
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'), cards=new Map();
  let running=false, audio=null;
  const animate=(element,frames,options)=>{if(element&&!reduced.matches&&!document.hidden)return element.animate(frames,options);};
  STAFF.forEach((person,index)=>{
    const card=document.createElement('button');card.type='button';card.className='employee';card.dataset.agent=person.id;
    card.setAttribute('aria-label',person.name+' '+person.role);
    const bubble=document.createElement('span');bubble.className='bubble';
    const canvas=document.createElement('canvas');canvas.width=canvas.height=32;
    const name=document.createElement('b');name.textContent=person.name;
    const role=document.createElement('small');role.textContent=person.role;
    const state=document.createElement('em');state.textContent='대기';
    card.append(bubble,canvas,name,role,state);
    document.querySelector(`[data-room="${person.room}"] .desks`).append(card);
    cards.set(person.id,{card,canvas,state,bubble,index,active:false});drawSprite(canvas,index);
    card.onclick=()=>document.dispatchEvent(new CustomEvent('select-agent',{detail:person.id}));
  });
  function bell(){
    if(reduced.matches||!document.getElementById('sound')?.checked)return;
    try{audio ||= new AudioContext();audio.resume();for(const [note,delay] of [[880,0],[1320,.12]]){
      const osc=audio.createOscillator(),gain=audio.createGain();osc.type='sine';osc.frequency.value=note;
      gain.gain.setValueAtTime(.025,audio.currentTime+delay);gain.gain.exponentialRampToValueAtTime(.0001,audio.currentTime+delay+.5);
      osc.connect(gain).connect(audio.destination);osc.start(audio.currentTime+delay);osc.stop(audio.currentTime+delay+.5);
    }}catch{/* Optional sound cannot affect analysis. */}
  }
  document.getElementById('sound')?.addEventListener('change',bell);
  function handoff(from,toRoom){
    if(reduced.matches||document.hidden)return;
    const a=cards.get(from)?.card.getBoundingClientRect(),room=document.querySelector(`[data-room="${toRoom}"]`),b=room?.getBoundingClientRect();
    if(!a||!b)return;
    const paper=document.createElement('span');paper.className='flying-paper';paper.textContent='≡';
    paper.style.left=(a.left+a.width/2)+'px';paper.style.top=(a.top+8)+'px';document.body.append(paper);
    const x=b.left+b.width/2-a.left-a.width/2,y=b.top+b.height/2-a.top;
    const flight=animate(paper,[{transform:'translate(0,0) rotate(-12deg)',opacity:0},{transform:`translate(${x*.5}px,${Math.min(y,0)-70}px) rotate(18deg)`,opacity:1},{transform:`translate(${x}px,${y}px) rotate(0deg)`,opacity:0}],{duration:800,easing:'ease-in-out'});
    if(flight)flight.finished.then(()=>paper.remove(),()=>paper.remove());else paper.remove();
  }
  function verdict(side){
    const box=document.getElementById('verdict');
    animate(box,[{transform:'scale(1.06)',filter:'brightness(1.5)'},{transform:'translateX(-2px)'},{transform:'translateX(2px)'},{transform:'scale(1)',filter:'brightness(1)'}],{duration:360});
    if(reduced.matches||document.hidden||side==='HOLD')return;
    const r=box.getBoundingClientRect();
    for(let i=0;i<16;i++){
      const confetti=document.createElement('i');confetti.className='confetti';confetti.style.left=(r.left+r.width/2)+'px';confetti.style.top=(r.top+18)+'px';confetti.style.background=['#8dd6b2','#e3c276','#839bc7'][i%3];document.body.append(confetti);
      const motion=animate(confetti,[{transform:'translate(0,0)',opacity:1},{transform:`translate(${Math.cos(i)*140}px,${50+Math.sin(i)*60}px) rotate(${i*53}deg)`,opacity:0}],{duration:700+i*20,easing:'ease-out'});
      if(motion)motion.finished.then(()=>confetti.remove(),()=>confetti.remove());else confetti.remove();
    }
  }
  [...document.querySelectorAll('.room')].forEach((room,i)=>animate(room,[{filter:'brightness(.22)'},{filter:'brightness(1)'}],{duration:500,delay:i*110,fill:'backwards'}));
  animate(document.querySelector('h1'),[{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'translateY(0)'}],{duration:500});
  bus.subscribe(event=>{
    const c=cards.get(event.id);
    if(event.type==='run_start'){
      running=true;if(!event.replay)bell();
      for(const v of cards.values()){v.state.textContent='대기';v.card.classList.remove('working','done','resting');v.active=false;}
    }
    if(event.type==='agent_start'&&c){c.active=true;c.card.classList.add('working');c.card.classList.remove('done','resting');c.state.textContent=event.demo?'시연 중':`${event.node||'로컬'} 처리 중`;}
    if(event.type==='agent_say'&&c){c.bubble.textContent=event.text;c.card.title=event.text;}
    if(event.type==='agent_done'&&c){c.active=false;c.card.classList.remove('working');c.card.classList.add('done');c.state.textContent=event.fallback?'규칙 대체':event.demo?'시연 완료':`${event.node||'로컬'} 완료`;}
    if(event.type==='handoff'&&!event.replay)handoff(event.from,event.toRoom);
    if(event.type==='verdict'&&!event.replay)verdict(event.side);
    if(event.type==='run_end'||event.type==='run_failed'){
      running=false;for(const v of cards.values()){v.active=false;v.card.classList.remove('working');if(event.type==='run_failed')v.state.textContent='중단';}
    }
  });
  let frame=0;
  const timer=setInterval(()=>{
    if(document.hidden||reduced.matches)return;
    frame++;for(const c of cards.values())drawSprite(c.canvas,c.index,c.active,c.active?frame%2:frame%10===0?1:0);
    if(!running&&frame%28===0){const c=[...cards.values()][Math.floor(Math.random()*cards.size)];c.card.classList.add('resting');c.card.dataset.rest=['커피 타임 · 대기','기지개 · 대기','다음 요청 대기'][frame%3];setTimeout(()=>c.card.classList.remove('resting'),2500);}
  },650);
  return()=>{clearInterval(timer);audio?.close();};
}
