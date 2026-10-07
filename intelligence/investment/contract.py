import json,math,re
from pathlib import Path
import jsonschema
BAD=('stale','missing','conflicting','unsupported')
def validate(report):
 schema=json.loads(Path(__file__).with_name('report.schema.json').read_text())
 jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).validate(report)
 evidence={x['id']:x for x in report['evidence']}
 if len(evidence)!=len(report['evidence']):raise ValueError('Duplicate evidence ID')
 for e in evidence.values():
  if any(x not in evidence for x in e.get('input_evidence_ids',[])):raise ValueError('Missing calculation input')
  if e.get('value') is not None and not math.isfinite(e['value']):raise ValueError('Nonfinite evidence')
 for r in report['market_rows']:
  refs=r['evidence_ids']
  if any(x not in evidence for x in refs):raise ValueError('Unknown row evidence')
  if r['value'] is not None and not any(evidence[x].get('value')==r['value'] and evidence[x].get('unit')==r['unit'] for x in refs):raise ValueError('Value/unit mismatch')
  if r.get('change') is not None and not any(evidence[x].get('value')==r['change'] and evidence[x].get('unit')==r['change_unit'] for x in refs):raise ValueError('Change mismatch')
 for c in report['summary']+report['analysis']+[c for s in report['scenarios'] for c in s['effects']]:
  if not c['evidence_ids'] or any(x not in evidence for x in c['evidence_ids']):raise ValueError('Claim lacks evidence')
  if c['kind'] in ('inference','scenario') and any(evidence[x]['quality_status'] in BAD for x in c['evidence_ids']):raise ValueError('Degraded evidence cannot support current inference')
  if c['kind'] in ('inference','scenario') and re.search(r'\d|확률|보장|반드시|무조건',c['text']):raise ValueError('Unverified numeric/predictive claim')
 for s in report['scenarios']:
  if not all(s[k] for k in ('horizon','assumptions','effects','invalidation_conditions')) or 'probability' in s:raise ValueError('Incomplete scenario')
 for w in report['watch_items']:
  if not w['evidence_ids'] or any(x not in evidence for x in w['evidence_ids']):raise ValueError('Unknown watch evidence')
 if report.get("editorial"):
  from .editorial import check
  check(report)
 return True
