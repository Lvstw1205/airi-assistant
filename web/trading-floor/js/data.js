const FAPI='https://fapi.binance.com', BYBIT='https://api.bybit.com';
export function symbolFor(input) {
  const aliases={'비트코인':'BTC','이더리움':'ETH','테슬라':'TSLA','엔비디아':'NVDA','금':'XAU'};
  const value=aliases[String(input).trim()]||String(input).trim().toUpperCase().replace(/(?:\/|-)USDT$|USDT$/,'');
  if(!['BTC','ETH'].includes(value))throw Error(`${value||'종목'}: 이 작업실은 BTC·ETH USDT 무기한 선물만 지원해. 주식은 기존 Stock101에서 확인해.`);
  return value+'USDT';
}
export async function getJSON(url,fetcher=fetch) {
  const response=await fetcher(url,{signal:AbortSignal.timeout(9000)});
  if(!response.ok)throw Error(`HTTP ${response.status}`);
  return response.json();
}
export function candles(rows,interval,now=Date.now(),venue='binance') {
  if(!Array.isArray(rows))return[];
  return rows.map(r=>({time:Number(r[0]),open:Number(r[1]),high:Number(r[2]),low:Number(r[3]),close:Number(r[4]),volume:Number(r[5]),closeTime:venue==='bybit'?Number(r[0])+interval-1:Number(r[6])}))
    .filter(b=>[b.time,b.open,b.high,b.low,b.close,b.volume,b.closeTime].every(Number.isFinite)&&b.close>0&&b.low>0&&b.high>=Math.max(b.open,b.close)&&b.low<=Math.min(b.open,b.close)&&b.closeTime<now)
    .sort((a,b)=>a.time-b.time).filter((b,i,arr)=>!i||b.time!==arr[i-1].time);
}
async function binance(symbol,fetcher) {
  const paths=[`/fapi/v1/klines?symbol=${symbol}&interval=5m&limit=145`,`/fapi/v1/klines?symbol=${symbol}&interval=1h&limit=101`,`/fapi/v1/ticker/24hr?symbol=${symbol}`,`/fapi/v1/premiumIndex?symbol=${symbol}`,`/futures/data/openInterestHist?symbol=${symbol}&period=1h&limit=25`,`/futures/data/topLongShortPositionRatio?symbol=${symbol}&period=1h&limit=1`];
  const raw=await Promise.allSettled(paths.map(p=>getJSON(FAPI+p,fetcher))),v=raw.map(r=>r.status==='fulfilled'?r.value:null),now=Date.now();
  return {venue:'Binance',bars5: candles(v[0],300000,now).slice(-144),bars1: candles(v[1],3600000,now).slice(-100),price:Number(v[2]?.lastPrice)||null,change:Number(v[2]?.priceChangePercent)||0,
    funding:v[3]?Number(v[3].lastFundingRate):null,fundingAsOf:v[3]?.time||null,oi:Array.isArray(v[4])?v[4].map(x=>({time:Number(x.timestamp),value:Number(x.sumOpenInterest)})):[],ratio:v[5]?.[0]?Number(v[5][0].longShortRatio):null,
    errors:raw.flatMap((r,i)=>r.status==='rejected'?[`${paths[i].split('?')[0]}: ${r.reason.message}`]:[]),sources:paths.map(p=>FAPI+p)};
}
async function bybit(symbol,fetcher) {
  const paths=[`/v5/market/kline?category=linear&symbol=${symbol}&interval=5&limit=145`,`/v5/market/kline?category=linear&symbol=${symbol}&interval=60&limit=101`,`/v5/market/tickers?category=linear&symbol=${symbol}`,`/v5/market/open-interest?category=linear&symbol=${symbol}&intervalTime=1h&limit=25`,`/v5/market/account-ratio?category=linear&symbol=${symbol}&period=1h&limit=1`];
  const raw=await Promise.allSettled(paths.map(async p=>{const d=await getJSON(BYBIT+p,fetcher);if(d.retCode!==0)throw Error('Bybit '+d.retCode);return d.result.list;})),v=raw.map(r=>r.status==='fulfilled'?r.value:null),now=Date.now(),ticker=v[2]?.[0];
  return {venue:'Bybit',bars5:candles(v[0],300000,now,'bybit').slice(-144),bars1:candles(v[1],3600000,now,'bybit').slice(-100),price:Number(ticker?.lastPrice)||null,change:Number(ticker?.price24hPcnt)*100||0,
    funding:ticker?Number(ticker.fundingRate):null,fundingAsOf:now,oi:Array.isArray(v[3])?v[3].map(x=>({time:Number(x.timestamp),value:Number(x.openInterest)})).sort((a,b)=>a.time-b.time):[],ratio:v[4]?.[0]&&Number(v[4][0].sellRatio)>0?Number(v[4][0].buyRatio)/Number(v[4][0].sellRatio):null,
    errors:raw.flatMap((r,i)=>r.status==='rejected'?[`${paths[i].split('?')[0]}: ${r.reason.message}`]:[]),sources:paths.map(p=>BYBIT+p)};
}
export async function collect(input,{fetcher=fetch}={}) {
  const symbol=symbolFor(input);let data=await binance(symbol,fetcher);
  if(data.bars5.length<73||data.bars1.length<50||!data.price){const fallback=await bybit(symbol,fetcher);if(fallback.bars5.length>=73&&fallback.bars1.length>=50&&fallback.price)data={...fallback,errors:[...data.errors.map(x=>'Binance unavailable: '+x),...fallback.errors]};else data.errors.push(...fallback.errors);}
  let fear=null,fearAsOf=null;try{const d=await getJSON('https://api.alternative.me/fng/?limit=1',fetcher);fear=Number(d.data[0].value);fearAsOf=Number(d.data[0].timestamp)*1000;}catch(e){data.errors.push('Fear & Greed: '+e.message);}
  const asOf=Date.now();return {...data,symbol,asOf,fear,fearAsOf,contract:'USDT perpetual',quote:'USDT',fixture:false,news:[],sources:[...data.sources,'https://alternative.me/crypto/fear-and-greed-index/'],valid:data.bars5.length>=73&&data.bars1.length>=50&&data.price>0&&asOf-data.bars5.at(-1).closeTime<900000};
}
export function fixture(direction=1) {
  const now=Math.floor(Date.now()/3600000)*3600000;
  const make=(length,step)=>Array.from({length},(_,i)=>{const c=62000+direction*i*28+Math.sin(i*1.7)*100;return {time:now-(length-i)*step,closeTime:now-(length-i-1)*step-1,open:c-25,high:c+55,low:c-70,close:c,volume:20+i%7};});
  const bars5=make(144,300000),bars1=make(100,3600000);return {symbol:'BTCUSDT',venue:'SAMPLE · 가상 데이터',contract:'USDT perpetual',quote:'USDT',bars5,bars1,price:bars5.at(-1).close,change:2.3,funding:.0001,ratio:1.2,oi:[],fear:55,fearAsOf:now,asOf:now,valid:true,fixture:true,errors:[],sources:[],news:[]};
}
