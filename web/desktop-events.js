/* Presentation adapter only. Tasks and speech remain in the existing AIRI page. */
(()=>{
 const send=detail=>window.webkit?.messageHandlers?.airiDesktop?.postMessage(detail);
 if(!window.webkit?.messageHandlers?.airiDesktop)return;
 window.airiDesktop=true;
 let lastPresence='',lastTasks='';
 window.addEventListener('airi-context',e=>{if(e.detail.phase==='request')send({kind:'request'});});
 window.addEventListener('airi-operation',e=>send({kind:'operation',...e.detail}));
 window.addEventListener('airi-chat-result',e=>send({kind:'result',...e.detail}));
 window.addEventListener('airi-speech-state',e=>{const d=e.detail;const p=d.speaking?'chat':d.preparing?'thinking':'idle';if(p!==window.__desktopSpeech){window.__desktopSpeech=p;send({kind:'speech',state:p});}});
 window.addEventListener('airi-presence',e=>{const p=e.detail.state;if(p!==lastPresence){lastPresence=p;send({kind:'presence',state:p});}});
 window.addEventListener('airi-emotion',e=>send({kind:'emotion',state:e.detail.name}));
 window.addEventListener('airi-spotify',e=>send({kind:'music',playing:!!e.detail.playing}));
 window.addEventListener('airi-desktop-tasks',e=>{const ids=e.detail.filter(t=>t.status==='running').map(t=>t.id).sort().join(',');if(ids!==lastTasks){lastTasks=ids;send({kind:'tasks',active:!!ids});}});
 window.addEventListener('airi-desktop-notification',e=>send({kind:'notification',text:e.detail}));
 window.AIRIDesktopAction=async(action,value)=>{
  if(action==='ask'){
   if(typeof token==='undefined'||!token){send({kind:'error',text:'AIRI 연결을 기다려 주세요.'});return;}
   if(busy){send({kind:'notification',text:'현재 답변이 끝난 뒤 다시 보내 주세요.'});return;}
   await window.AIRIVoicePlayer?.unlock();await submitChat(String(value).slice(0,8000));
  }
  if(action==='listen')$('microphone')?.click();
  if(action==='mute'){
   const checkbox=$('auto-speak');if(checkbox){checkbox.checked=!value;checkbox.dispatchEvent(new Event('change'));}
   if(value)await interruptSpeech();
  }
  if(action==='sleep'){
   await interruptSpeech();if(typeof endVoice==='function')endVoice();if(typeof releaseMicrophone==='function')releaseMicrophone();
   window.airiFocus=true;
  }
  if(action==='wake'){window.airiFocus=false;if(typeof resumeListening==='function')resumeListening();}
  if(action==='settings'){document.querySelector('#companion-settings, [data-page="settings"]')?.click();showPage('setup');}
 };
 send({kind:'ready'});
})();
