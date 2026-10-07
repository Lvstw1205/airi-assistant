"""Deterministic publication: no new model facts can enter after editorial review."""
import datetime as dt,re
from zoneinfo import ZoneInfo
from .evidence import numbers,normalized
ZONE=ZoneInfo(__import__('os').environ.get('AIRI_TIMEZONE','UTC'))
def render(report,pool):
 ko=report['language']=='ko';sources={s['id']:s for s in report.get('historical_sources',[])+report['sources']};budget={};quotes={}
 def say(en,kr):return kr if ko else en
 def cite(refs):
  ids=list(dict.fromkeys(s for r in refs if r in pool for s in pool[r]['source_ids']))
  return ' '.join('['+sources[s]['source']+']('+sources[s]['url']+')' for s in ids if s in sources)
 def unit(u,label='ANALYSIS'):
  refs=u['evidence_ids'];text=u['text'];ids={s for r in refs if r in pool for s in pool[r]['source_ids']};words=len(text.split())
  if not ids or not all(s in sources for s in ids):return None
  # Conservative per-source paraphrase and verbatim budgets for a public brief.
  if any(budget.get(s,0)+words>200 for s in ids):return None
  verbatim={}
  for s in ids:
   source=normalized(sources[s].get('body','') or ' '.join(f.get('quote','') for f in pool.values() if s in f.get('source_ids',[])));tokens=text.split();copied=set()
   for i in range(len(tokens)-4):
    if normalized(' '.join(tokens[i:i+5])) in source:copied.update(range(i,i+5))
   verbatim[s]=len(copied)
   if quotes.get(s,0)+len(copied)>25:return None
  for s in ids:budget[s]=budget.get(s,0)+words;quotes[s]=quotes.get(s,0)+verbatim[s]
  if label=='ANALYSIS' and any(not pool[r].get('confirmed') for r in refs):label='SIGNAL / conditional analysis'
  return label+': '+text+' '+cite(refs)
 def lines_for(group,label='ANALYSIS'):
  return [line for u in group if (line:=unit(u,label))]
 now=dt.datetime.fromisoformat(report['created']);start=dt.datetime.fromisoformat(report['window_start'])
 lines=['# AIRI INTELLIGENCE BRIEF',report['profile_label'],f"Date: {now.astimezone(ZONE).isoformat()}",f"Coverage Window: {start.astimezone(ZONE).isoformat()} → {now.astimezone(ZONE).isoformat()}",f"Sources Reviewed: {len(report['sources'])} article bodies · {report['coverage']['discovered']} discovered · {len(report['events'])} canonical events"]
 if report['status']=='limited':lines.append(say('LIMITED EVIDENCE — an executive assessment could not be fully verified.','근거 제한 — 충분히 검증된 종합 분석을 완성하지 못했습니다.'))
 # Reserve the publication budget for the factual development before synthesis.
 fact_lines={}
 for e in report['events']:
  fact_lines[e['id']]=[]
  for fact in e['confirmed_facts'][:2] or e['facts'][:2]:
   value=unit({'text':fact['text'],'evidence_ids':[fact['id']]},'FACT' if fact['confirmed'] else 'UNCERTAINTY — reported, not independently confirmed')
   if value:fact_lines[e['id']].append(value)
 lines+=['\n## EXECUTIVE ASSESSMENT']
 assessment=lines_for(report['synthesis']['executive_assessment'][:5])
 lines+=assessment or [say('Insufficient evidence to make a reliable assessment.','신뢰할 수 있는 종합 판단을 내릴 근거가 부족합니다.')]
 if report['history_count']==0:lines.append(say('No prior briefing timeline yet; a verified day-over-day comparison is unavailable.','첫 수집이므로 전일 사건 기록과의 검증된 비교는 아직 불가능합니다.'))
 lines+=['\n# TOP DEVELOPMENTS']
 if not report['events']:lines.append(say('No new event supported by retrievable article bodies in this window. Headlines were not used as facts.','이 기간에 본문 근거로 확인한 새 사건이 없습니다. 제목만으로 사실이나 분석을 만들지 않았습니다.'))
 for i,e in enumerate(report['events'],1):
  lines+=['\n## '+str(i)+'. '+e['event'],'Classification: '+e['classification'], 'Event time: '+(e['timestamp'] or 'Unverified')+' · basis: '+e['timestamp_basis'],'\n### Development']
  lines+=fact_lines[e['id']]
  analysis=e['analysis']
  for title,key in [('Context','context'),('Why It Matters','why_it_matters'),('What Is Driving It','causal_drivers'),('First-order Implications','first_order_effects'),('Second-order Implications','second_order_effects'),('Potential Beneficiaries','beneficiaries'),('Exposed Parties','exposed_parties')]:
   section=lines_for(analysis[key])
   if section:lines+=['\n### '+title]+section
  lines+=['\n### Key Uncertainty']
  lines+=['UNCERTAINTY: '+x for x in e['uncertainties'][:3]] or [say('No additional uncertainty was extracted; this does not imply certainty.','추가 불확실성이 추출되지 않았으며, 확실성을 의미하지 않습니다.')]
  for conflict in e['contradictions']:
   lines.append('UNCERTAINTY: Reporting differs on this point — '+conflict['key'])
   for account in conflict['accounts']:
    ids=[f['id'] for f in e['facts'] if f['text']==account['text']]
    if ids:
     value=unit({'text':account['text'],'evidence_ids':ids},'UNCERTAINTY — conflicting report')
     if value:lines.append(value)
   lines.append(conflict['resolution'])
  lines+=lines_for(analysis['uncertainties'],'UNCERTAINTY')
  watch=lines_for(analysis['watch_items'],'WATCH ITEM')
  if watch:lines+=['\n### Watch Next']+watch
  lines+=['Confidence: '+e['confidence'],'Sources:']
  for sid in e['source_ids']:
   source=sources[sid];lines.append(f"- [{source['source']}]({source['url']}) · published {source['published'] or 'unverified'} · retrieved {source['retrieved']} · Tier {source['quality']['tier']}"+(' · partial body' if source['partial'] else ''))
 lines+=['\n# CROSS-MARKET / CROSS-SECTOR SIGNALS']
 lines+=lines_for(report['synthesis']['cross_sector_signals'],'SIGNAL') or [say('No supported connection between separate events was established.','별개 사건을 연결할 충분한 근거가 확보되지 않았습니다.')]
 lines+=['\n# EMERGING TRENDS']
 trends=lines_for(report['synthesis']['trends'],'SIGNAL — Emerging trend')
 lines+=trends or [say('Insufficient observations across time to establish a trend.','서로 다른 날짜의 관측이 충분하지 않아 추세로 판단하지 않습니다.')]
 for t in report['synthesis']['trends'] if trends else []:lines.append('Evidence events: '+', '.join(t['event_ids'])+' · Confidence: '+t['confidence'])
 lines+=['\n# MARKET / BUSINESS IMPLICATIONS']
 observed=[u for e in report['events'] for u in e['analysis']['market_observation']]
 lines+=lines_for(observed,'FACT — sourced market observation') or [say('Observed market reaction: data unavailable from retrieved sources.','실제 시장 반응: 수집 자료에서 확인할 수 없습니다.')]
 lines+=lines_for(report['synthesis']['market_implications'],'ANALYSIS — conditional implication')
 lines+=['\n# RISK RADAR']
 risks=[]
 for risk in report['synthesis']['risks']:
  line=unit(risk,'SCENARIO — Risk | Trigger | Potential consequence')
  if line:risks.append(line+f" · Probability: {risk['probability']} (qualitative judgment) · Impact: {risk['impact']}")
 lines+=risks or [say('Insufficient evidence for a ranked risk assessment.','근거가 부족해 위험 순위나 발생 가능성을 만들어내지 않습니다.')]
 lines+=['\n# WATCHLIST — NEXT 24–72 HOURS']
 watch=[u for e in report['events'] for u in e['analysis']['watch_items']]
 published_watch=[]
 for item in watch:
  line=unit(item,'WATCH ITEM')
  if line:published_watch.append(line+' · '+(item['expected_at'] or say('Timing unverified; monitor, not a confirmed 72-hour calendar event.','일정 미확인 — 확인된 72시간 내 일정이 아니라 관찰 대상입니다.')))
 lines+=published_watch
 if not published_watch:lines.append(say('No specific upcoming release time was verified in retrieved sources.','수집 자료에서 구체적인 후속 발표 일정을 확인하지 못했습니다.'))
 lines+=['\n# BOTTOM LINE']
 lines+=lines_for(report['synthesis']['bottom_line']) or [say('Keep the verified developments separate from unresolved reports; interpretation is limited by available evidence.','확인된 사실과 미확인 보도를 구분해야 합니다. 현재 근거를 넘는 판단은 보류합니다.')]
 if report['limitations']:lines+=['\n## Retrieval / Quality Limits']+['- '+x for x in report['limitations'][:10]]
 lines.append('\n'+say('Local model analysis; confidence describes evidence support, not forecast certainty.','로컬 모델 분석입니다. 신뢰도는 근거의 지지 수준이며 전망의 확실성이 아닙니다.'))
 report['publication_budgets']=budget
 return '\n'.join(lines)
