/* Presentation-side intent checks. Existing server risk/confirmation gates remain authoritative. */
(()=>{
 'use strict';
 const phrase='실제 돈으로 자동매매 시작';
 function tradeAction(mode,desired,snapshot,confirmation={},now=Date.now()/1000){
  if(!['paper','live'].includes(mode)||typeof desired!=='boolean')throw Error('잘못된 제어 요청이야.');
  if(!snapshot||!Number.isFinite(snapshot.checked_at)||now-snapshot.checked_at>30||snapshot.checked_at>now+5)throw Error('상태가 오래됐어. 새로고침 후 다시 눌러줘.');
  const node=snapshot[mode];if(!node?.available)throw Error('현재 상태를 확인한 뒤 제어할 수 있어.');
  if(desired===node.enabled)return null;
  if(!desired)return 'crypto_'+(mode==='live'?'live_stop':'multi_stop');
  if(mode==='paper'){
   if(snapshot.live?.enabled)throw Error('실제매매를 중지한 뒤 모의매매를 켜줘.');
   return 'crypto_multi_start';
  }
  if(!node.configured)throw Error('먼저 상세보기에서 실제매매 계정과 예산을 설정해 줘.');
  if(confirmation.confirmed!==true||confirmation.confirmation!==phrase)throw Error('실제 자금 사용 확인과 시작 문구 입력이 필요해.');
  return 'crypto_live_start';
 }
 const policy={tradeAction,phrase};
 if(typeof module!=='undefined'&&module.exports)module.exports=policy;
 else window.AIRIDashboardPolicy=policy;
})();
