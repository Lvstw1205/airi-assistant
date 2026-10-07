/* A deliberate hold, shared by the live review sheet and the mock prototype. */
(function(root){
 'use strict';
 function create({commit,onChange=()=>{},delay=600,schedule=setTimeout,cancel=clearTimeout}){
  let timer=null,held=false,disposed=false;
  function end(){if(timer!==null)cancel(timer);timer=null;held=false;onChange(false);}
  return {
   start(){if(disposed||held)return;held=true;onChange(true);timer=schedule(()=>{timer=null;if(!held||disposed)return;onChange(false);commit();},Math.max(600,delay));},
   end,
   dispose(){end();disposed=true;}
  };
 }
 const api={create};if(typeof module==='object'&&module.exports)module.exports=api;else root.AIRIHold=api;
})(typeof window!=='undefined'?window:this);
