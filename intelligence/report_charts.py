"""Vector charts from stored observations only, with matching numeric tables."""
import datetime as dt,math,json,re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/"vendor"))
from reportlab.graphics.shapes import Drawing,Line,String,Circle,PolyLine
from reportlab.lib import colors
from reportlab.platypus import Paragraph,Table,TableStyle,PageBreak,KeepTogether
from reportlab.lib.styles import ParagraphStyle

def points(history):
 rows=[];seen=set()
 for x in history:
  try:d=dt.date.fromisoformat(str(x['date'])[:10]);v=float(x['value'])
  except (ValueError,TypeError,KeyError):continue
  if not math.isfinite(v) or d in seen:continue
  seen.add(d);rows.append((d,v))
 return sorted(rows)[-60:]

def plot(rows,width,font):
 d=Drawing(width,180);left=72;right=width-12;bottom=28;top=156;values=[v for _,v in rows];lo=min(values);hi=max(values);pad=(hi-lo)*.1 or max(abs(hi)*.01,.01);lo-=pad;hi+=pad
 x=lambda date:left+(date-rows[0][0]).days/max(1,(rows[-1][0]-rows[0][0]).days)*(right-left)
 y=lambda v:bottom+(v-lo)/(hi-lo)*(top-bottom)
 for i in range(5):
  v=lo+(hi-lo)*i/4;yy=y(v);d.add(Line(left,yy,right,yy,strokeColor=colors.HexColor('#d8e1e6'),strokeWidth=.4));d.add(String(left-6,yy-3,f'{v:,.4f}',fontName=font,fontSize=7,textAnchor='end'))
 d.add(Line(left,bottom,left,top,strokeColor=colors.black,strokeWidth=.5));d.add(Line(left,bottom,right,bottom,strokeColor=colors.black,strokeWidth=.5))
 coords=[p for date,v in rows for p in (x(date),y(v))];d.add(PolyLine(coords,strokeColor=colors.HexColor('#087885'),strokeWidth=1.2))
 for date,v in rows:d.add(Circle(x(date),y(v),1.5,fillColor=colors.HexColor('#087885'),strokeWidth=0))
 for index,anchor in [(0,'start'),(len(rows)//2,'middle'),(len(rows)-1,'end')]:d.add(String(x(rows[index][0]),10,rows[index][0].isoformat(),fontName=font,fontSize=7,textAnchor=anchor))
 return d

def sections(series,width,font,citation):
 style=ParagraphStyle('ChartText',fontName=font,fontSize=9,leading=14,spaceAfter=5,wordWrap='CJK');small=ParagraphStyle('ChartSmall',parent=style,fontSize=8,leading=12);result=[]
 import html
 p=lambda s:Paragraph(html.escape(str(s)),style)
 for i,s in enumerate(series,1):
  rows=points(s.get('history',[]))
  if len(rows)<2:continue
  result += [PageBreak(),p('Figure A'+str(i)),p(s['name']+' · '+s['unit']),plot(rows,width,font)]
  result.append(p('Note. 실제 저장 관측값 '+str(len(rows))+'개. '+rows[0][0].isoformat()+'–'+rows[-1][0].isoformat()+'. Y축은 표시 범위에 맞춰 조정했으며 0에서 시작하지 않을 수 있음. 날짜는 관측 시장의 날짜. 누락값은 보간하지 않음. 품질: '+s.get('quality','미확인')+'. '+citation(s)))
  result += [p('Table A'+str(i)),p(s['name']+' · 그래프의 최근 5개 관측값')]
  cells=[['관측일','값 ('+s['unit']+')']]+[[str(date),format(v,'.10g')] for date,v in rows[-5:]]
  t=Table([[Paragraph(html.escape(x),small) for x in row] for row in cells],colWidths=[width*.4,width*.6],repeatRows=1);t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.7,colors.black),('LINEBELOW',(0,0),(-1,0),.5,colors.black),('LINEBELOW',(0,-1),(-1,-1),.7,colors.black),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));result.append(t)
  result.append(p('Note. 표와 그래프는 동일한 관측 배열을 사용함. 표시 반올림 외 재계산 없음. '+citation(s)))
 return result

def investment_series(report):
 sid=report['snapshot_id']
 if not re.fullmatch('[a-f0-9]{32}',sid):return []
 root=Path(__file__).resolve().parents[1]/'data/news-intelligence/investment-v2/snapshots'
 try:snap=json.loads((root/(sid+'.json')).read_text())
 except (OSError,ValueError):return []
 if snap.get('snapshot_id')!=sid or snap.get('mode')!=report['mode']:return []
 selected=report['market_rows'];priority=['SPDJI:index:^GSPC','UST:rates:us10y','BOC:fx:USD/CAD','CME:commodity:CL=F']
 if len(selected)>1:
  selected=sorted(selected,key=lambda x: priority.index(x['instrument_id']) if x['instrument_id'] in priority else 99)[:4]
 out=[]
 for row in selected:
  original=next((x for x in snap['rows'] if x['instrument_id']==row['instrument_id']),None)
  if not original or original.get('value')!=row['value']:continue
  out.append({'name':row['name'],'unit':row['unit'],'history':original.get('history',[]),'refs':row['evidence_ids'][:1],'quality':row['quality_status']})
 return out

def research_series(market):
 out=[]
 for key in ('tsx','sp500','ca10y','cadusd'):
  a=market.get('assets',{}).get(key,{})
  if a.get('available') and a.get('history'):out.append({'name':a.get('label',key),'unit':a.get('unit',''),'history':a['history'],'refs':[a['source_id']],'quality':'stale' if a.get('stale') else 'observed'})
 return out
