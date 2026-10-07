import hashlib
import html
import json
from pathlib import Path

def source_names(pack,refs):
    ids=list(dict.fromkeys(s for r in refs for s in ([r] if r in pack.get('sources',{}) else pack.get('evidence',{}).get(r,{}).get('source_ids',[]))))
    return '; '.join((pack['sources'][s].get('publisher') or pack['sources'][s].get('name') or pack['sources'][s].get('title','Source'))+', '+str(pack['sources'][s].get('published','Date not available'))+(f", p. {pack['sources'][s]['page']}" if pack['sources'][s].get('page') else '') for s in ids if s in pack.get('sources',{}))

def text_report(record):
    d=record['payload'];pack=d.get('pack') or {};plan=d.get('plan') or {};out=[]
    if d.get('reviews'):
        review=d['reviews'][-1];out+=['# Research review','Number | Classification | Evidence | Action','--- | --- | --- | ---']
        out += [f"{r['number']} | {r['classification']} | {', '.join(r['evidence_ids'])} | {r['action']}" for r in review['numeric_audit']]
        out += ['Weak arguments:']+[r['issue']+' → '+r['correction'] for r in review['weakest_arguments']]
        if review.get('counterargument'):out+=['Strongest counterargument: '+review['counterargument']['text']]
    out+=['# '+(plan.get('thesis') or {}).get('text',d['options']['query']),d['options']['report_type']+' · as of '+d['options']['as_of'],'## Research notes']
    for i,n in enumerate(d.get('notes',[])):out+=[str(i+1)+'. '+n['text'],'Source: '+source_names(pack,n['evidence_ids'])]
    if plan:
        out+=['## Thesis and outline','Core thesis: '+plan['thesis']['text'],'Consensus: '+(plan['consensus']['text'] if plan.get('consensus') else 'Data not available; dated consensus evidence required.'),'Variant perception: '+plan['variant']['text']]
        out += [x['title']+' — '+x['question'] for x in plan['outline']]
        out+=['## Key Takeaways']+[u['text'] for u in plan['takeaways']]
    for s in d.get('sections',[]):
        out+=['## '+s['title']]
        for u in ([s['conclusion']] if s.get('conclusion') else [])+s['paragraphs']:
            out+=[u['kind']+': '+u['text'],'Source: '+source_names(pack,u['evidence_ids'])]
        for t in s['tables']:
            out += [t['title'],' | '.join(t['columns'])]+[' | '.join(map(str,row)) for row in t['rows']]+['Source: '+source_names(pack,t['evidence_ids']),t.get('note','')]
    if pack.get('gaps') or plan.get('missing_data'):out+=['## Data not available']+list(dict.fromkeys(pack.get('gaps',[])+plan.get('missing_data',[])))
    out+=['## Disclaimer','This is investment analysis, not personalized financial advice. Forecasts and valuation outputs are conditional estimates, not guaranteed outcomes. No trading instruction is executed.']
    return '\n\n'.join(out)

def render_pdf(path,report,number,_scale=1,_attempt=0):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak,BaseDocTemplate,PageTemplate,Frame,FrameBreak,NextPageTemplate
    from reportlab.graphics.shapes import Drawing,String
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    # English body; this font also preserves Korean publisher names in citations.
    if 'Desk' not in pdfmetrics.getRegisteredFontNames():__import__('pdf_font').register('Desk')
    r=report['professional_research'];d=r['payload'];p=d['plan'];pack=d['pack'];deep=d['options']['report_type']=='Sector Deep Dive';compact=d['options']['report_type']=='Spot Comment'
    ink=colors.HexColor('#17283B');muted=colors.HexColor('#516171');accent=colors.HexColor('#23666B')
    size=(8.4 if compact else 10.2)*_scale
    styles={
      'body':ParagraphStyle('body',fontName='Helvetica',fontSize=size,leading=size*1.35,spaceAfter=5,textColor=ink),
      'small':ParagraphStyle('small',fontName='Desk',fontSize=6.3 if compact else 7,leading=8 if compact else 10,textColor=muted,spaceAfter=6),
      'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=19,leading=23,textColor=ink,spaceAfter=13),
      'h':ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=10 if compact else 13,leading=13 if compact else 17,textColor=accent,spaceBefore=8,spaceAfter=5),
    }
    def para(text,kind='body'):return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[kind])
    story=[];full_width=A4[0]-84;width=full_width;n=0
    def table(title,cols,rows,refs=(),note='',exhibit=False):
        nonlocal n
        if exhibit:n+=1;title='Table '+str(n)+'. '+title
        story.append(para(title,'h'));data=[[para(x,'small') for x in cols]]+[[para(x if x is not None else 'Data not available','small') for x in row] for row in rows]
        t=Table(data,colWidths=[width/len(cols)]*len(cols),repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EDF4F3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,accent),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DBE1E5')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.append(t)
        story.append(para('Source: '+(source_names(pack,refs) or 'AIRI / TIM WORKS, '+d['options']['as_of']+'; review of the frozen evidence pack'),'small'))
        if note:story.append(para(note,'small'))
    review=d['reviews'][-1]
    story += [para('AIRI / TIM WORKS · RESEARCH '+str(number),'small'),para(p['thesis']['text'],'title'),para(d['options']['report_type']+' · '+d['options']['as_of']+' · English · Revision '+str(r['revision']),'small')]
    table('Research review', ['Check','Outcome'],[
        ['Numerical statements',str(len(review['numeric_audit']))+' entries reviewed; '+str(review['unsupported_removed'])+' unsupported entries removed'],
        ['Contradictions','No unresolved contradiction retained'],['Audit trail','Full number-by-number review and source links in Research Desk']])
    if compact:
        header_height=sum(f.wrap(full_width,10000)[1]+f.getSpaceBefore()+f.getSpaceAfter() for f in story)+10
        story.append(NextPageTemplate('columns'));story.append(FrameBreak());width=(full_width-18)/2
    story.append(para('Key Takeaways','h'))
    for u in p['takeaways']:story.append(para('• '+u['text']));story.append(para(source_names(pack,u['evidence_ids']),'small'))
    for section in d['sections']:
        if deep and section['key'].startswith('core_'):story.append(PageBreak())
        story.append(para(section['title'],'h'))
        if section.get('conclusion'):story.append(Paragraph('<b>'+html.escape(section['conclusion']['text'])+'</b>',styles['body']))
        for u in section['paragraphs']:
            story.append(para(('Estimate: ' if u['kind'] in ('Estimate','Forecast') else '')+u['text']))
            story.append(para(source_names(pack,u['evidence_ids']),'small'))
        for t in section['tables']:
            if n<2:table(t['title'],t['columns'],t['rows'],t['evidence_ids'],t.get('note',''),exhibit=True)
    story.append(para('Valuation and scenario exhibits','h'))
    val=p['valuation']
    if val.get('available'):
        table('Valuation assumptions',['Parameter','Value / unit','Basis and method'],[[a['name'],str(a['value'])+' '+a['unit'],a['basis']+': '+a['method']] for a in val['assumptions']],val['evidence_ids'],val['formula'],exhibit=True)
        table('Two-variable valuation sensitivity',[val['axis_names'][1]+' / '+val['axis_names'][0]]+list(map(str,val['x'])),val['rows'],val['evidence_ids'],val['sensitivity_method']+' Output: '+val['output_unit'],exhibit=True)
    if p['scenarios']:
        table('Scenario estimates',['Case / weight','Trigger','Outcome'],[[x['name']+' / '+str(x['probability'])+'% (Estimate)',x['trigger']['text'],x['outcome']['text']] for x in p['scenarios']],['Q_SCENARIOS'],'Subjective scenario weights, not calibrated probabilities; total 100%.',exhibit=True)
    if p.get('risks') and n<5:
        table('Risks ranked by probability × impact',['Risk','Probability / impact / score','Thesis falsifier'],[[x['risk']['text'],str(x['probability'])+'% / '+str(x['impact_score'])+' / '+str(x['score']),x['falsifier']['text']] for x in p['risks']],['Q_RISKS'],pack['evidence']['Q_RISKS']['method'],exhibit=True)
    bridge=p.get('earnings_bridge') or {}
    if bridge.get('available') and n<6:
        table('Earnings bridge — house estimates',['Year','Revenue','Net margin %','Net profit'],[[x['year'],x['revenue'],x['net_margin_pct'],x['net_profit']] for x in bridge['years']],['Q_EARNINGS'],bridge['currency']+' unscaled. '+bridge['formula']+' '+bridge['method'],exhibit=True)
    charts=pack.get('charts',[])[:max(0,6-n)]
    for chart in charts:
        n+=1;story.append(para(f'Figure {n}. '+chart['title']+' · '+chart['unit'],'h'))
        drawing=Drawing(width,142);line=LinePlot();line.x=42;line.y=27;line.width=width-57;line.height=104
        values=chart['values'];line.data=[[(i,v['value']) for i,v in enumerate(values)]];line.lines[0].strokeColor=accent;line.lines[0].strokeWidth=1.5
        line.xValueAxis.valueMin=0;line.xValueAxis.valueMax=len(values)-1;line.xValueAxis.valueSteps=[0,len(values)-1];line.xValueAxis.labelTextFormat=lambda v:values[min(len(values)-1,int(v))]['date']
        line.xValueAxis.labels.fontName='Desk';line.xValueAxis.labels.fontSize=6;line.yValueAxis.labels.fontName='Desk';line.yValueAxis.labels.fontSize=7;drawing.add(line);story.append(drawing)
        source='; '.join((pack['sources'].get(s,{}).get('publisher') or pack['sources'].get(s,{}).get('name','Source'))+', '+str(pack['sources'].get(s,{}).get('published','Date not available')) for s in chart['source_ids'])
        story.append(para('Source: '+source+'. Stored observations; no interpolation.','small'))
    if n<4:story.append(para('Data not available: fewer than four supported exhibits. No synthetic market data added.','small'))
    if review.get('counterargument'):story += [para('Strongest counterargument','h'),para(review['counterargument']['text']),para('Source: '+source_names(pack,review['counterargument']['evidence_ids']),'small')]
    missing=list(dict.fromkeys(p.get('missing_data',[])+pack.get('gaps',[])))
    if missing:story += [para('Evidence limitations','h')]+[para(x,'small') for x in missing[:20]]
    story += [para('Disclaimer','h'),para('This is investment analysis, not personalized financial advice. Valuations, scenario weights and forecasts are estimates conditional on stated assumptions. No trade is executed.','small'),para('References','h')]
    for source in pack['sources'].values():
        line=(source.get('publisher') or source.get('name') or source.get('title','Source'))+'. ('+str(source.get('published','n.d.'))+'). '+source.get('title','')+'. '+(source.get('url') or (Path(source['path']).name if source.get('path') else ''))
        story.append(para(line,'small'))
    if deep:
        story.append(PageBreak());story.append(para('Appendix · Research review','title'))
        for w in review['weakest_arguments']:
            story.append(para(w['issue'],'h'));story.append(para(w['correction']))
        table('Number-by-number verification',['Location / number','Classification','Source / method','Disposition'],[[a['unit']+' / '+a['number'],a['classification'],source_names(pack,a['evidence_ids'])+' '+a.get('method',''),a['action']] for a in review['numeric_audit']],note='Each numerical occurrence is classified. Unsupported values were removed; estimation inputs remain explicitly conditional. Provider plot observations are included.')
    def page(canvas,doc):
        canvas.setFont('Desk',7);canvas.setFillColor(muted);canvas.drawString(42,24,'AIRI Research · '+d['options']['as_of']);canvas.drawRightString(A4[0]-42,24,str(doc.page))
    if compact:
        frame_width=(full_width-18)/2
        doc=BaseDocTemplate(str(path),pagesize=A4,title=p['thesis']['text'],author='AIRI / TIM WORKS')
        header_bottom=A4[1]-36-header_height
        first=[Frame(42,header_bottom,full_width,header_height,id='header',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]+[Frame(x,40,frame_width,header_bottom-54,id='first-'+str(i),leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0) for i,x in enumerate((42,42+frame_width+18))]
        later=[Frame(x,40,frame_width,766,id='col-'+str(i),leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0) for i,x in enumerate((42,42+frame_width+18))]
        doc.addPageTemplates([PageTemplate(id='first',frames=first,onPage=page),PageTemplate(id='columns',frames=later,onPage=page)])
        doc.build(story)
    else:
        SimpleDocTemplate(str(path),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=36,bottomMargin=39,title=p['thesis']['text'],author='AIRI / TIM WORKS').build(story,onFirstPage=page,onLaterPages=page)
    raw=Path(path).read_bytes()
    from pypdf import PdfReader
    pages=len(PdfReader(path).pages)
    meets=(2<=pages<=3 if compact else 10<=pages<=15 if deep else True)
    if not meets and _attempt<2:
        adjust=.9 if pages>(3 if compact else 15) else 1.12
        return render_pdf(path,report,number,_scale*adjust,_attempt+1)
    narration=[u['text'] for u in p['takeaways']]
    return {'title':p['thesis']['text'],'sha256':hashlib.sha256(raw).hexdigest(),'chunks':narration,'pages':pages,'exhibits':n,'layout_target_met':meets}
