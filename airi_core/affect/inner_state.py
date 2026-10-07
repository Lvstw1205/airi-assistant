"""ALMA-inspired expression state; not a claim of subjective feelings."""
import math,time

def advance(store,cfg,event_valence=0.0,relevance=0.0,now=None):
    now=now or time.time();rows=store.rows('SELECT * FROM airi_state WHERE id=1')
    prior=rows[0] if rows else {'emotion':0.0,'mood':0.0,'updated':now}
    elapsed=max(0,now-prior['updated'])
    emotion=prior['emotion']*2**(-elapsed/cfg['emotion_half_life_seconds'])
    mood=prior['mood']*2**(-elapsed/cfg['mood_half_life_seconds'])
    # Absence only decays toward neutral. It never accumulates resentment.
    if relevance:
        emotion=max(-1,min(1,emotion+event_valence*relevance))
        mood=max(-1,min(1,mood+event_valence*relevance*.1))
    with store.db() as c:c.execute('INSERT OR REPLACE INTO airi_state VALUES(1,?,?,?)',(emotion,mood,now))
    return {'emotion':round(emotion,3),'mood':round(mood,3),'simulated':True}
