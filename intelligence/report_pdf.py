"""Evidence-preserving Korean research layout; no model-generated facts at export."""
import datetime as dt, html, re, sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable

HEADINGS={
 'EXECUTIVE ASSESSMENT':'핵심 판단', 'TOP DEVELOPMENTS':'주요 사건과 분석',
 'Development':'확인한 내용', 'Context':'배경과 맥락', 'Why It Matters':'왜 중요한가',
 'What Is Driving It':'원인과 전달 경로', 'First-order Implications':'1차 영향',
 'Second-order Implications':'2차 파급효과', 'Potential Beneficiaries':'수혜 가능 영역',
 'Exposed Parties':'위험 노출 영역', 'Key Uncertainty':'반론과 미확인 사항',
 'Watch Next':'후속 확인 지표', 'CROSS-MARKET / CROSS-SECTOR SIGNALS':'시장·산업 간 연결',
 'EMERGING TRENDS':'추세 판단', 'MARKET / BUSINESS IMPLICATIONS':'시장·기업에 대한 시사점',
 'RISK RADAR':'위험 시나리오', 'WATCHLIST — NEXT 24–72 HOURS':'다음 24~72시간 관찰 대상',
 'BOTTOM LINE':'결론', 'Retrieval / Quality Limits':'자료 수집과 검증의 한계'}
LABELS={
 'SIGNAL / conditional analysis:':'조건부 해석:','ANALYSIS — conditional implication:':'조건부 영향:',
 'SCENARIO — Risk | Trigger | Potential consequence:':'시나리오 - 위험 | 조건 | 결과:',
 'UNCERTAINTY — reported, not independently confirmed:':'단일 출처 보도·독립 확인 전:',
 'UNCERTAINTY — conflicting report:':'출처 간 상충:', 'SIGNAL — Emerging trend:':'추세 신호:',
 'FACT — sourced market observation:':'출처로 확인한 시장 반응:',
 'ANALYSIS:':'해석:', 'FACT:':'확인된 사실:', 'UNCERTAINTY:':'미확인 사항:', 'WATCH ITEM:':'관찰 지표:', 'SIGNAL:':'신호:',
 'Event time unverified; publication time is not event time.':'사건 발생 시점은 미확인입니다. 기사 발행 시각과 구분해야 합니다.',
 'No additional uncertainty was extracted; this does not imply certainty.':'추가 불확실성을 추출하지 못했으며, 확실하다는 뜻은 아닙니다.'}
LINK=re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')

def localize(line):
 for a,b in LABELS.items():line=line.replace(a,b)
 return line.replace('—','-').replace('–','-').replace('→',' > ')

def blocks(report,text):
 """Only already published (budgeted, reviewed) prose enters PDF and narration."""
 out=[];refs=[];seen={};source_by_url={s['url']:s for s in report.get('historical_sources',[])+report.get('sources',[])}
 for raw in text.splitlines():
  line=raw.strip()
  if not line:continue
  if line.startswith(('# AIRI INTELLIGENCE', 'Date:', 'Coverage Window:', 'Sources Reviewed:')) or line==report.get('profile_label'):continue
  if line=='Sources:' or line.startswith(('- [','Classification:','Event time:','Evidence events:')):continue
  if line.startswith('Confidence:'):
   level=line.split(':',1)[1].strip();out.append(('meta','근거 신뢰도: '+{'LOW':'낮음','MEDIUM':'중간','HIGH':'높음'}.get(level,level)));continue
  if line.startswith('- Article body not reviewed:'):continue  # Exact failures are in the appendix.
  def link(m):
   url=m[2]
   if url not in seen:
    seen[url]=len(refs)+1;refs.append({'number':seen[url],'label':m[1],'url':url,**source_by_url.get(url,{})})
   return ' ['+str(seen[url])+']'
  line=LINK.sub(link,line)
  if line.startswith('#'):
   level=len(line)-len(line.lstrip('#'));heading=line.lstrip('#').strip()
   if heading=='TOP DEVELOPMENTS':continue
   out.append(('h'+str(min(level,3)),localize(HEADINGS.get(heading,heading))))
  else:out.append(('p',localize(line.lstrip('- '))))
 return out,refs

def narration(report,text):
 result=[]
 speech=[('p',line) for line in report.get('spoken_briefing',[])] if report.get('delivery_style') in ('article_commentary','financial_research') else blocks(report,text)[0]
 for kind,line in speech:
  if kind=='meta':continue
  line=re.sub(r'\[\d+\]','',line)
  line=re.sub(r'https?://\S+','',line)
  line=re.sub(r'AIRI_(?:RESULT|TASK)_\S+','',line)
  line=re.sub(r'(?<![A-Za-z])AIRI(?![A-Za-z_])','아이리',line,flags=re.I).strip()
  if not line:continue
  # Sentences stay small; no huge TTS request or parallel GPU queue.
  for sentence in re.split(r'(?<=[.!?。])\s+|\n+',line):
   while len(sentence)>150:
    cut=sentence.rfind(' ',50,150)
    if cut<50:cut=150
    result.append(sentence[:cut].strip());sentence=sentence[cut:].strip()
   if sentence:result.append(sentence)
 return result

def render_pdf(path,report,text,number):
 if report.get('professional_research'):
  from research_desk.render import render_pdf as render_desk
  meta=render_desk(path,report,number)
  if not meta['layout_target_met']:raise ValueError('Research page target not met ('+str(meta['pages'])+' pages). The draft requires depth/length revision before publication.')
  return meta
 if report.get('investment_v2'):
  from .investment.pdf import render_pdf as investment_pdf
  return investment_pdf(path,report,number)
 if report.get('delivery_style')=='financial_research':
  from .research_pdf import render_pdf as render_research
  return render_research(path,report,number)
 if 'AIRI-Korean' not in pdfmetrics.getRegisteredFontNames():
  __import__('pdf_font').register('AIRI-Korean')
 font='AIRI-Korean';navy=colors.HexColor('#142C43');teal=colors.HexColor('#087D87');grey=colors.HexColor('#5A6976');light=colors.HexColor('#EAF0F4')
 styles={
  'p':ParagraphStyle('Body',fontName=font,fontSize=9.3,leading=15.8,textColor=navy,wordWrap='CJK',spaceAfter=7),
  'h1':ParagraphStyle('Major',fontName=font,fontSize=16,leading=24,textColor=navy,spaceBefore=18,spaceAfter=10,keepWithNext=True,wordWrap='CJK'),
  'h2':ParagraphStyle('Section',fontName=font,fontSize=12,leading=18,textColor=navy,spaceBefore=14,spaceAfter=8,keepWithNext=True,wordWrap='CJK'),
  'h3':ParagraphStyle('Sub',fontName=font,fontSize=10,leading=16,textColor=teal,spaceBefore=8,spaceAfter=4,keepWithNext=True,wordWrap='CJK'),
  'meta':ParagraphStyle('Meta',fontName=font,fontSize=7.8,leading=12,textColor=grey,wordWrap='CJK',spaceAfter=6),
  'title':ParagraphStyle('Title',fontName=font,fontSize=23,leading=32,textColor=navy,wordWrap='CJK',spaceAfter=12)}
 def p(s,kind='p'):return Paragraph(html.escape(str(s)),styles[kind])
 generated=dt.datetime.now(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y.%m.%d %H:%M')
 asof=dt.datetime.fromisoformat(report['created']).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y.%m.%d %H:%M')
 title=('기사 스크랩과 아이리 생각' if report.get('delivery_style')=='article_commentary' else None) or report.get('query') or {'morning':'뉴스·거시경제 분석','market':'시장·거시경제 분석','technology':'AI·기술 산업 분석','company':report.get('company','기업')+' 분석'}.get(report['profile'],'뉴스·시장 분석')
 doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=53,bottomMargin=48,title=title,author='AIRI · Local Research',pageCompression=1)
 story=[p('AIRI  /  RESEARCH REPORT '+str(number),'meta'),Spacer(1,9),p(title,'title'),p('분석 기준 '+asof+'  |  PDF 작성 '+generated+'  |  설정한 지역 시간','meta'),HRFlowable(width='100%',thickness=2,color=teal),Spacer(1,12)]
 cov=report.get('coverage',{});confirmed=sum(len(e.get('confirmed_facts',[])) for e in report['events'])
 table=Table([[p('검토한 기사 본문','meta'),p('분석한 사건','meta'),p('확인된 사실','meta')],[p(str(len(report['sources']))+'건','h2'),p(str(len(report['events']))+'건','h2'),p(str(confirmed)+'건','h2')]],colWidths=[doc.width/3]*3)
 table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),light),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,1),(-1,1),6)]));story.extend([table,Spacer(1,12)])
 if report.get('status')=='limited' or confirmed==0:story.append(p('근거 제한: 독립 확인 또는 검토를 통과한 분석이 충분하지 않습니다. 관측되지 않은 시장 반응·수익률·목표 가격을 추정해 채우지 않습니다.','meta'))
 body,refs=blocks(report,text)
 from .apa7 import References
 if report.get('delivery_style')=='article_commentary':
  refs=[{**s,'number':i+1} for i,s in enumerate(report.get('sources',[]))]
 apa=References({str(ref['number']):ref for ref in refs})
 body=[(kind,re.sub(r'\[(\d+)\]',lambda m:apa.cite([m[1]]),line)) for kind,line in body]
 if report.get('delivery_style')=='article_commentary':
  if report.get('query'):story.append(p('요청 주제: '+report['query'],'meta'))
  story.append(p('기사 내용과 아이리의 해석을 나눠 읽는 보고서입니다. 음성 브리핑은 핵심 소개, 내용 설명, 아이리 생각 순서로 짧게 전달합니다.','meta'))
  sources={s['id']:s for s in report['sources']}
  for index,card in enumerate(report.get('published_cards',[]),1):
   source=sources[card['source_id']]
   if index>1:story.append(PageBreak())
   story.append(p('기사 '+str(index)+' | '+source['title'],'h1'))
   story.append(p(apa.cite([str(next(i+1 for i,src in enumerate(report['sources']) if src['id']==source['id']))]),'meta'))
   story.append(p(source['source']+' · 발행 '+(source.get('published') or '미확인')+' · 수집 '+source['retrieved'],'meta'))
   story.append(Paragraph('<link href="'+html.escape(source['url'],quote=True)+'" color="#087D87">원문 열기: '+html.escape(source['url'])+'</link>',styles['meta']))
   story.append(p('기사 원문 스크랩' if card['mode']=='original' else '기사 핵심 발췌','h2'))
   if card['partial']:story.append(p('수집된 본문 일부입니다. 원문 전체는 위 링크에서 확인할 수 있습니다.','meta'))
   elif card['mode']!='original':story.append(p('짧은 원문 발췌와 검증된 내용 요약입니다. 기사 전문은 위 원문 링크에서 읽을 수 있습니다.','meta'))
   for paragraph in card['body'].split('\n\n'):story.append(p(paragraph))
   if card['mode']!='original':
    story.append(p('기사 내용 설명','h3'))
    for paragraph in card['summary']:story.append(p(paragraph))
   thoughts=[Spacer(1,8),HRFlowable(width='100%',thickness=1,color=teal),p('아이리 생각','h2')]
   thoughts.extend(p(paragraph) for paragraph in card['opinion'] or ['이 기사만으로 추가 판단을 확정할 근거가 부족해.'])
   story.append(KeepTogether(thoughts))
   if card['caveat']:
    story.append(p('이 판단의 한계','h3'))
    for paragraph in card['caveat']:story.append(p(paragraph))
   if card['watch']:
    story.append(p('다음에 확인할 것','h3'))
    for paragraph in card['watch']:story.append(p(paragraph))
 else:
  for kind,line in body:story.append(p(line,kind))
 if report.get('delivery_style')!='article_commentary':story.append(PageBreak())
 story.extend([p('부록 | 근거·방법론·출처','h1'),p('분석 절차','h2'),p('공개 기사 원문 수집 → 인용 근거 추출 → 사실 검토 → 사건 분류 → 인과 경로 분석 → 출처별 근거 검토 → 최종 발행. 자료 속 지시문은 실행하지 않습니다. 해석은 관측 사실과 분리하며, 일정·가격·수치는 출처로 확인한 범위만 사용합니다.')])
 story.append(p('자료 범위와 해석상의 한계','h2'))
 story.append(p(f"발견 {cov.get('discovered',0)}건, 본문 조회 시도 {cov.get('attempted',0)}건, 검토 {len(report['sources'])}건. 편집 검토에서 제외된 분석 단위 {len(report.get('qc',{}).get('rejected',[]))}건. 모델: {report.get('model','local')}.",'meta'))
 story.append(p('발행일은 사건 발생일과 다를 수 있습니다. 단일 출처 보도는 독립 확인 사실로 승격하지 않습니다. 과거 문서는 당시의 분석 맥락이며 현재 시세의 증거가 아닙니다. 근거가 없는 숫자 그래프는 만들지 않습니다. 본문은 검증된 자료 범위에 따라 길이가 달라집니다.','meta'))
 for warning in report.get('limitations',[])[:12]:story.append(p(localize(warning),'meta'))
 story.append(p('출처 목록','h2'))
 story += apa.flowables(font)
 def page(canvas,doc):
  canvas.saveState();canvas.setStrokeColor(light);canvas.line(46, A4[1]-35,A4[0]-46,A4[1]-35);canvas.setFont(font,7);canvas.setFillColor(grey)
  canvas.drawString(46,A4[1]-26,'AIRI RESEARCH  /  '+str(number).zfill(3));canvas.drawRightString(A4[0]-46,A4[1]-26,asof+'  PT')
  canvas.line(46,35,A4[0]-46,35);canvas.drawString(46,23,'근거 기반 분석 · 사실 / 해석 / 불확실성 구분');canvas.drawRightString(A4[0]-46,23,str(doc.page));canvas.restoreState()
 doc.build(story,onFirstPage=page,onLaterPages=page)
 return {'title':title,'chunks':narration(report,text)}
