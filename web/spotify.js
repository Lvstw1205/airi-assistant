/* Spotify UI adapter. OAuth and tokens stay on the AIRI loopback server. */
(()=>{
 let state={configured:false,connected:false,playing:false,track:null,artist:null,album_art:null,progress_ms:0,duration_ms:0,device:null,error:null};
 let listeners=new Set();
 const publish=()=>{for(const fn of listeners)fn({...state});window.dispatchEvent(new CustomEvent('airi-spotify',{detail:{...state}}));};
 async function request(body){const response=await fetch('/api/spotify',{method:'POST',headers:{'Content-Type':'application/json','X-AIRI-Token':token},body:JSON.stringify(body||{action:'status'})});const data=await response.json();if(!response.ok)throw Error(data.error||'Spotify 요청에 실패했습니다.');return data;}
 const api={
  status:()=>({...state}),
  subscribe(fn){listeners.add(fn);fn({...state});return()=>listeners.delete(fn);},
  async refresh(){const response=await fetch('/api/spotify',{headers:{'X-AIRI-Token':token}});const data=await response.json();if(!response.ok)throw Error(data.error||'Spotify 상태를 확인하지 못했습니다.');state={...state,...data};publish();return api.status();},
  connect(){window.location.assign('/spotify/authorize');},
  async configure(clientId){state={...state,...await request({action:'configure',client_id:clientId})};publish();return api.status();},
  async disconnect(){state={...state,...await request({action:'disconnect'})};publish();return api.status();},
  async command(command,payload={}){state={...state,...await request({action:'command',command,...payload})};publish();return api.status();}
 };
 window.AIRISpotify=api;
 const start=()=>{if(typeof token==='undefined'||!token){setTimeout(start,500);return;}api.refresh().catch(()=>{});};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
 // Playback can start in the Spotify app after AIRI has loaded. Poll only
 // while connected so the Music card updates without another OAuth flow.
 setInterval(()=>{if(typeof token!=='undefined'&&token&&!document.hidden)api.refresh().catch(()=>{});},15000);
 window.addEventListener('focus',()=>{if(typeof token!=='undefined'&&token)api.refresh().catch(()=>{});});
})();
