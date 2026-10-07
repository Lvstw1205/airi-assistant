"""Free public retrieval, local inference, bounded and independently configurable briefs."""
WEIGHTS = dict(impact=.25, relevance=.20, novelty=.15, credibility=.15, persistence=.15, urgency=.10)
INTERESTS = ['Canada','United States','South Korea','Configured location','British Columbia','AI','technology','financial markets','macroeconomics','corporations','labour','business strategy']
PROFILES = {
 'morning':dict(label='Morning Brief',hours=24,topics=[]),
 'evening':dict(label='Evening Brief',hours=12,topics=[]),
 'breaking':dict(label='Breaking News Brief',hours=6,topics=[]),
 'market':dict(label='Market Brief',hours=24,topics=['macroeconomics','monetary_policy','markets','energy','labour']),
 'technology':dict(label='AI & Technology Brief',hours=24,topics=['AI','technology','companies','regulation','supply_chains']),
 'canada':dict(label='Canada Brief',hours=24,topics=['Canada','Configured location','British Columbia']),
 'korea':dict(label='Korea Brief',hours=24,topics=['South Korea']),
 'company':dict(label='Company Intelligence Brief',hours=24,topics=['companies']),
}
# Feed URLs published by the organizations; paywalls are never bypassed.
FEEDS = [
 ('Bank of Canada','https://www.bankofcanada.ca/content_type/press-releases/feed/',['Canada','monetary_policy']),
 ('Federal Reserve','https://www.federalreserve.gov/feeds/press_all.xml',['United States','monetary_policy','regulation']),
 ('Statistics Canada','https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom',['Canada','macroeconomics','labour']),
 ('Bank of Korea','https://www.bok.or.kr/eng/bbs/E0000634/news.rss?menuNo=400069',['South Korea','monetary_policy']),
 ('CBC Business','https://www.cbc.ca/webfeed/rss/rss-business',['Canada','markets','companies']),
 ('CBC British Columbia','https://www.cbc.ca/webfeed/rss/rss-canada-britishcolumbia',['Canada','Configured location','British Columbia']),
 ('CNBC Business','https://www.cnbc.com/id/100003114/device/rss/rss.html',['United States','markets','companies']),
 ('CNBC Technology','https://www.cnbc.com/id/19854910/device/rss/rss.html',['AI','technology']),
 ('BBC World','https://feeds.bbci.co.uk/news/world/rss.xml',['geopolitics']),
 ('NPR World','https://feeds.npr.org/1004/rss.xml',['geopolitics']),
]
TOPICS = {
 'macroeconomics':r'GDP|inflation|CPI|economy|경제|물가',
 'monetary_policy':r'central bank|Federal Reserve|Bank of Canada|Bank of Korea|interest rate|금리|한국은행',
 'markets':r'stock|bond|yield|currency|equities|증시|주가|채권|환율',
 'AI':r'\bAI\b|artificial intelligence|OpenAI|인공지능',
 'technology':r'technolog|semiconductor|chip|software|기술|반도체',
 'companies':r'company|earnings|revenue|corporat|기업|실적|매출',
 'geopolitics':r'war|sanction|tariff|export control|전쟁|제재|관세',
 'energy':r'oil|energy|electricity|gas|power grid|원유|에너지|전력',
 'regulation':r'regulat|court|antitrust|법원|규제',
 'labour':r'labour|labor|jobs|employment|wages|고용|노동|실업',
 'supply_chains':r'supply chain|shipping|logistic|공급망|물류',
}
TIERS = {
 1:['bankofcanada.ca','federalreserve.gov','statcan.gc.ca','bls.gov','bea.gov','sec.gov','canada.ca','gov.bc.ca','bok.or.kr','kostat.go.kr','kosis.kr','ftc.gov','justice.gov','supremecourt.gov','ecb.europa.eu','imf.org','oecd.org','sedarplus.ca','treasury.gov','investor.nvidia.com','investor.apple.com','microsoft.com','investor.fb.com','abc.xyz','investor.tsmc.com','rbc.com','td.com','bmo.com','cibc.com','scotiabank.com','nbc.ca','cnrl.com','suncor.com','cenovus.com','enbridge.com','tcenergy.com'],
 2:['tmx.com','tsx.com','cmegroup.com','cboe.com','theice.com','spglobal.com'],
 3:['finance.yahoo.com','morningstar.com','simplywall.st','marketwatch.com','investing.com'],
 4:['reuters.com','bloomberg.com','apnews.com','ft.com','wsj.com','theglobeandmail.com','bnnbloomberg.ca','bbc.com','bbc.co.uk','cbc.ca','cnbc.com','economist.com','npr.org','nytimes.com','yonhapnews.co.kr','en.yna.co.kr','arstechnica.com','theverge.com','techcrunch.com','nature.com','science.org','ieee.org','x.com','twitter.com','reddit.com','facebook.com','tiktok.com','youtube.com'],
}
# Unknown publishers are unverified, not automatically "specialist" evidence.
DEFAULTS = dict(max_articles=12,max_events=4,article_chars=14000,context_days=30,cache_minutes=30,model='gemma4:latest',language='ko',enrich_events=2,deadline_seconds=840)

SOURCE_POLICY='source-hierarchy/2'
TRUSTED_JOURNALISM={'reuters.com','bloomberg.com','ft.com','wsj.com','theglobeandmail.com','bnnbloomberg.ca','apnews.com'}
