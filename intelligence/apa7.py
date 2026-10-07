"""APA 7 author-date citations. Never infer publication dates from market dates."""
import datetime as dt,html,re
from collections import defaultdict
from urllib.parse import urlsplit
ORG={'finance.yahoo.com':'Yahoo Finance','bankofcanada.ca':'Bank of Canada','home.treasury.gov':'U.S. Department of the Treasury','api.exchange.coinbase.com':'Coinbase','federalreserve.gov':'Board of Governors of the Federal Reserve System','bls.gov':'U.S. Bureau of Labor Statistics','sec.gov':'U.S. Securities and Exchange Commission','statcan.gc.ca':'Statistics Canada'}
def date_value(value):
 try:return dt.datetime.fromisoformat(str(value).replace('Z','+00:00')).date()
 except (ValueError,TypeError):return None

def normalize(s):
 url=s.get('url') or s.get('source_url') or '';host=urlsplit(url).hostname or ''
 author=s.get('author') or s.get('organization_author')
 if not isinstance(author,str):author=None
 if not author:author=next((v for k,v in ORG.items() if host==k or host.endswith('.'+k)),None)
 title=s.get('title') or s.get('name') or s.get('label') or s.get('description') or 'Untitled source'
 if host=='home.treasury.gov':title='Daily Treasury par yield curve rates'
 if host.endswith('bankofcanada.ca') and '/upcoming-events' in url:title='Upcoming events'
 if host.endswith('federalreserve.gov') and 'fomccalendars' in url:title='Federal Open Market Committee calendars'
 published=date_value(s.get('published_at') or s.get('published'))
 return {'url':url,'author':author,'title':title,'date':published,'year':str(published.year) if published else 'n.d.','retrieved':date_value(s.get('retrieved_at') or s.get('collected_at') or s.get('retrieved')),'dynamic':s.get('kind') in ('dataset','calendar','observation','announcement') or s.get('dynamic',False),'site':s.get('source') or s.get('site_name') or ''}

class References:
 def __init__(self,sources):
  self.alias={};unique={}
  for key,s in sources.items():
   x=normalize(s);identity=x['url'] or (x['author'],x['title'],x['year'])
   if identity not in unique:unique[identity]=x
   self.alias[key]=unique[identity]
  self.entries=sorted(unique.values(),key=lambda x:((x['author'] or x['title']).casefold(),x['year'],re.sub(r'^(the|a|an) ','',x['title'],flags=re.I).casefold(),x['url']))
  groups=defaultdict(list)
  for x in self.entries:groups[(x['author'] or x['title'],x['year'])].append(x)
  for group in groups.values():
   for i,x in enumerate(group):x['suffix']=chr(97+i) if len(group)>1 else '';x['date_label']=x['year']+('-' if x['year']=='n.d.' and x['suffix'] else '')+x['suffix']
 def cite(self,ids):
  rows=[]
  for id in ids:
   x=self.alias.get(id)
   if x is not None and x not in rows:rows.append(x)
  rows.sort(key=lambda x:((x['author'] or x['title']).casefold(),x['date_label']))
  return '('+'; '.join((x['author'] or '“'+x['title']+'”')+', '+x['date_label'] for x in rows)+')' if rows else ''
 def reference_html(self,x):
  esc=html.escape;d=x['date'];date=x['date_label'] if not d else str(d.year)+x['suffix']+', '+d.strftime('%B')+' '+str(d.day)
  title='<i>'+esc(x['title'])+'</i>' if not re.search('[가-힣]',x['title']) else esc(x['title'])
  text=(esc(x['author'])+'. ('+date+'). '+title+'.') if x['author'] else title+'. ('+date+').'
  if x['site'] and x['site']!=x['author']:text+=' '+esc(x['site'])+'.'
  if x['dynamic'] and x['retrieved']:text+=' Retrieved '+x['retrieved'].strftime('%B')+' '+str(x['retrieved'].day)+', '+str(x['retrieved'].year)+', from'
  if x['url']:text+=' <link href="'+esc(x['url'],quote=True)+'" color="#153048">'+esc(x['url'])+'</link>'
  return text
 def flowables(self,font):
  from reportlab.lib.styles import ParagraphStyle
  from reportlab.platypus import Paragraph,PageBreak
  from reportlab.pdfbase import pdfmetrics
  from reportlab.pdfbase.ttfonts import TTFont
  if 'APA-Italic' not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register('APA-Italic')
  if 'APA-Bold' not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register('APA-Bold')
  pdfmetrics.registerFontFamily(font,normal=font,bold='APA-Bold',italic='APA-Italic',boldItalic='APA-Italic')
  style=ParagraphStyle('APA7Reference',fontName=font,fontSize=11,leading=22,leftIndent=36,firstLineIndent=-36,spaceAfter=0,wordWrap='CJK')
  heading=ParagraphStyle('APA7ReferencesHeading',fontName=font,fontSize=12,leading=24,alignment=1,spaceAfter=12,keepWithNext=True)
  return [PageBreak(),Paragraph('<b>References</b>',heading)]+[Paragraph(self.reference_html(x),style) for x in self.entries]
