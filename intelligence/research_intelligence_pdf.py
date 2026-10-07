"""Presentation only: renders the validated precomputed synthesis object."""
import datetime as dt,html,sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Spacer,KeepTogether
from .research_schema import validate,finite
from .research_pdf import fmt,FONT,NAVY,TEAL,GREY,LIGHT
from .research_synthesis import SNAPSHOT

def render_pdf(path,report,number):
 validate(report);r=report['research'];s=r['synthesis'];m=r['market'];pool=r['evidence'];used=set()
 def collect_refs(value):
  if isinstance(value,dict):
   for fid in value.get('evidence_ids',[]):used.update(pool[fid]['source_ids'])
   for child in value.values():collect_refs(child)
  elif isinstance(value,list):
   for child in value:collect_refs(child)
 collect_refs(s);collect_refs(r['events'])
 used.update(m['assets'][k]['source_id'] for k in SNAPSHOT if m['assets'].get(k,{}).get('source_id'))
 sources={x['id']:x for x in r['sources'] if x['id'] in used};labels={sid:src['name'] for sid,src in sources.items()}
 from .apa7 import References
 from .report_charts import sections,research_series
 apa=References(sources)
 if FONT not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register(FONT)
 styles={name:ParagraphStyle(name,fontName=FONT,fontSize=size,leading=lead,textColor=color,spaceAfter=after,wordWrap='CJK',keepWithNext=name in ('h1','h2')) for name,size,lead,color,after in [('title',19,23,NAVY,7),('h1',15,20,NAVY,10),('h2',9.8,13,TEAL,5),('body',8.5,12,NAVY,5),('small',7,9.3,GREY,3),('cell',7.1,9.4,NAVY,0)]}
 def p(text,style='body'):return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[style])
 def cite(evidence):return apa.cite([sid for f in evidence for sid in pool[f]['source_ids']])
 def text(u):return u['text']+' '+cite(u.get('evidence_ids',[]))
 def table(rows,widths,compact=False):
  t=Table([[p(c,'cell') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),LIGHT),('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DCE5EA')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),3 if compact else 5),('BOTTOMPADDING',(0,0),(-1,-1),3 if compact else 5)]));return t
 def section(title):story.append(p(title,'h2'))
 def page(title):story.extend([PageBreak(),p(title,'h1')])
 local=lambda date:dt.datetime.fromisoformat(date).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M PT')
 generated=dt.datetime.now(dt.timezone.utc).isoformat();report['pdf_generated_at']=generated
 doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=44,bottomMargin=40,title='AIRI Market Intelligence',author='AIRI Research');w=doc.width
 story=[p('AIRI MARKET INTELLIGENCE','title'),p('Research '+str(number).zfill(3)+' · '+local(report['created'])+' · '+r['schema']+' · '+s['version'],'small')]
 section('MARKET SNAPSHOT · 관측일은 보고서 시각과 다를 수 있음')
 rows=[['Asset / source','Observation','Current','Daily','5D','20D']]
 for k in SNAPSHOT:
  a=m['assets'].get(k,{})
  rows.append([a.get('label',k)+(' '+apa.cite([a['source_id']]) if a.get('source_id') in labels else ''),str(a.get('observed_at') or 'N/A')+(' partial' if a.get('partial_session') else ''),((f"{a['current']:.4f}" if k=='cadusd' else fmt(a.get('current')))+' '+('bp' if a.get('kind')=='spread' else '%' if a.get('kind')=='yield' else '')) if a.get('available') else 'N/A',fmt(a.get('daily_change'),a.get('change_unit','%')),fmt(a.get('change_5d'),a.get('change_unit','%')),fmt(a.get('change_20d'),a.get('change_unit','%'))])
 story.append(table(rows,[w*.27,w*.19,w*.18,w*.12,w*.12,w*.12],True));story.append(p('CAD = USD per CAD · WTI/Gold = futures, not spot · yield changes = bp · price changes = %. Futures contract/roll status is unverified.','small'))
 section('DAILY MOVE / BROADER REGIME')
 regimes=s['market_regime'];story.append(table([['Daily Move','Equity','Volatility'],[s['daily_move']['classification'],regimes['equity']['classification'],regimes['volatility']['classification']],['Rates','CAD','Commodity'],[regimes['rates']['classification'],regimes['cad']['classification'],regimes['commodity']['classification']]],[w/3]*3,True))
 section('WHAT ACTUALLY MATTERS TODAY')
 for i,c in enumerate(s['top_developments']):story.append(p(f"{i+1}. {c['title']} · {c['status']} · {c['confidence']['level']}\n"+c.get('evidence_summary',c['text'])+'\n'+c['why_it_matters']+' '+cite(c['evidence_ids']),'small'))
 if not s['top_developments']:story.append(p('중요도를 검증한 항목이 없다. 임의로 세 가지를 채우지 않았다.','small'))
 section('CROSS-ASSET READ')
 for u in s['overall_read'][:3]:story.append(p(text(u),'small'))
 story.append(p('PRIMARY RISK · '+text(s['primary_risk']),'small'))
 cat=s['next_catalysts'][0] if s['next_catalysts'] else None
 story.append(p('NEXT CATALYST · '+(cat['date']+' '+(cat.get('time') or 'Time Not Verified')+' '+cat['event']+' '+cite(cat['evidence_ids']) if cat else 'Date Not Verified'),'small'))
 story.append(p('CONFIDENCE · '+s['confidence']['level']+' · '+s['confidence']['reason'],'small'))
 page('MARKET MOVE DIAGNOSTICS')
 basis={}
 for b in s.get('analysis_basis',[]):basis.setdefault((b['live_observation'],b['analysis_observation']),[]).append(b['key'])
 for (live,completed),keys in basis.items():story.append(p('Live '+live+' / broader comparisons use completed '+str(completed)+': '+', '.join(keys),'small'))
 section(s['daily_move']['method']+' · '+s['daily_move']['classification'])
 story.append(table([['Input','Observed']]+[[k.replace('_',' '),fmt(v,'%' if k!='volume_ratio' else '')] for k,v in s['daily_move']['inputs'].items()],[w*.6,w*.4]));story.append(p(s['daily_move']['rules'],'small'));story.append(p('Missing: '+', '.join(s['daily_move']['missing'] or ['none']),'small'))
 if s['daily_move'].get('reason'):story.append(p(s['daily_move']['reason'],'small'))
 section('REGIME RATIONALE · 당일 등락과 별개의 관측 기간')
 for name,value in regimes.items():story.append(p(name.upper()+' · '+value['classification']+' · '+value['confidence']['level'],'h2'));story.append(p(value['reason']+' '+cite(value['evidence_ids'])));story.append(p(str(value['confidence']['dimensions']['Timing Match']),'small'))
 section('WHAT WOULD CHANGE OUR VIEW?')
 for c in s['top_developments']:story.append(p(c['title']+' · '+c['invalidation']+' '+cite(c['evidence_ids'])))
 page('CROSS-ASSET ANALYSIS')
 story.append(p('CONSISTENT WITH / CONTRADICTED는 명시된 경제 경로와 관측 방향의 비교다. 인과 확인·통계적 상관 추정·투자 수익 예측이 아니다. 공통 관측일로 기간을 맞춘다.','small'))
 rows=[['Relationship / status','Matched changes (left / right)','Mechanism / counter-check']]
 for c in s['cross_asset_read']:
  changes=[]
  for n,data in c['windows'].items():
   if data['available']:
    units=['bp' if s['analysis_assets'][k].get('kind') in ('yield','spread') else '%' for k in c['assets']]
    changes.append(n+'D '+f"{data['changes'][0]:+.2f}{units[0]} / {data['changes'][1]:+.2f}{units[1]}"+'\n'+data['start']+' → '+data['end'])
   else:changes.append(n+'D unavailable')
  if c['quality_flags']:changes.append(' / '.join(c['quality_flags']))
  rows.append([c['title']+'\n'+c['status']+'\nConfidence '+c['confidence']['level'], '\n'.join(changes)+'\n'+cite(c['evidence_ids']),c['mechanism']+'\n반증/확인: '+c['invalidation']])
 story.append(table(rows,[w*.21,w*.31,w*.48],True))
 section('SUPPORTIVE FACTOR');story.append(p(text(s['primary_opportunity_or_supportive_factor']),'small'))
 page('RATES / FX / YIELD CURVE')
 rows=[['Matched yield spread','Observation','Current','5D Δ','20D Δ','Shape / change']]
 for key,a in s['rates'].items():
  rows.append([a['label']+' '+cite(a.get('evidence_ids',[])),a.get('observed_at','N/A'),fmt(a.get('current'),'bps'),fmt(a.get('change_5d'),'bps'),fmt(a.get('change_20d'),'bps'),(a['curve_shape']+' / '+a['curve_change']) if a.get('available') and 'curve' in key else '—'])
 story.append(table(rows,[w*.3,w*.14,w*.13,w*.13,w*.13,w*.17],True))
 for a in s['rates'].values():
  if a.get('warning'):story.append(p(a['label']+': '+a['warning'],'small'))
 story.append(p('수익률곡선의 형태와 기울기 변화만으로 경기침체를 예측하지 않는다. 금리차와 CAD의 방향 일치는 원인 확인과 다르다.','small'))
 section('CATALYST CALENDAR · 공식 일정에서 확인한 날짜만 표시')
 rows=[['Date / time ET','Event / country','Consensus / previous','Why / exposed assets']]
 for c in s['next_catalysts'][:8]:rows.append([c['date']+'\n'+(c.get('time') or 'Time Not Verified'),c['event']+' · '+c['country']+' '+cite(c['evidence_ids']),'N/A / N/A',c['why_it_matters']+'\n'+', '.join(c['assets'])])
 if len(rows)>1:story.append(table(rows,[w*.18,w*.3,w*.13,w*.39],True))
 else:story.append(p('Date Not Verified — 일정 공급자 연결 또는 파싱 실패.'))
 story.extend(p(x,'small') for x in s['calendar'].get('missing',[]));story.append(p('Calendar items available: '+str(len(s['next_catalysts']))+'; earliest eight shown. Full list retained in JSON.','small'))
 page('SECTOR / BREADTH / CONTRIBUTORS')
 section('SECTOR DISPERSION · ETF PROXY ≠ official sector index ≠ TSX contribution')
 rows=[['Sector / evidence','Daily','5D','20D','20D relative vs TSX']]
 for a in s['sector_dispersion']['rows']:rows.append([a['sector']+'\n'+a['evidence_type']+' '+cite(a['evidence_ids']),fmt(a['daily'],'%'),fmt(a['5d'],'%'),fmt(a['20d'],'%'),fmt(a['relative_vs_tsx'])+' pp'])
 story.append(table(rows,[w*.38,w*.14,w*.14,w*.14,w*.2],True));story.extend(p(text(u),'small') for u in s['sector_dispersion']['analysis'])
 section('MARKET BREADTH')
 b=s['breadth'];story.append(p(b['interpretation']))
 if b['available']:
  story.append(table([['Advancers','Decliners','Unchanged','A/D','Above 50DMA','New highs / lows'],[str(b['advancers']),str(b['decliners']),str(b['unchanged']),fmt(b['ad_ratio']),fmt(b['above_50dma'],'%'),str(b['new_highs'])+' / '+str(b['new_lows'])]],[w/6]*6,True));story.append(p(b['method']+' · '+b['high_low_basis']+' '+cite(b['evidence_ids']),'small'))
 else:story.append(p(b['reason'],'small'))
 section('TOP POSITIVE / NEGATIVE CONTRIBUTORS')
 c=s['contributors']
 if c['available']:
  rows=[['Company / sector','Weight','Return','Approx. contribution']]+[[x['symbol']+' / '+str(x['sector']),fmt(x['weight_pct'],'%'),fmt(x['return_pct'],'%'),fmt(x['contribution_pp'])+' pp '+cite(x['evidence_ids'])] for x in c['positive']+c['negative']]
  story.append(table(rows,[w*.4,w*.18,w*.18,w*.24],True));story.append(p(c['method']+' Coverage weight '+fmt(c['coverage_weight_pct'],'%'),'small'))
 else:story.append(p(c['reason'],'small'))
 for group,title in [('confirmed','CONFIRMED MARKET DEVELOPMENTS'),('developing','DEVELOPING / UNVERIFIED EVENTS')]:
  for e in [e for e in r['events'] if e['id'] in s['event_groups'][group]]:
   page(title);section(e['title']);v=e['verification']
   story.append(p('Verification: '+v['status']+' · Confidence '+e['confidence']+'\nPrimary: '+(', '.join(labels[k] for k in v['primary_source_ids']) or 'Not verified')+' · Independent source count: '+str(v['independent_sources'])+'\nPublication: '+', '.join(str(x) for x in v['publication_times'])+'\nEvent time: '+str(v['event_time'] or 'Not verified'),'small'))
   if v['primary_search_reason']:story.append(p(v['primary_search_reason'],'small'))
   section('WHAT HAPPENED');story.extend(p(text(u)) for u in e['facts'])
   section('WHY IT MATTERS');story.extend(p(text(u)) for u in e['why_it_matters'])
   section('EVENT → FINANCIAL TRANSMISSION')
   story.append(table([['Stage / status','Evidence-grounded link']]+[[u['stage']+'\n'+u['support_status'],text(u)] for u in e['transmission_map']],[w*.3,w*.7],True))
   section('SCENARIOS · conditional, no invented probabilities')
   for c in e['transmission_scenarios']:
    story.append(p(c['name']+' · Trigger: '+text(c['trigger'])));story.extend(p(text(u),'small') for u in c['transmission']);story.append(p('Assets: '+', '.join(c['assets'])+'\nInvalidation: '+' / '.join(text(u) for u in c['invalidation']),'small'))
   if not e['transmission_scenarios']:story.append(p('시나리오의 검증된 전제·전달 경로·반증 조건이 함께 확보되지 않아 수치나 방향을 채워 넣지 않았다.','small'))
   section('WHAT WOULD CHANGE OUR VIEW / WHAT TO WATCH');story.extend(p(text(u),'small') for u in e['invalidation']+e['watch']);story.extend(p(x,'small') for x in e['missing'])
 page('DATA QUALITY / AUDIT / SOURCES')
 counts=r['article_counts'];story.append(table([['Discovered','Fetched','Reviewed','Included','Excluded','Failed','Article sources'],[str(counts[k]) for k in ('discovered_articles','fetched_articles','reviewed_articles','included_articles','excluded_articles','failed_articles','source_count')]],[w/7]*7,True))
 story.append(p('Reviewed = Included + Excluded. Data series and calendar sources are separate from article counts. Exclusion reasons and provider failures remain in JSON. Generation: '+local(generated),'small'))
 story.append(table([['Series','Observation','Flags / instrument']]+[[q['key'],q['observation_date'] or 'N/A',', '.join(q['flags'])+' · '+str(q['instrument'] or '')] for q in s['data_quality']],[w*.24,w*.18,w*.58],True))
 section('CONFIDENCE BREAKDOWN');story.extend(p(k+': '+str(v),'small') for k,v in s['confidence']['dimensions'].items())
 section('PROVIDER / CALENDAR FAILURES');story.extend(p(str(x.get('url') or x.get('series'))+' · '+str(x.get('reason')),'small') for x in m.get('data_ledger',[]) if x.get('status')=='failed')
 section('METHOD / LIMITATIONS');story.extend(p(k+': '+v,'small') for k,v in s['methodology'].items())
 story.append(p('VERIFIED identifies a primary/infrastructure observation; it does not certify causality. SINGLE_SOURCE, PROXY, stale/partial observations and date mismatches constrain downstream confidence. No paid market-data feed or complete official TSX constituent weights were assumed.','small'))
 section('SOURCES · hierarchy version 2')
 story += sections(research_series(m),w,FONT,lambda row:apa.cite(row['refs']))
 story += apa.flowables(FONT)
 def footer(c,doc):
  c.saveState();c.setFont(FONT,7);c.setFillColor(GREY);c.drawString(40,A4[1]-25,'AIRI MARKET INTELLIGENCE / '+str(number).zfill(3));c.drawRightString(A4[0]-40,A4[1]-25,local(report['created']));c.drawString(40,20,'Observation / interpretation / hypothesis / uncertainty');c.drawRightString(A4[0]-40,20,str(doc.page));c.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 from .report_pdf import narration
 return {'title':r['universe']+' · Market Intelligence','chunks':narration(report,'')}
