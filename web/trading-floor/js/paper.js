const KEY='airi.pixel.demo.v1';
export function fresh(){return {version:1,balance:10000,initial:10000,positions:[],closed:[],curve:[10000],seen:[]};}
export function load(storage){try{const a=JSON.parse(storage.getItem(KEY));if(a?.version===1&&Number.isFinite(a.balance)&&Array.isArray(a.positions)&&Array.isArray(a.closed)&&Array.isArray(a.curve)&&Array.isArray(a.seen))return a;}catch{}return fresh();}
export function save(account,storage){try{storage.setItem(KEY,JSON.stringify(account));return true;}catch{return false;}}
export function open(account,plan,snapshot,runId){
  if(!runId||account.seen.includes(runId)||plan.side==='HOLD'||!plan.guard||!snapshot.valid||snapshot.fixture||account.positions.some(p=>p.symbol===snapshot.symbol))return false;
  const margin=Math.min(account.balance*.01*plan.size,account.balance-account.positions.reduce((a,p)=>a+p.margin,0));if(margin<=0)return false;
  const fee=margin*plan.lev*.0005;if(account.balance<margin+fee)return false;
  account.balance-=fee;account.positions.push({...plan,symbol:snapshot.symbol,venue:snapshot.venue,margin,quantity:margin*plan.lev/plan.entry,opened:snapshot.asOf,lastCheck:snapshot.asOf,runId,entryFee:fee});account.seen.push(runId);account.seen=account.seen.slice(-500);return true;
}
export function mark(account,snapshot){
  if(!snapshot?.valid||snapshot.fixture)return;
  for(const p of [...account.positions]){
    if(p.symbol!==snapshot.symbol||p.venue!==snapshot.venue||snapshot.asOf<=p.lastCheck)continue;
    const long=p.side==='LONG',bars=snapshot.bars5.filter(b=>b.time>=p.lastCheck&&b.closeTime>=p.opened);
    let exit=null,reason='',ambiguous=false;
    for(const b of bars){
      const stop=long?b.low<=p.sl:b.high>=p.sl,target=long?b.high>=p.tp:b.low<=p.tp;
      if(stop&&target){exit=long?Math.min(b.open,p.sl):Math.max(b.open,p.sl);reason='SL (같은 봉 TP/SL · 보수적 처리)';ambiguous=true;break;}
      if(stop){exit=long?Math.min(b.open,p.sl):Math.max(b.open,p.sl);reason='SL';break;}
      if(target){exit=p.tp;reason='TP';break;}
    }
    if(exit===null){const price=snapshot.price;if(long?price<=p.sl:price>=p.sl){exit=price;reason='SL · 관측 가격';}else if(long?price>=p.tp:price<=p.tp){exit=p.tp;reason='TP · 관측 가격';}}
    if(exit!==null){const liquidated=long?exit<=p.liq:exit>=p.liq;const fee=p.quantity*exit*.0005;const pnl=liquidated?-p.margin:Math.max(-p.margin,p.quantity*(exit-p.entry)*(long?1:-1)-fee);if(liquidated)reason='LIQ · 갭 발생 · 격리 증거금 전액 손실 가정';account.balance+=pnl;account.closed.push({...p,exit,reason,ambiguous,liquidated,pnl:pnl-p.entryFee,closed:snapshot.asOf,funding:'미반영'});account.positions=account.positions.filter(x=>x!==p);account.curve.push(account.balance);}
    else p.lastCheck=bars.at(-1)?.closeTime||p.lastCheck;
  }
  account.closed=account.closed.slice(-300);account.curve=account.curve.slice(-500);
}
export function stats(account){let peak=account.initial,mdd=0;for(const b of account.curve){peak=Math.max(peak,b);mdd=Math.max(mdd,(peak-b)/peak*100);}return {balance:account.balance,pnl:account.balance-account.initial,wins:account.closed.length?100*account.closed.filter(x=>x.pnl>0).length/account.closed.length:null,mdd,positions:account.positions.length,trades:account.closed.length};}
