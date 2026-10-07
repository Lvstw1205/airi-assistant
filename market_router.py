"""Deterministic finance routing. Missing data never falls through to a guessed quote."""
import re
import mcp_bridge
CURRENCIES={'USD','CAD','EUR','GBP','JPY','KRW','AUD','CHF','CNY','HKD','INR','NZD'}
ALIASES={'리얼티 인컴':'O','리얼티인컴':'O','realty income':'O','tesla':'TSLA','테슬라':'TSLA','apple':'AAPL','애플':'AAPL','nvidia':'NVDA','엔비디아':'NVDA','microsoft':'MSFT','amazon':'AMZN','royal bank':'RY.TO','rbc':'RY.TO','td bank':'TD.TO','shopify':'SHOP.TO','s&p 500':'^GSPC','tsx':'^GSPTSE'}
CA={'RY','TD','BMO','BNS','CM','ENB','CNQ','SU','CNR','CP','BCE','XEQT','VEQT','VFV','XIC','VCN','ZSP'}
STOP={'I','A','THE','IS','WHAT','HOW','ARE','CAN','US','USA','CA','API','MCP','ETF','STOCK','PRICE','PE','USD','CAD','EUR','GBP','JPY','KRW','AUD','TODAY','BUY','SELL','OF','TO','AND','IN','IT','FOR','MY'}
def is_outlook(query):
    return bool(re.search(r'전망|예측|목표\s*가|오를까|떨어질까|outlook|forecast|predict|price target|perspectives|prévision|objectif',query,re.I))

def contextual_query(query,history):
    # Resolve short follow-ups from user questions only, never from generated prices.
    if intent(query):return query
    followup=re.search(r'전망|예측|다시|그럼|그건|그거|왜|근거|출처|outlook|forecast|again|what about|source|why|prévision|encore',query,re.I)
    if followup and len(query)<160:
        for message in reversed((history or [])[-6:]):
            if message.get('role')=='user':
                prior=message.get('content','')
                if intent(prior):return prior+'\n'+query
                break
    return query

def intent(query):
    q=query.lower()
    if re.search(r'exchange\s*rate|currency|forex|taux de change|devises|환율|환전|\b(?:usd|cad)\s*[/→-]\s*(?:usd|cad)\b',q) or (len(re.findall(r'\b(?:USD|CAD|EUR|GBP|JPY|KRW|AUD)\b',query,re.I))>=2):return 'fx'
    known=any(re.search(re.escape(a),q) for a in ALIASES)
    if is_outlook(q) and (known or re.search(r'주식|주가|투자|배당|종목|stock|invest|share|\b[0-9]+\s*(?:년|years?)',q)):return 'outlook'
    if re.search(r'invest|cours|bourse|actions|stock|share price|quote|ticker|\betf\b|dividend|market|주식|주가|투자|배당|시세|종목',q):return 'quote'
    if any(re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',q) for a in ALIASES) and re.search(r'price|worth|가격|얼마',q):return 'quote'
    return None

def fx_args(query):
    q=query
    for pattern,code in [(r'캐나다\s*달러|canadian\s*dollars?','CAD'),(r'미국\s*달러|us\s*dollars?','USD'),(r'한국\s*원|원화|korean\s*won','KRW')]:q=re.sub(pattern,code,q,flags=re.I)
    codes=[]
    for c in re.findall(r'\b[A-Za-z]{3}\b',q):
        if c.upper() in CURRENCIES and c.upper() not in codes:codes.append(c.upper())
    if len(codes)>2:raise ValueError('Please request one currency pair at a time.')
    base,quote=(codes+[c for c in ('USD','CAD') if c not in codes])[:2]
    amount=re.search(r'(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:'+base+r'|dollars?|달러)',q,re.I)
    return {'base':base,'quote':quote,'amount':float(amount[1].replace(',','')) if amount else 1}

def symbols(query):
    found=[];q=query.lower()
    for name,ticker in ALIASES.items():
        if (name in q if re.search('[가-힣]',name) else re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',q)):found.append(ticker)
    for ticker in re.findall(r'\$([A-Za-z][A-Za-z0-9.\-]{0,12})|\b([A-Z][A-Z0-9.\-]{0,12})\b',query):
        t=(ticker[0] or ticker[1]).upper().rstrip('.')
        if t in STOP:continue
        if t in CA and not re.search(r'\bNYSE\b|US listing|미국 상장',query,re.I):t+='.TO'
        if t not in ('NYSE','NASDAQ','TSX'):found.append(t)
    return list(dict.fromkeys(found))[:3]

def lookup(app,query,history=None):
    original=query
    query=contextual_query(query,history)
    action=intent(query)
    if action=='quote' and is_outlook(query):action='outlook'
    if not action:return None
    if re.search(r'하지\s*마|do not (?:look|fetch|check)|don.t (?:look|fetch|check)',query,re.I):return {'text':'Live lookup skipped as requested. No current price has been verified.','cards':[]}
    korean=bool(re.search('[가-힣]',query))
    french=bool(re.search(r'\b(quel|quelle|bonjour|taux|cours|bourse|actions|devises|combien|donne|prix)\b',query,re.I))
    if action=='outlook':
        # A quote provider is not a source for annual multi-year price predictions.
        tickers=symbols(query)
        name='Realty Income (NYSE: O)' if 'O' in tickers else ', '.join(tickers)
        if korean:
            text=(name+' — ' if name else '')+'현재 연결된 시세 도구로는 연도별 장기 목표주가를 검증할 수 없어. 앞선 답변에 출처 없이 제시한 미래 가격이 있다면 철회할게. 확인하지 않은 웹사이트를 참고했다고 말하거나 전망 숫자를 만들어서는 안 돼.'
            if 'O' in tickers:
                text+='\n리얼티 인컴의 미국 상장 주가는 USD 기준으로 확인해야 해. 장기 전망을 분석하려면 주당 AFFO(배당 여력을 볼 때 참고하는 지표), 배당 지급 비율, 차입·차환 비용, 임차인과 공실 위험을 확인해야 해. 회사 공시와 명시적인 가정에 근거한 시나리오는 확정적인 미래 가격과 구분해야 해.\n공시 확인 위치: https://www.realtyincome.com/investors/quarterly-and-annual-results\n이 답변에서 최신 공시를 실시간으로 조회한 것은 아니야.'
        elif french:
            text=(name+' — ' if name else '')+"Les outils connectés ne vérifient pas les objectifs de cours annuels à long terme. Je retire toute projection précédente sans source. Une cotation actuelle ne permet pas de prévoir les prix futurs : il faut des données financières datées et des hypothèses explicites."
        else:
            text=(name+' — ' if name else '')+'The connected quote tools do not verify annual long-term price targets. I retract any earlier unsourced projections. A current quote is not a multi-year forecast; a scenario needs dated financial statements and explicit assumptions. No fresh filings were retrieved for this answer.'
        return {'text':text,'cards':[]}
    try:
        if action=='fx':
            args=fx_args(query);r=mcp_bridge.request(app,'market','call','market_exchange_rate',args)
            label=f"1 {r['base']} = {r['rate']:.6f} {r['quote']}"
            text=label+f"\nAs of {r['as_of']} · {r['source']} · daily indicative reference rate."
            if args['amount']!=1:text+=f"\n{r['amount']:,.2f} {r['base']} ≈ {r['converted']} {r['quote']}."
            text+='\n은행·카드 환전 수수료가 포함되지 않은 일일 참고 환율이야.' if korean else '\nThis is a daily reference rate, not a live executable bank quote; fees and spreads are excluded.'
            text+='\n'+r.get('source_url','')
            if r.get('stale'):text+='\nThe published rate is over five days old; do not treat it as current.'
            if french:
                text=label+f"\nRéférence du {r['as_of']} · {r['source']}. Taux indicatif quotidien, hors frais bancaires."
                if args['amount']!=1:text+=f"\n{r['amount']:,.2f} {r['base']} ≈ {r['converted']} {r['quote']}."
                if r.get('stale'):text+='\nAttention : cette référence date de plus de cinq jours et ne constitue pas un taux actuel.'
                text+='\n'+r.get('source_url','')
            return {'text':text,'cards':[r]}
        tickers=symbols(query)
        if not tickers:return {'text':('Quelle action ou quel FNB souhaitez-vous consulter ? Par défaut : Canada et États-Unis, par exemple AAPL ou RY.TO.' if french else '어떤 종목을 볼까? 캐나다·미국 기준으로 AAPL, RY.TO, VFV.TO처럼 알려줘.' if korean else 'Which stock or ETF? I default to Canadian and US listings—for example AAPL, RY.TO, or VFV.TO. Add .TO for Toronto.'),'cards':[]}
        cards=[];texts=[]
        for ticker in tickers:
            r=mcp_bridge.request(app,'market','call','market_quote',{'symbol':ticker});cards.append(r)
            line=f"{r.get('shortName') or ticker} ({ticker}) — {r['price']:,.2f} {r['currency']}\nQuote time: {r['as_of']} · {r.get('fullExchangeName') or r.get('exchange') or 'exchange unspecified'} · Yahoo Finance."
            if r.get('trailingPE') is not None:line+=f"\nTrailing P/E: {r['trailingPE']:.2f}."
            line+='\nLatest available regular-session quote; may be delayed.\n'+r['source_url']
            if r.get('stale'):line+=' Older than 24 hours—this is not a fresh trading quote.'
            if french:
                line=f"{r.get('shortName') or ticker} ({ticker}) — {r['price']:,.2f} {r['currency']}\nCotation du {r['as_of']} · Yahoo Finance. Dernier cours disponible, potentiellement différé."
                if r.get('stale'):line+=' Cette cotation date de plus de 24 heures.'
                line+='\n'+r['source_url']
            elif korean:
                line=f"{r.get('shortName') or ticker} ({ticker}) — {r['price']:,.2f} {r['currency']}\n기준 시각: {r['as_of']} · Yahoo Finance. 최근 정규장 시세이며 지연될 수 있어."
                if r.get('stale'):line+=' 24시간 이상 지난 시세이므로 현재 거래 가격과 구분해줘.'
                line+='\n'+r['source_url']
            texts.append(line)
        return {'text':'\n\n'.join(texts),'cards':cards}
    except Exception:
        return {'text':('Je ne peux pas vérifier les données financières actuelles. Vérifiez le symbole ou la devise et réessayez.' if french else '현재 금융 데이터를 확인하지 못했어. 추정 숫자는 제시하지 않을게. 종목·통화와 연결 상태를 확인해줘.' if korean else 'I couldn’t verify current market data. I won’t substitute an estimated number. Check the ticker/currency and try again.'),'cards':[]}
