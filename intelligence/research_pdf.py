"""Dashboard-first market / company PDF with traceable facts and typed analysis."""
import datetime as dt,html,math,re,sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether,HRFlowable
from reportlab.graphics.shapes import Drawing,Line,String,PolyLine
from .research_schema import validate,finite
from .research_financials import LABELS,FIELDS
FONT='AIRI-Korean';NAVY=colors.HexColor('#17334A');TEAL=colors.HexColor('#087E8B');GREY=colors.HexColor('#5C6C7B');LIGHT=colors.HexColor('#EDF3F6');PURPLE=colors.HexColor('#7556A0')
NAMES={'facts':'WHAT HAPPENED · 확인된 내용','why_it_matters':'WHY IT MATTERS · 왜 중요한가','transmission':'MARKET TRANSMISSION · 전달 경로','stocks':'RELEVANT STOCKS · 기업 노출','fundamentals':'FUNDAMENTAL CONNECTION · 손익 연결','analysis':'AIRI ANALYSIS · 아이리 생각','beneficiaries':'POTENTIAL BENEFICIARIES · 조건부 수혜','risks':'POTENTIALLY EXPOSED · 위험','base':'BASE CASE','bull':'BULL CASE','bear':'BEAR CASE','invalidation':'WHAT WOULD INVALIDATE THIS VIEW · 반증 조건','watch':'WHAT TO WATCH NEXT · 후속 확인'}
TAG={'FACT':'사실','ANALYSIS':'해석','HYPOTHESIS':'가설','UNCERTAINTY':'미확인'}

def fmt(v,unit=None):
 if not finite(v):return 'Not Available'
 if unit in ('percent','%','bps'):return f'{v:+.2f}' + ('bp' if unit=='bps' else '%')
 if abs(v)>=1e9:return f'{v/1e9:,.2f}B'
 if abs(v)>=1e6:return f'{v/1e6:,.2f}M'
 return f'{v:,.2f}'

def chart(points,label,width=495,height=94,unit=''):
 d=Drawing(width,height);d.add(String(0,height-10,label,fontName=FONT,fontSize=8,fillColor=NAVY))
 good=[p for p in points if finite(p[1])]
 if len(good)<3:d.add(String(0,height-35,'시계열 3개 미만: 차트 미작성',fontName=FONT,fontSize=8,fillColor=GREY));return d
 values=[p[1] for p in good];lo,hi=min(values),max(values);span=hi-lo or max(abs(hi)*.05,1);left=48;right=width-9;bottom=20;top=height-22
 coords=[]
 for i,(_,v) in enumerate(good):coords += [left+(right-left)*i/(len(good)-1),bottom+(top-bottom)*(v-lo)/span]
 d.add(Line(left,bottom,right,bottom,strokeColor=GREY,strokeWidth=.4));d.add(PolyLine(coords,strokeColor=TEAL,strokeWidth=1.6,fillColor=None))
 d.add(String(0,top-2,fmt(hi),fontName=FONT,fontSize=7,fillColor=GREY));d.add(String(0,bottom,fmt(lo),fontName=FONT,fontSize=7,fillColor=GREY))
 d.add(String(left,4,good[0][0],fontName=FONT,fontSize=7,fillColor=GREY));d.add(String(right,4,good[-1][0],fontName=FONT,fontSize=7,textAnchor='end',fillColor=GREY))
 if unit:d.add(String(right,height-10,unit,fontName=FONT,fontSize=7,textAnchor='end',fillColor=GREY))
 return d

def render_pdf(path,report,number):
 if report.get('research',{}).get('synthesis') and not report['research']['company'].get('enabled'):
  from .research_intelligence_pdf import render_pdf as render_intelligence
  return render_intelligence(path,report,number)
 validate(report);r=report['research'];m=r['market'];f=r['company'];company=f.get('enabled',False)
 if FONT not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register(FONT)
 styles={
 'body':ParagraphStyle('ResearchBody',fontName=FONT,fontSize=9,leading=14.4,textColor=NAVY,spaceAfter=5,wordWrap='CJK'),
 'small':ParagraphStyle('ResearchSmall',fontName=FONT,fontSize=7.2,leading=10.2,textColor=GREY,spaceAfter=4,wordWrap='CJK'),
 'h1':ParagraphStyle('ResearchHeading',fontName=FONT,fontSize=16,leading=22,textColor=NAVY,spaceBefore=12,spaceAfter=8,keepWithNext=True,wordWrap='CJK'),
 'h2':ParagraphStyle('ResearchSection',fontName=FONT,fontSize=10.4,leading=15,textColor=TEAL,spaceBefore=9,spaceAfter=5,keepWithNext=True,wordWrap='CJK'),
 'title':ParagraphStyle('ResearchTitle',fontName=FONT,fontSize=21,leading=27,textColor=NAVY,spaceAfter=8,wordWrap='CJK')}
 def p(text,style='body'):return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[style])
 sources={s['id']:s for s in r['sources']};used=set(r['included_source_ids'])|({s['id'] for s in m['sources']} if not company else set())|{s['id'] for s in f.get('sources',[])}
 for event in r['events']:
  for field in ['facts']+list(NAMES)[1:]:
   for u in event.get(field,[]):used.update(s for eid in u['evidence_ids'] for s in r['evidence'][eid]['source_ids'])
 from .apa7 import References
 from .report_charts import sections,research_series
 apa=References({sid:src for sid,src in sources.items() if sid in used})
 labels={sid:apa.cite([sid]) for sid in sources if sid in used}
 citations=lambda refs:apa.cite([sid for eid in refs for sid in r['evidence'][eid]['source_ids']])
 def up(u):
  prefix=TAG[u['tag']]+(' · 단일 출처 보고' if u['tag']=='FACT' and not u.get('confirmed') else '')
  return p(prefix+' | '+u['text']+' '+citations(u['evidence_ids']))
 def table(rows,widths,header=True):
  t=Table([[p(c,'small') for c in row] for row in rows],colWidths=widths,repeatRows=1 if header else 0,hAlign='LEFT')
  t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('BACKGROUND',(0,0),(-1,0),LIGHT),('LINEBELOW',(0,0),(-1,0),.6,TEAL),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DFE7EB'))]));return t
 generated=dt.datetime.now(dt.timezone.utc).isoformat();report['pdf_generated_at']=generated
 local=lambda s:dt.datetime.fromisoformat(s).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M PT')
 title=('COMPANY EXECUTIVE DASHBOARD' if company else 'AIRI MARKET DASHBOARD');doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=48,bottomMargin=44,title=title,author='AIRI Research')
 width=doc.width;story=[p('AIRI RESEARCH  /  '+str(number).zfill(3)+'  /  '+r['schema'],'small'),p(title,'title'),p((f.get('name') or f.get('requested_company') or r['universe']+' equity research')+' · '+local(report['created']),'small'),HRFlowable(width='100%',thickness=1.6,color=TEAL),Spacer(1,8)]
 if company and f.get('available'):
  records=f['records']+f['derived'];cards=[]
  for key in f['kpi_metrics'][:8]:
   rows=sorted([v for v in records if v['metric']==key],key=lambda v:(v['period_end'],v['frequency']=='quarterly'),reverse=True);v=rows[0] if rows else None
   cards.append(LABELS.get(key,key)+'\n'+(fmt(v['value'],v.get('unit'))+' '+('' if v.get('unit') in ('percent','%','bps') else v.get('unit') or v['currency'])+'\n'+v['period_end']+' '+v['frequency']+' '+citations([v['id']]) if v else 'Not Available'))
  story.append(table([cards[i:i+4] for i in range(0,len(cards),4)],[width/4]*4,False));story.append(p('Historical Actual · 재무 통화 '+f['currency']+' · 업종별 KPI: '+f['template']+' · 컨센서스/가이던스는 실제 확보된 경우만 비교','small'))
  annual=[v for v in records if v['metric']=='revenue' and v['frequency']=='annual'];story.append(chart([(v['period_end'],v['value']) for v in sorted(annual,key=lambda v:v['period_end'])],'매출 장기 추이 · Historical Actual',width,100,f['currency']))
 else:
  rows=[['Market / observation','Current','Daily','5D','20D / 1M']]
  for key in ('tsx','sp500','nasdaq','cadusd','wti','gold','ca10y','us10y'):
   a=m['assets'].get(key,{})
   if a.get('available'):
    rows.append([a['label']+' · '+a['observed_at']+' '+apa.cite([a['source_id']])+(' · stale' if a['stale'] else '')+(' · intraday' if a['partial_session'] else ''),fmt(a['current'])+' '+a['unit'],fmt(a['daily_change'],a['change_unit']),fmt(a['change_5d'],a['change_unit']),fmt(a['change_20d'],a['change_unit'])])
   else:rows.append([a.get('label',key),'Not Available','-','-','-'])
  story.append(table(rows,[width*.32,width*.23,width*.15,width*.15,width*.15]));story.append(p('Daily/5D/20D는 거래 관측치 기준 변화. 수익률은 %, 국채 금리는 bp. FX는 USD per CAD. 선물은 현물이 아니며 롤오버 영향 가능. 각 행의 관측일은 서로 다를 수 있다.','small'))
  tsx=m['assets'].get('tsx',{});story.append(chart([(v['date'],v['value']) for v in tsx.get('history',[])[-21:]],'TSX 최근 21개 관측치',width,78,'index points'))
 story.append(p(('' if company else 'Market Character: '+m['market_character']+'  |  ')+'Research Signal: '+r['executive']['research_signal']+'  |  Confidence: '+r['executive']['confidence'],'small'))
 if not company:
  top=m['sector_proxies']['top'];weak=m['sector_proxies']['weakest']
  story.append(p('Sector ETF proxies · top: '+(m['assets'][top]['label'] if top else 'N/A')+' / weakest: '+(m['assets'][weak]['label'] if weak else 'N/A')+' · 공식 업종 수익률·기여도 아님','small'))
 story.append(p('TOP 3 THINGS TO KNOW','h2'))
 findings=r['executive']['top3'][:3]
 if company and f.get('available') and not findings:findings=(f['quality_flags']+f['connections'])[:3]
 for i in range(3):
  if i<len(findings):story.append(p(str(i+1)+'. '+findings[i]['text']+' '+citations(findings[i]['evidence_ids'])))
  else:story.append(p(str(i+1)+'. '+(['시장 폭·기여 종목·정확한 원인 자료가 부족해 시장 심리 분류를 보류한다.','정량적 전망·목표주가·시나리오 확률은 임의 생성하지 않았다.','다음 확인 대상은 본문에 근거와 미확보 항목을 함께 표시했다.'][i]),'small'))
 driver=r['executive']['major_driver'];risk=r['executive']['key_risk'];watch=r['executive']['next_catalyst']
 story.append(p(('Key Business Driver: ' if company else 'Key Market Driver: ')+(driver['text'] if driver else '확인된 인과관계 없음')+'\nMain Risk: '+(risk['text'] if risk else '업종 핵심 지표와 1차 공시 검증의 공백' if company else '시장 폭·지수 기여도 자료의 공백')+'\nNext Catalyst: '+(watch['text'] if watch else '확인된 일정 없음'),'small'))
 if not company:
  # Market diagnostic is separate from headline-driven event analysis.
  story.extend([PageBreak(),p('MARKET MOVE DIAGNOSTICS','h1'),p('1. Observation · 관측값과 데이터 공백','h2')])
  rows=[['Asset','Previous','YTD','Volume','20D mean | volatility']]
  for key,a in m['assets'].items():
   if not a.get('available') or key.startswith('sector_'):continue
   rows.append([a['label']+' '+apa.cite([a['source_id']]),fmt(a['previous']),fmt(a['ytd_change'],a['change_unit']),fmt(a.get('volume')),fmt(a.get('average_absolute_move_20d'),a['change_unit'])+' | '+fmt(a.get('realized_daily_volatility_20d'),a['change_unit'])])
  story.append(table(rows,[width*.27,width*.16,width*.14,width*.16,width*.27]));story.append(p('2. Significance test · 유의성 점검','h2'));sig=m['significance'];story.append(p(sig['classification']));story.append(p(sig['method'],'small'));story.append(p('Missing: '+', '.join(sig['missing'] or ['none']),'small'))
  story.append(p('3. Sector attribution · 업종과 기여도','h2'));rows=[['Canadian sector ETF proxy','Daily','Observed']]
  for key,a in m['assets'].items():
   if key.startswith('sector_') and a.get('available'):rows.append([a['label']+' ('+a['symbol']+') '+apa.cite([a['source_id']]),fmt(a['daily_change'],'%'),a['observed_at']])
  story.append(table(rows,[width*.62,width*.18,width*.2]));top=m['sector_proxies']['top'];weak=m['sector_proxies']['weakest'];story.append(p('Proxy top: '+(m['assets'][top]['label'] if top else 'Not Available')+' / weakest: '+(m['assets'][weak]['label'] if weak else 'Not Available'),'small'));story.append(p('ETF 가격 변화를 공식 TSX 업종 성과나 지수 기여도로 치환하지 않는다. 상승·하락 종목 수와 구성 종목 가중치가 없어 기여도는 미확보다.','small'))
  story.append(p('4. Cross-asset check / 5. Macro connection','h2'));story.append(p('TSX·CAD·원유·금·캐나다/미국 금리·미국 주가지수의 관측일을 대조한다. 동행만으로 원인을 확정하지 않는다. 거시 발표는 사건별 발생 시점과 근거를 확인한 경우에만 아래에 연결한다.'))
  for k,v in m['missing'].items():story.append(p(k+': '+v,'small'))
 for e in r['events']:
  story.extend([PageBreak(),p('EVENT · '+e['title'],'h1'),p('Impact '+e['impact']+' | Relevance '+e['relevance']+' | '+e['category']+' | Confidence '+e['confidence']+' | Signal '+e['signal'],'small'),p('Event occurrence: '+(e['event_time'] or 'Unverified')+' · '+str(e['event_time_basis']),'small')])
  for sid in e['source_ids']:
   src=sources[sid];story.append(p('['+labels[sid]+'] '+src['name']+' · Article publication '+str(src.get('published_at') or 'unknown')+' · Collection '+src['collected_at'],'small'));story.append(Paragraph('<link href="'+html.escape(src['url'],quote=True)+'" color="#087E8B">원문 링크</link>',styles['small']))
  if e['excerpt']:story.extend([p('SHORT SOURCE QUOTE','h2'),p('“'+e['excerpt']['text']+'” '+apa.cite([e['excerpt']['source_id']]),'small')])
  for field,label in NAMES.items():
   if not e[field]:continue
   story.append(p(label,'h2'))
   for u in e[field]:
    prefix=(u.get('stage','')+' → ') if field=='transmission' else (u['ticker']+' · Exposure '+u['exposure']+' | ') if field=='stocks' else (u.get('metric','')+' · '+u.get('direction','uncertain')+' | ') if field=='fundamentals' else ''
    text=prefix+u['text']+(' · Date '+(u.get('date') or 'Not Available') if field=='watch' else '')
    story.append(up({**u,'text':text}))
  if e['missing']:story.append(p('INSUFFICIENT EVIDENCE · 구체적으로 없는 정보','h2'));story.extend(p(x,'small') for x in e['missing'])
 if company:
  story.extend([PageBreak(),p('THREE-WAY FINANCIAL STATEMENTS','h1')])
  if not f.get('available'):story.append(p(f.get('reason','Statements unavailable')))
  else:
   for group,title in [('income','INCOME STATEMENT'),('balance','BALANCE SHEET'),('cashflow','CASH FLOW STATEMENT')]:
    story.append(p(title,'h2'));periods=sorted({x['period_end'] for x in f['records'] if x['statement']==group and x['frequency']=='quarterly'},reverse=True)[:4]
    frequency='quarterly'
    if not periods:frequency='annual';periods=sorted({x['period_end'] for x in f['records'] if x['statement']==group},reverse=True)[:4]
    rows=[['Metric · '+f['currency']]+periods];keys=list(FIELDS[group])
    if group=='balance':keys+=['net_debt','working_capital']
    if group=='cashflow':keys+=['fcf']
    missing_metrics=[]
    for metric in keys:
     values=[next((x for x in f['records']+f['derived'] if x['metric']==metric and x['period_end']==period and x['frequency']==frequency),None) for period in periods]
     if not any(values):missing_metrics.append(LABELS.get(metric,metric));continue
     rows.append([LABELS.get(metric,metric)]+[fmt(x['value']) if x else 'N/A' for x in values])
    if periods:story.append(table(rows,[width*.34]+[width*.66/len(periods)]*len(periods)))
    if missing_metrics:story.append(p('Not Available: '+', '.join(missing_metrics),'small'))
    story.append(p('Historical Actual · '+frequency+' · '+f['currency']+' · B=billion, M=million · 期末日は発表日ではない。'.replace('期末日は発表日ではない。','기간 말일과 공시일은 다르다.')+' '+citations([x['id'] for x in f['records'] if x['statement']==group][:1]),'small'))
   story.append(p('3-WAY CONNECTION / EARNINGS QUALITY','h2'))
   seen=set()
   for u in f['connections']+f['quality_flags']:
    if u['text'] not in seen:story.append(up({**u,'text':str(u.get('period_end',''))+' '+str(u.get('frequency',''))+' | '+u['text']}));seen.add(u['text'])
   story.append(p('Historical Actual / Company Guidance / Analyst Consensus / AIRI Scenario는 서로 다른 데이터 유형이다. 확인되지 않은 guidance와 consensus는 N/A다.','small'))
   story.extend([PageBreak(),p('FINANCIAL TRENDS · HISTORICAL ACTUAL','h1')])
   plots=[]
   for metric in (('revenue','net_income','eps','roe') if f['template']=='bank' else ('revenue','operating_margin','eps','ocf','fcf','net_debt')):
    vals=sorted([v for v in f['records']+f['derived'] if v['metric']==metric and v['frequency']=='annual'],key=lambda v:v['period_end'])
    plots.append(chart([(v['period_end'],v['value']) for v in vals],LABELS[metric],width/2-10,112,'%' if metric in ('operating_margin','roe') else f['currency']))
   story.append(Table([plots[i:i+2] for i in range(0,len(plots),2)],colWidths=[width/2]*2));story.append(p('각 그래프는 독립된 단위·축을 사용한다. 연간 데이터가 3개 미만이면 추세 차트를 만들지 않는다. 분기 하나를 장기 추세로 해석하지 않는다.','small'))
   story.append(p('ACTUAL VS EXPECTATION / PREVIOUS PERIOD','h2'));rows=[['Metric / basis / period','Actual','Comparator','Difference']]
   comps=sorted(f['comparisons'],key=lambda v:(v['basis']=='Analyst Consensus',v['period_end']),reverse=True)
   for c in comps[:14]:rows.append([LABELS.get(c['metric'],c['metric'])+' / '+c['basis']+' / '+c['period_end'],fmt(c['actual']),fmt(c['comparison']),fmt(c['difference'])])
   story.append(table(rows,[width*.48,width*.17,width*.17,width*.18]));story.append(p(f['consensus_status']+' · '+f['guidance_status'],'small'))
   story.append(p('PRIOR AIRI THESIS','h2'));prior=f.get('previous_thesis');story.append(p((prior['created']+' | '+' / '.join(prior['findings'])) if prior else 'Not Available — 같은 기업의 이전 검증 보고서가 없다.','small'))
   story.append(p('BASE / BULL / BEAR FINANCIAL SENSITIVITY','h2'));forecast=f['forecast']
   if not forecast['enabled']:story.append(p('Not Available — '+forecast['reason']))
   else:
    story.append(p('ILLUSTRATIVE SCENARIO · 실제 실적·회사 가이던스 아님','h2'));story.extend(p(a,'small') for a in forecast['assumptions']);rows=[['Metric']+[c['name'] for c in forecast['cases']]]
    for metric in ('revenue','margin','operating_income','net_income','eps','ocf','capex','fcf','net_debt'):rows.append([metric]+[fmt(c[metric]) for c in forecast['cases']])
    story.append(table(rows,[width*.4]+[width*.2]*3))
   company_research=f.get('research',{})
   for field in ('analysis','base','bull','bear','invalidation','watch'):
    if company_research.get(field):
     story.append(p(NAMES[field],'h2'));story.extend(up(u) for u in company_research[field])
   story.append(p('FINANCIAL RISK / LIMITATIONS','h2'));story.extend(p(x,'small') for x in f['issues']);story.append(p('Missing industry KPIs: '+', '.join(f['missing_kpis']),'small'));story.append(p('Primary verification: '+str(f.get('primary_confirmation',{}).get('status'))+' · '+str(f.get('primary_confirmation',{}).get('reason','')),'small'))
 story.extend([p('AUDIT / SOURCES / LIMITATIONS','h1')]);stats=r['article_counts'];story.append(table([['Discovery','Fetched','Reviewed','Included','Excluded','Failed','Article sources'],[str(stats[k]) for k in ('discovered_articles','fetched_articles','reviewed_articles','included_articles','excluded_articles','failed_articles','source_count')]],[width/7]*7));story.append(p('Reviewed = Included + Excluded. 기사 수와 데이터셋 수는 구분한다. 같은 사건의 여러 독립 출처는 한 이벤트로 묶는다. 모든 제외 이유는 보고서 JSON의 article_ledger에 보관한다.','small'));story.append(p('Validation: PASS · citation references, source counts, exclusion reasons, typed claims. PDF generated '+local(generated),'small'))
 story.append(p('FACT / ANALYSIS / HYPOTHESIS / UNCERTAINTY를 내부 저장한다. 색상 없이도 유형·단위를 읽을 수 있다. 가격 변동 색상은 투자 성과의 개선·악화 판정을 뜻하지 않는다. 원인은 확인할 수 있을 때만 연결한다.','small'))
 story += sections(research_series(m),width,FONT,lambda row:apa.cite(row['refs']))
 story += apa.flowables(FONT)
 def page(c,doc):
  c.saveState();c.setFont(FONT,7);c.setFillColor(GREY);c.drawString(44,A4[1]-28,'AIRI FINANCIAL RESEARCH / '+str(number).zfill(3));c.drawRightString(A4[0]-44,A4[1]-28,local(report['created']));c.setStrokeColor(LIGHT);c.line(44,33,A4[0]-44,33);c.drawString(44,21,'근거 / 계산 / 해석 / 미확인 분리');c.drawRightString(A4[0]-44,21,str(doc.page));c.restoreState()
 doc.build(story,onFirstPage=page,onLaterPages=page)
 from .report_pdf import narration
 return {'title':(f.get('name','기업')+' · 재무 분석' if company else r['universe']+' · 시장 리서치'),'chunks':narration(report,'')}
