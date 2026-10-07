"""Stable exchange/type identities; provider symbols are not global identities."""
def item(exchange,symbol,name,region,currency,timezone,calendar=None,asset='equity',provider='yahoo',unit=None):
 return dict(instrument_id=f'{exchange}:{asset}:{symbol}',exchange=exchange,symbol=symbol,name=name,region=region,currency=currency,timezone=timezone,calendar=calendar,asset_class=asset,provider=provider,unit=unit or ('index points' if asset=='index' else currency),license_status='Personal research only; redistribution rights not established',frequency='1d')
REGISTRY=[
 item('SPDJI','^GSPC','S&P 500','미국','USD','America/New_York','XNYS','index'),
 item('NASDAQ','^IXIC','나스닥 종합','미국','USD','America/New_York','XNYS','index'),
 item('TSX','^GSPTSE','S&P/TSX','캐나다','CAD','America/Toronto','XTSE','index'),
 item('KRX','^KS11','코스피','한국','KRW','Asia/Seoul','XKRX','index'),
 item('OSE','^N225','닛케이 225','일본','JPY','Asia/Tokyo','XTKS','index'),
 item('HKEX','^HSI','항셍','중국/홍콩','HKD','Asia/Hong_Kong','XHKG','index'),
 item('XETRA','^GDAXI','독일 DAX','유럽','EUR','Europe/Berlin','XFRA','index'),
 item('LSE','^FTSE','FTSE 100','유럽','GBP','Europe/London','XLON','index'),
 item('NASDAQ','AAPL','애플','미국','USD','America/New_York','XNYS'),
 item('NASDAQ','NVDA','엔비디아','미국','USD','America/New_York','XNYS'),
 item('NASDAQ','MSFT','마이크로소프트','미국','USD','America/New_York','XNYS'),
 item('TSX','RY.TO','로열뱅크','캐나다','CAD','America/Toronto','XTSE'),
 item('TSX','SHOP.TO','쇼피파이','캐나다','CAD','America/Toronto','XTSE'),
 item('KRX','005930.KS','삼성전자','한국','KRW','Asia/Seoul','XKRX'),
]
for symbol,name,unit in [('CL=F','WTI 선물','USD/barrel'),('BZ=F','Brent 선물','USD/barrel'),('GC=F','금 선물','USD/troy oz'),('HG=F','구리 선물','USD/lb')]:
 REGISTRY.append(item('CME' if symbol!='BZ=F' else 'ICE',symbol,name,'글로벌','USD','America/New_York',None,'commodity','yahoo',unit))
for symbol in ('USD/CAD','USD/KRW','EUR/USD','USD/JPY'):
 REGISTRY.append(item('BOC',symbol,symbol,'글로벌',symbol[4:],'America/Toronto',None,'fx','boc',f'{symbol[4:]} per 1 {symbol[:3]}'))
for symbol,name,region,provider in [('ca2y','캐나다 2년','캐나다','boc'),('ca10y','캐나다 10년','캐나다','boc'),('us2y','미국 2년','미국','treasury'),('us10y','미국 10년','미국','treasury')]:
 REGISTRY.append(item('BOC' if provider=='boc' else 'UST',symbol,name,region,None,'America/New_York',None,'rates',provider,'percent'))
for symbol,name in [('BTC-USD','비트코인'),('ETH-USD','이더리움')]:REGISTRY.append(item('COINBASE',symbol,name,'글로벌','USD','UTC',None,'crypto','coinbase','USD per coin'))
BY_ID={x['instrument_id']:x for x in REGISTRY}
DEFAULT_IDS=[x['instrument_id'] for x in REGISTRY if x['asset_class']!='equity']
UNSUPPORTED=['중국 본토 개별 종목','기타 신흥국','신용 스프레드','온체인·펀딩·미결제약정','TSX 전체 구성종목 기여도']
def resolve(value):
 if value not in BY_ID:raise ValueError('지원 목록에서 거래소와 종목 종류를 확인해 선택해 줘.')
 return dict(BY_ID[value])
def search(query=''):
 q=str(query).casefold().strip()
 return [dict(x) for x in REGISTRY if not q or q in ' '.join(str(v) for v in x.values()).casefold()]
