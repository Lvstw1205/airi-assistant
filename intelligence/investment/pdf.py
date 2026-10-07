"""PDF presentation of the same validated object returned to the browser."""
import html,sys,re,datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parents[1]/'vendor'))
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .contract import validate

def speech_chunks(text):
 return [s.strip() for s in re.split(r'(?<=[.!?])\s+',text) if s.strip()]

def render_pdf(path,envelope,number):
 if envelope.get('investment_v2',{}).get('editorial'):
  from .editorial_pdf import render_pdf as editorial_pdf
  return editorial_pdf(path,envelope,number)
 r=envelope['investment_v2'];validate(r);font='AIRI-Investment'
 if font not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register(font)
 navy=colors.HexColor('#153048');teal=colors.HexColor('#087885');grey=colors.HexColor('#576a7c')
 styles={k:ParagraphStyle(k,fontName=font,fontSize=size,leading=leading,textColor=color,spaceAfter=5,wordWrap='CJK',keepWithNext=k in ('title','heading')) for k,size,leading,color in [('title',22,28,navy),('heading',13,18,teal),('body',9,14,navy),('small',7,10,grey),('cell',7.5,11,navy)]}
 def p(text,kind='body'):return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[kind])
 evidence={e['id']:e for e in r['evidence']};labels={id:str(i+1) for i,id in enumerate(evidence)}
 from ..apa7 import References
 from ..report_charts import sections,investment_series
 apa=References({k:{**v,'title':v['description'].removesuffix(' value'),'kind':'dataset' if v['kind']!='announcement' else 'calendar'} for k,v in evidence.items()})
 def cite(c):return ' '+apa.cite(c['evidence_ids'])
 def claims(items):
  result=[]
  for c in items:
   result+=[p(c['text']+cite(c)),p(c['kind']+' · 신뢰도 '+c['confidence'],'small')]
   result+=[p('반론: '+x,'small') for x in c['counter_evidence']]+[p('추가 확인: '+x,'small') for x in c['missing_data']]
  return result
 def table(rows,widths):
  t=Table([[p(v,'cell') for v in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f2f5')),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#cbd9df')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));return t
 local=dt.datetime.fromisoformat(r['generated_at']).astimezone(ZoneInfo(r['display_timezone'])).strftime('%Y-%m-%d %H:%M PT');doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=48,bottomMargin=42,title='AIRI 세계 투자 분석',author='AIRI');w=doc.width
 story=[p('AIRI · 세계 투자 분석','title'),p(f"Report {number} · {r['mode'].upper()} · {local}",'small'),p('Snapshot '+r['snapshot_id']+' · Data quality '+r['data_quality'],'small'),p('관측과 해석을 나눠 보는 시장','heading')]
 if r['mode']=='fixture':story.append(p('FIXTURE · 합성 예제이며 실제 시장 데이터가 아니야.','heading'))
 story+=claims(r['summary']) or [p('현재 판단을 뒷받침할 자료가 부족해.')]
 story.append(p('각 자산은 마지막 완료 관측을 사용해. 일별 자료의 날짜 경계 시각은 실제 체결 시각이 아니야. 기간·시장·통화가 다르면 직접 비교하지 않아.','small'))
 for asset,title in [('index','세계 대표 지수'),('equity','선택 기업'),('fx','환율 · 방향 확인'),('rates','금리 · bp 변화'),('commodity','원자재 · 선물'),('crypto','암호자산 · UTC 일별 관측')]:
  rows=[x for x in r['market_rows'] if x['asset_class']==asset]
  if not rows:continue
  story.append(p(title,'heading'));tr=[['자산 / 단위','값 / 변화','관측일 / 품질']]
  for x in rows:tr.append([x['name']+'\n'+x['unit'],('자료 없음' if x['value'] is None else f"{x['value']:,.4f}")+'\n'+('자료 부족' if x['change'] is None else f"{x['change']:+.2f} {x['change_unit']}"),(dt.datetime.fromisoformat(x['observed_at']).astimezone(ZoneInfo(x['timezone'])).date().isoformat() if x['observed_at'] else '미확인')+'\n'+x['quality_status']+cite(x)])
  story.append(table(tr,[w*.38,w*.27,w*.35]))
 story+=[PageBreak(),p('근거 · 해석 · 가장 강한 반론','title')]+claims(r['analysis'])
 technical=[x for x in r['market_rows'] if x.get('metrics',{}).get('rsi14') is not None]
 if technical:
  story.append(p('가격 지표 · 기업 가치 판단과 구분','heading'));tr=[['자산','RSI','EMA','관측 구간 최대 낙폭']]
  for x in technical:
   q=x['metrics'];tr.append([x['name'],f"{q['rsi14']:.2f}",f"{q['ema20']:.4f}",f"{q['max_drawdown_pct']:.2f}%"])
  story.append(table(tr,[w*.4,w*.15,w*.22,w*.23]));story.append(p(technical[0]['metrics']['method'],'small'))
 story+=[PageBreak(),p('조건부 시나리오와 다음 확인','title')]
 for s in r['scenarios']:
  story.append(p({'bull':'상승 조건','base':'기본 조건','bear':'하락 조건'}[s['case']],'heading'));story.append(p(s['horizon'],'small'));story+= [p('가정: '+x) for x in s['assumptions']]+claims(s['effects'])+[p('판단이 바뀌는 조건: '+x) for x in s['invalidation_conditions']]
 story.append(p('공식 일정','heading'))
 for c in r['watch_items']:story.append(p(c['window']+' · '+c['event']+' · '+(dt.datetime.fromisoformat(c['scheduled_at']).astimezone(ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))).strftime('%Y-%m-%d %H:%M PT') if c.get('scheduled_at') else c.get('date','날짜 미확인')+' · 시간 미확인')+cite(c),'small'))
 if not r['watch_items']:story.append(p('확인된 일정 없음. 날짜를 추측하지 않았어.'))
 story+=[PageBreak(),p('데이터 제한과 원자료','title')]+[p(x,'small') for x in r['limitations']]
 story += sections(investment_series(r),w,font,lambda row:apa.cite(row['refs']))
 story += apa.flowables(font)
 def footer(c,doc):
  c.saveState();c.setFont(font,7);c.setFillColor(grey);c.drawString(40,A4[1]-26,'AIRI INVESTMENT INTELLIGENCE / '+r['mode'].upper());c.drawRightString(A4[0]-40,22,str(doc.page));c.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 speech=envelope.get('spoken_briefing','');chunks=speech_chunks(speech)
 return {'title':'세계 투자 분석 · '+r['mode'],'chunks':chunks}
