/* Renderer-independent state. All renderers receive the same immutable snapshot. */
(()=>{
 const states=Object.freeze(['IDLE','LISTENING','THINKING','SPEAKING','WORKING','STUDYING','GAMING','RELAXING','SLEEPY']);
 const emotions=Object.freeze(['neutral','happy','wink','thinking','surprised','confused','worried','pout','annoyed','cute-heart','sad','sleepy','excited','angry','cute','playful','aegyo']);
 const visemes=Object.freeze(['sil','aa','ih','ou','ee','oh','mm','fv','th','rest']);
 const clamp=v=>Math.max(0,Math.min(1,Number(v)||0));
 function create({host=null,clock=()=>performance.now()}={}){
  let adapter=null,baseState='IDLE',emotionUntil=0,voiceUntil=0,disposed=false,cues=[],voiceId=null;
  const value={state:'IDLE',emotion:'neutral',intensity:0,viseme:'sil',level:0,speaking:false,asset:null,adapter:'placeholder',environment:'afternoon',updatedAt:clock()};
  const listeners=new Set(),snapshot=()=>({...value});
  function publish(){if(disposed)return;value.updatedAt=clock();if(host){host.dataset.characterState=value.state;host.dataset.characterEmotion=value.emotion;host.dataset.characterAdapter=value.adapter;}adapter?.update(snapshot());for(const fn of listeners)fn(snapshot());}
  function stopVoice(){value.speaking=false;value.level=0;value.viseme='sil';value.state=baseState;cues=[];voiceId=null;voiceUntil=0;}
  const runtime={states,emotions,visemes,snapshot,
   subscribe(fn){listeners.add(fn);fn(snapshot());return()=>listeners.delete(fn);},
   setState(state){if(!states.includes(state)||state==='SPEAKING')return;baseState=state;value.state=value.speaking?'SPEAKING':state;publish();},
   setEnvironment(phase){if(['morning','afternoon','evening','night'].includes(phase)){value.environment=phase;publish();}},
   setEmotion(name,intensity=.35,duration=5000){if(!emotions.includes(name))return;value.emotion=name;value.intensity=clamp(intensity);emotionUntil=clock()+Math.max(0,Math.min(30000,Number(duration)||0));publish();},
   setViseme(name,level=0){value.viseme=visemes.includes(name)?name:'sil';value.level=clamp(level);publish();},
   // Timed cues are seconds from actual audio playback start; never guessed from text.
   setTimeline(id,items){voiceId=id;cues=(Array.isArray(items)?items:[]).filter(c=>Number.isFinite(c.start)&&Number.isFinite(c.end)&&c.start>=0&&c.end>c.start&&visemes.includes(c.viseme)).slice(0,10000).sort((a,b)=>a.start-b.start);},
   setVoice(speaking,level=0,{id=null,elapsed=0}={}){if(!speaking){stopVoice();publish();return;}value.speaking=true;value.state='SPEAKING';voiceUntil=clock()+1200;if(id!==voiceId){voiceId=id;cues=[];}const cue=cues.find(c=>elapsed>=c.start&&elapsed<c.end);value.level=clamp(level);value.viseme=cue?.viseme||(value.level>.02?'aa':'sil');publish();},
   tick(){if(disposed)return;let changed=false;if(value.speaking&&clock()>voiceUntil){stopVoice();changed=true;}if(value.emotion!=='neutral'&&clock()>=emotionUntil){value.emotion='neutral';value.intensity=0;changed=true;}if(changed)publish();},
   replaceRaster(url){value.asset=String(url||'');publish();},
   attach(next){if(!next||typeof next.update!=='function')throw new TypeError('Character adapter requires update(snapshot)');adapter?.dispose?.();adapter=next;value.adapter=next.name||'custom';publish();return()=>{if(adapter===next){adapter.dispose?.();adapter=null;value.adapter='placeholder';publish();}};},
   dispose(){if(disposed)return;stopVoice();publish();adapter?.dispose?.();adapter=null;listeners.clear();disposed=true;}
  };return runtime;
 }
 window.AIRICharacterRuntime={states,emotions,visemes,create};
})();
