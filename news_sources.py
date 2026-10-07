"""Registered news providers, with explicit fresh-feed fallback and no model guesses."""
import datetime as dt
import json
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import dashboard

def provider(tool):
    host=urlsplit(tool['url']).hostname
    if host in ('newsapi.ai','www.newsapi.ai','eventregistry.org'):return 'eventregistry'
    if host in ('newsapi.org','www.newsapi.org'):return 'newsapi'

def fetch_tool(app,tool):
    kind=provider(tool)
    if not kind:raise ValueError('지원하는 뉴스 API가 아닙니다.')
    path=app.DATA/'api-keys'/tool['id']
    if not path.exists():raise ValueError('뉴스 API 키가 없습니다.')
    key=path.read_text().strip()
    now=dt.datetime.now(dt.timezone.utc)
    if kind=='eventregistry':
        body={'action':'getArticles','resultType':'articles','categoryUri':'dmoz/Business',
              'sourceLocationUri':['http://en.wikipedia.org/wiki/Canada','http://en.wikipedia.org/wiki/United_States'],
              'lang':'eng','dateStart':(now-dt.timedelta(days=1)).date().isoformat(),
              'articlesSortBy':'date','articlesSortByAsc':False,'articlesCount':20,
              'includeArticleBody':False,'isDuplicateFilter':'skipDuplicates','apiKey':key}
        req=urllib.request.Request('https://eventregistry.org/api/v1/article/getArticles',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    else:
        req=urllib.request.Request('https://newsapi.org/v2/top-headlines?country=us&category=business&pageSize=20',headers={'X-Api-Key':key})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as r:
            data=json.loads(r.read(2*1024**2))
        if data.get('error') or data.get('status')=='error':raise ValueError('뉴스 API가 요청을 거절했습니다. 계정 권한과 잔액을 확인하세요.')
        articles=data.get('articles',{})
        rows=articles.get('results',[]) if isinstance(articles,dict) else articles
        result=[];seen=set()
        for row in rows:
            published=row.get('dateTimePub') or row.get('publishedAt') or row.get('dateTime')
            try:stamp=dt.datetime.fromisoformat(published.replace('Z','+00:00'))
            except (ValueError,TypeError,AttributeError):continue
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
            url=row.get('url','');title=row.get('title','')
            if not title or url in seen or urlsplit(url).scheme not in ('http','https') or not now-dt.timedelta(hours=24)<=stamp<=now+dt.timedelta(minutes=5):continue
            seen.add(url);source=row.get('source') or {}
            result.append({'title':title,'url':url,'published':stamp.isoformat(),'source':source.get('title') or source.get('name') or tool['name']})
        if not result:raise ValueError('뉴스 API에 지난 24시간의 확인 가능한 경제 기사가 없습니다.')
        result.sort(key=lambda r:r['published'],reverse=True)
        app.automation.record_status(app,tool,'ok','경제 뉴스 실제 조회 성공 · '+str(len(result))+'건')
        return {'items':result[:10],'source':tool['name'],'checked_at':now.isoformat(),'stale':False}
    except Exception as error:
        message=('뉴스 API HTTP '+str(error.code)+' · 인증·사용 한도를 확인하세요.') if isinstance(error,urllib.error.HTTPError) else str(error) if isinstance(error,ValueError) else '뉴스 API 연결 실패'
        app.automation.record_status(app,tool,'error',message)
        raise ValueError(message) from None

def business(app):
    failures=[]
    for tool in app.automation.public_tools(app):
        if tool['enabled'] and tool['has_key'] and provider(tool):
            try:return {**fetch_tool(app,tool),'provider_errors':failures}
            except ValueError as e:failures.append(tool['name']+': '+str(e))
    result=dashboard.news('business',force=True)
    if result.get('stale') or not result.get('items'):raise ValueError('현재 경제 뉴스를 확인하지 못했습니다. '+ '; '.join(failures))
    return {**result,'source':'CBC / CNBC','provider_errors':failures}

def briefing(app):
    # Shared full-body, multi-stage intelligence pipeline; no headline fallback.
    import intelligence
    report,text=intelligence.build(intelligence.store(app),'market',intelligence.settings(app))
    return text
