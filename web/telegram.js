(() => {
  const panel=el('article','panel telegram-panel');panel.id='telegram-panel';
  const heading=el('h2','','Telegram · 밖에서도 AIRI'),status=el('p','muted','연결 상태 확인 중'),badge=el('p','footnote');
  const steps=el('ol');
  const first=el('li','','Telegram의 '),father=el('a','','공식 BotFather');father.href='https://t.me/BotFather';father.target='_blank';father.rel='noreferrer';first.append(father,document.createTextNode('에서 /newbot으로 전용 봇을 만드세요.'));
  steps.append(first,el('li','','받은 봇 토큰을 아래에 등록하세요.'),el('li','','표시되는 연결 링크를 휴대폰에서 열고 시작(Start)을 누르세요. 연결한 본인의 개인 메시지만 처리합니다.'));
  const form=el('form'),label=el('label','','봇 토큰'),input=el('input'),connect=el('button','primary','봇 연결');
  input.type='password';input.autocomplete='new-password';input.placeholder='BotFather 토큰';input.required=true;input.maxLength=130;input.id='telegram-token';label.htmlFor=input.id;label.append(input);form.append(label,connect);
  const controls=el('div','approval-actions'),enabledLabel=el('label','reminder-choice'),enabled=el('input'),alertsLabel=el('label','reminder-choice'),alerts=el('input'),pair=el('button','secondary','본인 계정 연결 링크 만들기');
  enabled.type=alerts.type='checkbox';enabledLabel.append(enabled,el('span','','원격 명령 연결'));alertsLabel.append(alerts,el('span','','일정·작업 결과 알림'));controls.append(enabledLabel,alertsLabel,pair);
  const pairing=el('div'),help=el('details'),summary=el('summary','','원격 사용법');
  help.append(summary,el('p','','일반 메시지로 대화·일정·스킬 저장을 요청하세요. 음성 메시지(최대 5분)도 인식합니다.'));
  const commands=el('ul');for(const text of ['/stock — Stock101 모의·실제매매 상태, 손익, 보유, 체결과 전략 조회','/tasks — 일정과 작업 번호 확인','/work 이번 주 공부 계획 작성해줘 — 백그라운드 작업 실행','/result 12 — 12번 작업 결과와 생성 파일 받기','/approvals — API·MCP 실행 승인 버튼','/alerts on 또는 /alerts off — 알림 설정','문서(최대 20MB)에 작업 지시를 캡션으로 첨부하거나, 파일에 답장으로 /work 지시를 보내세요.','MD 파일에 /skill 캡션을 붙이면 스킬로 저장합니다.'])commands.append(el('li','',text));help.append(commands);
  panel.append(heading,status,badge,steps,form,controls,pairing,help,el('p','footnote','Mac이 켜져 있고 잠자기 상태가 아니며 인터넷에 연결되어 있어야 명령과 알림을 처리합니다. 공유기 포트 개방이나 n8n은 필요하지 않습니다. 휴대폰의 Telegram 알림도 켜주세요.'));
  $('page-setup').insertBefore(panel,$('page-setup').querySelector('.setup-guide'));
  const newsForm=el('form'),newsLabel=el('label','','경제 뉴스 · 매일 발송 시간 (설정한 지역)'),newsTime=el('input'),newsOn=el('input'),newsToggle=el('label','reminder-choice'),newsSave=el('button','secondary','뉴스 예약 저장'),newsStatus=el('p','footnote');
  newsTime.type='time';newsTime.value='06:00';newsTime.required=true;newsLabel.append(newsTime);newsOn.type='checkbox';newsToggle.append(newsOn,el('span','','매일 경제 뉴스 받기'));newsForm.append(newsLabel,newsToggle,newsSave,newsStatus);panel.append(newsForm);
  newsForm.onsubmit=async event=>{event.preventDefault();newsSave.disabled=true;try{render(await api('telegram',{news_schedule:{clock:newsTime.value,enabled:newsOn.checked}}));toast('경제 뉴스 예약을 저장했습니다.');}catch(e){toast(e.message);}finally{newsSave.disabled=false;}};
  let loading=false,linked=false,pairTimer;
  function render(data){
    linked=data.paired;enabled.checked=data.enabled;alerts.checked=data.notifications;
    if(!newsForm.contains(document.activeElement)){newsTime.value=data.news_schedule?.clock||'06:00';newsOn.checked=!!data.news_schedule?.enabled;}
    newsStatus.textContent=data.news_schedule?(data.news_schedule.enabled?'다음 발송: '+new Date(data.news_schedule.next_run).toLocaleString():'발송 중지')+' · '+data.news_schedule.last_status+(!data.notifications?' · 전체 알림이 꺼져 있어 발송 대기':''):'예: “매일 아침 6시 경제 뉴스 보내줘”라고 말해도 등록됩니다.';
    enabled.disabled=alerts.disabled=pair.disabled=!data.has_token;
    status.textContent=(data.paired?'본인 계정 연결 완료 · 끝자리 '+data.owner:data.has_token?'휴대폰에서 본인 계정 연결 필요':'봇 토큰 등록 필요')+' · '+data.status;
    badge.textContent=data.has_token?'@'+data.bot_username+' · 토큰 ••••••••'+(data.queued?' · 전송 대기 '+data.queued+'건':''):'';
    if(data.paired&&!data.pair_pending)pairing.replaceChildren();
    if(data.pair_url){
      pairing.replaceChildren();const link=el('a','primary','Telegram에서 본인 계정 연결');link.href=data.pair_url;link.target='_blank';link.rel='noreferrer';
      pairing.append(el('p','','10분 동안 유효한 일회용 연결 링크입니다.'),link,el('p','footnote','휴대폰의 봇 대화에 아래 명령을 보내도 됩니다.'),el('code','',data.pair_command));
      clearTimeout(pairTimer);pairTimer=setTimeout(()=>{pairing.replaceChildren(el('p','','연결 링크가 만료되었습니다. 새 링크를 만들어 주세요.'));},600000);
    }
    if(linked&&!data.pair_pending)clearTimeout(pairTimer);
  }
  async function refreshTelegram(){if(!token||loading)return;loading=true;try{render(await api('telegram'));}catch(e){status.textContent=e.message;}finally{loading=false;}}
  form.onsubmit=async event=>{event.preventDefault();connect.disabled=true;try{render(await api('telegram',{token:input.value.trim()}));input.value='';toast('봇 확인 완료. 연결 링크에서 Start를 눌러주세요.');}catch(e){toast(e.message);}finally{connect.disabled=false;}};
  pair.onclick=async()=>{pair.disabled=true;try{render(await api('telegram',{pair:true}));}catch(e){toast(e.message);}finally{pair.disabled=false;}};
  for(const [control,name] of [[enabled,'enabled'],[alerts,'notifications']])control.onchange=async()=>{control.disabled=true;try{render(await api('telegram',{[name]:control.checked}));}catch(e){control.checked=!control.checked;toast(e.message);}finally{control.disabled=false;}};
  const boot=setInterval(()=>{if(token){clearInterval(boot);refreshTelegram();}},500);
  setInterval(()=>{if(!document.hidden&&$('page-setup').classList.contains('active'))refreshTelegram();},5000);
})();
