"""Bounded conversational proposals; no tools, notifications, or hidden reasoning."""
import time,uuid

HEURISTICS=('relevance','information_gap','expected_benefit','urgency','consistency','originality','balance','flow')

def propose(store,body,scores,episode_id=None):
    if not isinstance(body,str) or not 0<len(body)<=500:raise ValueError('Thought must be a short conversational candidate.')
    if set(scores)!=set(HEURISTICS) or any(type(v) not in (int,float) or not 1<=v<=5 for v in scores.values()):raise ValueError('Eight scores between 1 and 5 are required.')
    key=uuid.uuid4().hex
    with store.db() as c:c.execute('INSERT INTO thoughts(id,ts,body,score,source_episode) VALUES(?,?,?,?,?)',(key,time.time(),body,sum(scores.values()),episode_id))
    return key

def eligible(store,cfg,*,turn_open=False,existing_budget_allows=False):
    if not cfg['proactive_enabled'] or not turn_open or not existing_budget_allows:return None
    items=store.rows('SELECT id,body,score FROM thoughts WHERE used=0 AND score>=? ORDER BY score DESC,ts DESC LIMIT 1',(cfg['thought_score_threshold'],))
    return items[0] if items else None

def reflect_explicit(store):
    """Only copies user-authored episodes into review proposals. Never edits identity."""
    with store.db() as c:
        for row in c.execute('SELECT id,content FROM episodes WHERE explicit_user_statement=1 AND unresolved=1 ORDER BY id DESC LIMIT 5').fetchall():
            body='사용자가 남긴 미결 항목 검토: '+row['content'][:500]
            if not c.execute('SELECT 1 FROM proposals WHERE kind=? AND body=?',('callback',body)).fetchone():
                c.execute('INSERT INTO proposals(ts,kind,body) VALUES(?,?,?)',(time.time(),'callback',body))
