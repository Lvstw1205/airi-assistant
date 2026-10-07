import {sma} from './indicators.js';
export function drawChart(canvas,snapshot,plan){
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2),w=Math.max(320,rect.width),h=Math.max(200,rect.height);canvas.width=w*dpr;canvas.height=h*dpr;
  const g=canvas.getContext('2d');g.scale(dpr,dpr);g.fillStyle='#0b111b';g.fillRect(0,0,w,h);
  if(!snapshot?.bars5?.length){g.fillStyle='#7c8e9e';g.font='14px monospace';g.fillText('ANALYZE → 닫힌 5분봉을 불러와.',25,70);return;}
  const bars=snapshot.bars5.slice(-100),close=snapshot.bars5.map(b=>b.close),ma20=sma(close,20).slice(-100),ma50=sma(close,50).slice(-100);
  const levels=plan?.side!=='HOLD'&&plan?.entry?[plan.entry,plan.tp,plan.sl]:[];
  let low=Math.min(...bars.map(b=>b.low),...levels),high=Math.max(...bars.map(b=>b.high),...levels);const span=Math.max(high-low,high*.002);low-=span*.1;high+=span*.1;
  const left=14,right=w-95,top=18,bottom=h-27,plotW=right-left,plotH=bottom-top,x=i=>left+(i+.5)*plotW/bars.length,y=p=>bottom-(p-low)/(high-low)*plotH;
  g.font='10px monospace';for(let i=0;i<5;i++){const yy=top+i*plotH/4,v=high-i*(high-low)/4;g.strokeStyle='#1c2938';g.beginPath();g.moveTo(left,yy);g.lineTo(right,yy);g.stroke();g.fillStyle='#8298ad';g.fillText(v.toLocaleString('en-US',{maximumFractionDigits:1}),right+8,yy+4);}
  if(levels.length){g.fillStyle='#51dda918';g.fillRect(x(bars.length-25),Math.min(y(plan.entry),y(plan.tp)),plotW*25/bars.length,Math.abs(y(plan.entry)-y(plan.tp)));g.fillStyle='#ff718218';g.fillRect(x(bars.length-25),Math.min(y(plan.entry),y(plan.sl)),plotW*25/bars.length,Math.abs(y(plan.entry)-y(plan.sl)));}
  const width=Math.max(1,plotW/bars.length*.6);bars.forEach((b,i)=>{g.fillStyle=g.strokeStyle=b.close>=b.open?'#6de5b2':'#f57f90';g.beginPath();g.moveTo(x(i),y(b.high));g.lineTo(x(i),y(b.low));g.stroke();g.fillRect(x(i)-width/2,Math.min(y(b.close),y(b.open)),width,Math.max(1,Math.abs(y(b.close)-y(b.open))));});
  for(const [values,color]of [[ma20,'#edcb7b'],[ma50,'#8aaaf3']]){g.strokeStyle=color;g.beginPath();let began=false;values.forEach((v,i)=>{if(v!==null){if(!began){g.moveTo(x(i),y(v));began=true;}else g.lineTo(x(i),y(v));}});g.stroke();}
  if(levels.length)for(const [label,value,color]of [['ENTRY',plan.entry,'#d5dde8'],['TP',plan.tp,'#6de5b2'],['SL',plan.sl,'#f57f90']]){g.strokeStyle=color;g.setLineDash([4,4]);g.beginPath();g.moveTo(left,y(value));g.lineTo(right,y(value));g.stroke();g.setLineDash([]);g.fillStyle=color;g.fillText(label,right-42,y(value)-4);}
  g.fillStyle='#8298ad';for(const i of [0,Math.floor(bars.length/2),bars.length-1])g.fillText(new Date(bars[i].time).toLocaleTimeString('en-CA',{hour:'2-digit',minute:'2-digit'}),Math.min(right-45,x(i)),h-9);
}
