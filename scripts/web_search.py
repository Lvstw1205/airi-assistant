"""Isolated search dependency runner; accepts a public query via stdin, not argv."""
import json,sys
from ddgs import DDGS
try:
    request=json.load(sys.stdin)
    results=DDGS(timeout=7).text(request['query'],region='ca-en',max_results=request.get('limit',5))
    print(json.dumps([{'title':r.get('title',''),'url':r.get('href',''),'snippet':r.get('body',''),'published_at':None} for r in results],ensure_ascii=False))
except Exception:
    print(json.dumps({'error':'Search provider unavailable'}));sys.exit(1)
