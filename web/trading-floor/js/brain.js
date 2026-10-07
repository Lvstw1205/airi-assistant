import {ema,rsi,bollinger,macd,sma} from './indicators.js';
export const STAFF=[['taro','TARO','기술 분석','analysts'],['diana','DIANA','수급 분석','analysts'],['nova','NOVA','뉴스 리서치','analysts'],['vibe','VIBE','시장 심리','analysts'],['bull','BULL','상승 논거','research'],['bear','BEAR','하락 논거','research'],['ace','ACE','매매 계획','trading'],['risky','RISKY','공격적 검토','risk'],['safe','SAFE','보수적 검토','risk'],['neutral','NEUTRAL','중립 검토','risk'],['pm','PM','최종 검수','executive'],['blitz','BLITZ','단기 관찰','scalp'],['guard','GUARD','청산 검증','scalp']].map(([id,name,role,room])=>({id,name,role,room}));
const finite=x=>typeof x==='number'&&Number.isFinite(x);
export function levels(side,entry,lev,mmr=.005) {
  if(!finite(lev)||lev<1||lev>100||!finite(entry)||entry<=0)throw Error('가격·레버리지 범위가 올바르지 않아.');
  const dir=side==='LONG'?1:side==='SHORT'?-1:0;
  const tp=entry*(1+dir*.15/lev),sl=entry*(1-dir*.30/lev),liq=dir===1?entry*(1-1/lev)/(1-mmr):entry*(1+1/lev)/(1+mmr);
  return {entry,tp,sl,liq,lev,mmr,rr:.5,guard:dir!==0&&Math.abs(liq-entry)>Math.abs(sl-entry),liquidationEstimate:true};
}
export function analyze(s,{lev=3,mode='swing',now=Date.now()}={}) {
  const bad=()=>({plan:{side:'HOLD',confidence:0,size:0,reason:'필수 가격·닫힌 봉 데이터가 부족하거나 15분 이상 지났어.',guard:false},reports:{},metrics:{},snapshot:s,algorithm:'signed-v2'});
  if(!s?.valid||s.bars5?.length<73||s.bars1?.length<50||!finite(s.price)||s.price<=0||(!s.fixture&&now-s.asOf>900000))return bad();
  const c=s.bars5.map(b=>b.close),p=c.at(-1),hour=s.bars1.map(b=>b.close),h=hour.at(-1),e=ema(hour,50).at(-1),rs=rsi(c).at(-1),bb=bollinger(c),prev=s.bars5.slice(-73,-1);
  const upper=Math.max(...prev.map(b=>b.high)),lower=Math.min(...prev.map(b=>b.low));
  const trend=h>e*1.001?1:h<e*.999?-1:0,breakout=p>upper?1:p<lower?-1:0;
  const reentry=c.at(-2)<bb.at(-2).lower&&p>bb.at(-1).lower?1:c.at(-2)>bb.at(-2).upper&&p<bb.at(-1).upper?-1:0;
  const aux=[];
  if(s.symbol==='BTCUSDT'&&finite(s.fear)&&now-s.fearAsOf<172800000)aux.push(s.fear<25?.5:s.fear>75?-.5:0);
  if(finite(s.funding))aux.push(s.funding>.0003?-.5:s.funding<-.0003?.5:0);
  if(finite(s.ratio))aux.push(s.ratio>2?-.5:s.ratio<.5?.5:0);
  let oiDelta=null,oiLabel='미결제약정 자료 없음';
  if(s.oi?.length>1){const a=s.oi[0],b=s.oi.at(-1);oiDelta=a.value>0?(b.value/a.value-1)*100:null;
    const previous=hour[Math.max(0,hour.length-s.oi.length)];const priceUp=h>previous;
    oiLabel=oiDelta>0?(priceUp?'가격·OI 동반 상승':'가격 하락·OI 증가'):(priceUp?'가격 상승·OI 감소':'가격·OI 동반 하락');
    if(oiDelta>0)aux.push(priceUp?.5:-.5);}
  const votes=trend+breakout+reentry+aux.reduce((a,b)=>a+b,0),side=votes>0?'LONG':votes<0?'SHORT':'HOLD';
  const chase=(side==='LONG'&&rs>=75)||(side==='SHORT'&&rs<=25),confidence=side==='HOLD'?50:Math.min(85,Math.max(50,50+10*Math.abs(votes)-(chase?10:0)));
  const plan=side==='HOLD'?{side,confidence,size:0,reason:'방향 점수가 상쇄됨',guard:false}: {side,confidence,...levels(side,s.price,Number(lev)),size:rs>=70||rs<=30||confidence<60?.5:1,reason:`1시간 EMA50 필터 ${trend}; 5분 돌파 ${breakout}; 밴드 재진입 ${reentry}; 보조 ${aux.reduce((a,b)=>a+b,0)}; 추격 감점 ${chase?10:0}`};
  if(side!=='HOLD'&&!plan.guard){plan.side='HOLD';plan.size=0;plan.reason='GUARD 거부: 손절보다 청산이 먼저 올 수 있음';}
  const metrics={trend,breakout,reentry,ema50:e,rsi:rs,upper,lower,votes,chase,oiDelta,oiLabel,macd:macd(c).at(-1),sma20:sma(c,20).at(-1),mode};
  const f=n=>finite(n)?n.toLocaleString('ko-KR',{maximumFractionDigits:2}):'미확인';
  const reports={
    taro:`[계산] 닫힌 1시간 봉 ${f(h)}, EMA50 ${f(e)}. 5분 RSI14 ${f(rs)}. 직전 72봉 범위 ${f(lower)}–${f(upper)}.`,
    diana:`[관측] 펀딩 ${finite(s.funding)?(s.funding*100).toFixed(4)+'%':'미확인'}, 롱숏 비율 ${f(s.ratio)}. ${oiLabel}. [해석] OI만으로 새 매수·매도 주체를 특정할 수 없어.`,
    nova:s.news?.length?`[조회] 날짜가 확인된 뉴스 ${s.news.length}건. 제목만으로 가격 변동 원인을 확정하지 않아.`:'[미확인] 이 스냅샷에는 검증된 뉴스가 없어. 뉴스 방향은 점수에 넣지 않았어.',
    vibe:`[관측] 공포탐욕 ${f(s.fear)}. [해석] BTC 지수이며 ETH 가격 전망의 직접 근거로 쓰지 않아.`,
    bull:`[시나리오] ${f(upper)} 위 돌파와 유지가 확인되면 상승 논거가 강화돼. 현재 추세 표는 ${trend}.`,
    bear:`[반론] ${f(lower)} 하단 이탈, 수수료와 펀딩 비용이 계획을 훼손할 수 있어. RSI ${f(rs)}만으로 반전을 단정하지 않아.`,
    ace:`[모의 계획] ${plan.side} · 규칙 점수 ${confidence}/100. 승률 예측이 아니야.`,
    risky:'[해석] 돌파를 노릴 수 있지만 손익비 0.5는 비용 전에도 손실 폭이 더 커. 포지션 확대 근거는 부족해.',
    safe:'[검수] 수수료·펀딩·체결 지연을 별도로 봐야 해. 레버리지 청산가는 근사치야.',
    neutral:`[검수] 선택한 거래소는 ${s.venue}. 다른 거래소 가격과 섞지 않았어. 누락 항목 ${s.errors?.length||0}건.`,
    pm:`[판정] ${plan.side} · 기본 모의 증거금의 ${(plan.size||0)*100}% 적용. 실거래 주문은 보내지 않아.`,
    blitz:`[계산] 5분 RSI ${f(rs)}. ${mode==='scalp'?'스캘프 관찰이지만 별도 검증되지 않은 전략이야.':'단기 신호는 장기 전망이 아니야.'}`,
    guard:`[계산] 유지증거금률 0.5% 가정. ${plan.guard?'손절선이 추정 청산선보다 가까워.':'거래 보류.'} 거래소 실제 청산가와 다를 수 있어.`
  };
  return {plan,reports,metrics,snapshot:s,algorithm:'signed-v2'};
}
