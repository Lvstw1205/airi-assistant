import {getJSON,candles} from './data.js';
export async function history(snapshot,until=snapshot.asOf+86400000,fetcher=fetch){
  const start=Math.floor(snapshot.asOf/300000)*300000,end=Math.min(until,Date.now());
  if(snapshot.venue==='Binance')return candles(await getJSON(`https://fapi.binance.com/fapi/v1/klines?symbol=${snapshot.symbol}&interval=5m&startTime=${start}&endTime=${end}&limit=1000`,fetcher),300000,Date.now());
  if(snapshot.venue==='Bybit'){const d=await getJSON(`https://api.bybit.com/v5/market/kline?category=linear&symbol=${snapshot.symbol}&interval=5&start=${start}&end=${end}&limit=1000`,fetcher);if(d.retCode!==0)throw Error('Bybit history unavailable');return candles(d.result.list,300000,Date.now(),'bybit');}
  throw Error('No matching venue history');
}
export function grade(result,bars,now=Date.now()){
  const p=result.plan,s=result.snapshot;
  if(p.side==='HOLD')return {state:'NOT_APPLICABLE',reason:'HOLD에는 방향 승패를 매기지 않아.'};
  if(now-s.asOf<86400000)return {state:'PENDING',reason:'24시간 경과 전'};
  const start=Math.floor(s.asOf/300000)*300000,end=s.asOf+86400000,range=bars.filter(b=>b.time>=start&&b.time<end).sort((a,b)=>a.time-b.time);
  if(!range.length||range[0].time!==start||range.at(-1).closeTime<end-1||range.some((b,i)=>i&&b.time-range[i-1].time!==300000))return {state:'UNKNOWN',reason:'24시간 구간의 봉 데이터 누락'};
  const long=p.side==='LONG';
  for(const b of range){const stop=long?b.low<=p.sl:b.high>=p.sl,target=long?b.high>=p.tp:b.low<=p.tp;
    if((stop||target)&&(b.time<s.asOf||b.closeTime>=end))return {state:'AMBIGUOUS',reason:'진입·종료 시각이 포함된 부분 봉에서 도달해 정확한 선후를 알 수 없어.',time:b.time};
    if(stop&&target)return {state:'AMBIGUOUS',reason:'같은 5분봉에서 목표·손절 모두 도달',time:b.time};
    if(stop)return {state:'STOP_FIRST',time:b.time,exit:long?Math.min(b.open,p.sl):Math.max(b.open,p.sl)};
    if(target)return {state:'TARGET_FIRST',time:b.time,exit:p.tp};}
  return {state:'NO_HIT',time:end,reason:'관측 구간에서 목표·손절 도달 없음. 부분 봉 종가를 24시간 가격으로 간주하지 않아.'};
}
