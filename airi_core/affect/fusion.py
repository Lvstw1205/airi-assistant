"""Advisory fusion. Face alone cannot establish the owner's emotional state."""
def fuse(observations,cfg):
    known=[o for o in observations if o.get('owner',True) and o.get('confidence',0)>0]
    if not known:return {'valence':None,'arousal':None,'confidence':0.0,'evidence':[],'notable_change':False,'trend_24h':None}
    weighted=[]
    for o in known:
        weight=cfg['channel_weights'].get(o['source'],0)*o['confidence']
        if o['source']=='face':weight=min(weight,cfg['face_weight_cap'])
        weighted.append((o,weight))
    total=sum(w for _,w in weighted)
    if not total:return fuse([],cfg)
    vals=[o['valence'] for o in known]
    conflict=max(vals)-min(vals)>cfg['conflict_delta']
    confidence=sum(o['confidence']*w for o,w in weighted)/total
    if conflict:confidence*=.5
    if all(o['source']=='face' for o in known):confidence=min(confidence,cfg['face_weight_cap'])
    return {'valence':sum(o['valence']*w for o,w in weighted)/total,'arousal':sum(o['arousal']*w for o,w in weighted)/total,'confidence':confidence,'evidence':[o.get('evidence','') for o in known],'notable_change':False,'trend_24h':None,'conflicting_channels':conflict}
