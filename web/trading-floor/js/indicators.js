export function sma(values, period) {
  if (!Number.isInteger(period)||period<1) throw Error('Invalid period');
  return values.map((_,i)=>i+1<period?null:values.slice(i+1-period,i+1).reduce((a,b)=>a+b,0)/period);
}
export function ema(values,period) {
  const out=values.map(()=>null);if(values.length<period)return out;
  let v=values.slice(0,period).reduce((a,b)=>a+b,0)/period;out[period-1]=v;
  for(let i=period;i<values.length;i++){v+=(values[i]-v)*2/(period+1);out[i]=v;}return out;
}
export function rsi(values,period=14) {
  const out=values.map(()=>null);if(values.length<=period)return out;
  let gain=0,loss=0;
  for(let i=1;i<=period;i++){const d=values[i]-values[i-1];gain+=Math.max(0,d);loss+=Math.max(0,-d);}
  gain/=period;loss/=period;
  const score=()=>loss===0?(gain===0?50:100):100-100/(1+gain/loss);
  out[period]=score();for(let i=period+1;i<values.length;i++){const d=values[i]-values[i-1];gain=(gain*(period-1)+Math.max(0,d))/period;loss=(loss*(period-1)+Math.max(0,-d))/period;out[i]=score();}return out;
}
export function bollinger(values,period=20,multiplier=2) {
  return sma(values,period).map((mid,i)=>{if(mid===null)return null;const variance=values.slice(i+1-period,i+1).reduce((a,v)=>a+(v-mid)**2,0)/period;return{mid,upper:mid+multiplier*Math.sqrt(variance),lower:mid-multiplier*Math.sqrt(variance)};});
}
export function macd(values) {
  const fast=ema(values,12),slow=ema(values,26),line=values.map((_,i)=>slow[i]===null?null:fast[i]-slow[i]);
  const signal=ema(line.slice(25),9);return line.map((value,i)=>({value,signal:i<25?null:signal[i-25],histogram:i<33?null:value-signal[i-25]}));
}
