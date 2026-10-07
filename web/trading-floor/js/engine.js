import {analyze} from './brain.js';import {line} from './script.js';
export class Bus {constructor(){this.listeners=new Set();}subscribe(fn){this.listeners.add(fn);return()=>this.listeners.delete(fn);}emit(type,data={}){for(const listener of this.listeners){try{listener({type,...data});}catch{/* A presentation failure must not interrupt analysis. */}}}}
export async function runDemo(snapshot,{lev=3,mode='swing',pace=1,bus=new Bus(),signal}={}) {
  const result=analyze(snapshot,{lev,mode}),runId=globalThis.crypto.randomUUID();let sequence=0;
  const emit=(type,data={})=>bus.emit(type,{...data,run_id:runId,sequence:++sequence,node:'RULES',as_of:snapshot.asOf,demo:true});
  const sleep=ms=>new Promise(r=>setTimeout(r,ms*pace));
  const work=async(id,ms)=>{if(signal?.aborted)throw Error('취소됨');emit('agent_start',{id});await sleep(ms);if(signal?.aborted)throw Error('취소됨');emit('agent_say',{id,text:line(id,result.reports[id]||result.plan.reason)});emit('agent_done',{id,report:result.reports[id]||result.plan.reason});};
  emit('run_start',{symbol:snapshot.symbol});
  await Promise.all([['taro',1800],['vibe',2200],['diana',2000],['nova',1200]].map(([id,ms])=>work(id,ms)));
  emit('handoff',{from:'taro',toRoom:'research'});
  for(const id of ['bull','bear','bull','bear'])await work(id,2000);
  await work('ace',2400);emit('handoff',{from:'ace',toRoom:'risk'});
  for(const id of ['risky','safe','neutral','blitz','guard','pm'])await work(id,700);
  emit('verdict',result.plan);emit('run_end',{result});return result;
}
