"""Seven-section reader contract. APA references and chart annex retained."""
import html,datetime as dt
from zoneinfo import ZoneInfo
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from ..apa7 import References
from ..report_charts import sections as charts,investment_series
from .editorial import check

def render_pdf(path,envelope,number):
 r=envelope['investment_v2'];check(r);font='AIRI-Editorial'
 if font not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register(font)
 styles={k:ParagraphStyle(k,fontName=font,fontSize=size,leading=lead,spaceAfter=8,wordWrap='CJK',keepWithNext=k in ('title','h')) for k,size,lead in [('title',20,28),('h',14,21),('body',10,17),('small',8,12)]}
 p=lambda text,kind='body':Paragraph(html.escape(str(text)),styles[kind])
 evidence={x['id']:x for x in r['evidence']};apa=References({k:{**v,'title':v['description'].removesuffix(' value'),'kind':'dataset' if v['kind']!='announcement' else ('article' if k.startswith('news') else 'calendar')} for k,v in evidence.items() if v.get('source_url')})
 def source_ids(ids):
  out=[]
  def walk(id,seen):
   if id in seen:return
   seen.add(id);v=evidence.get(id,{})
   if v.get('source_url'):out.append(id)
   else:
    for key in v.get('input_evidence_ids',[]):walk(key,seen)
  for id in ids:walk(id,set())
  return out
 doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=48,bottomMargin=42,title='AIRI 세계 투자 분석',author='AIRI')
 local=dt.datetime.fromisoformat(r['generated_at']).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M PT')
 story=[p('AIRI 세계 투자 분석','title'),p('[관측] 보고서 '+str(number)+' · '+local+' · '+r['mode'].upper(),'small')]
 for i,sec in enumerate(r['editorial']['sections'],1):
  story.append(p(str(i)+'. '+sec['title'],'h'))
  for item in sec['items']:
   if item.get('heading'):story.append(p(item['heading'],'h'))
   for c in item.get('sentences',[item]):
    citation=apa.cite(source_ids(c['evidence_ids'])) if c['evidence_ids'] else ''
    story.append(p('['+c['label']+'] '+c['text']+(' '+citation if citation else '')))
  if i==7:
   story.append(p('[관측] snapshot '+r['snapshot_id']+'이며, 계산과 원자료의 연결은 같은 스냅샷 감사 JSON에 저장한다.','small'))
   for s in r['editorial']['audit']['searches']:story.append(p('[관측] 원인 검색 기록: '+s['query']+' · '+s['status']+' · 본문 검토 '+str(len(s['fetch_ledger']))+'건이다.','small'))
 for flow in charts(investment_series(r),doc.width,font,lambda row:apa.cite(source_ids(row['refs']))):
  if isinstance(flow,Paragraph) and flow.text.startswith('Note.'):
   flow=Paragraph(flow.text.replace('Note.','Note. [관측]',1),flow.style)
  story.append(flow)
 story+=apa.flowables(font)
 def footer(c,d):
  c.saveState();c.setFont(font,7);c.drawString(48,A4[1]-25,'AIRI / CAD READER / '+r['mode'].upper());c.drawRightString(A4[0]-48,22,str(d.page));c.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 from .pdf import speech_chunks
 return {'title':'세계 투자 분석 · CAD 기준','chunks':speech_chunks(envelope.get('spoken_briefing',''))}
