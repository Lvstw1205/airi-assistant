"""Time-aware EWMA. Cold start never produces a notable-change claim."""
import math

def update(store,observation,cfg):
    ts=observation['ts'];x=observation['valence'];source=observation['source']
    with store.db() as c:
        previous=c.execute('SELECT * FROM user_baseline WHERE source=?',(source,)).fetchone()
        if not previous:
            c.execute('INSERT INTO user_baseline VALUES(?,?,?,?,?,?)',(source,x,0.0,1,ts,ts))
            return {'cold_start':True,'baseline_delta':None,'notable_change':False}
        age=ts-previous['first_ts'];variance=previous['variance']
        cold=age<cfg['cold_start_days']*86400 or previous['n']<cfg['baseline_min_samples']
        z=(x-previous['mean'])/math.sqrt(variance) if variance>1e-6 else None
        elapsed=max(0,ts-previous['last_ts']);alpha=1-math.exp(-math.log(2)*elapsed/(cfg['baseline_half_life_days']*86400))
        mean=previous['mean']+alpha*(x-previous['mean'])
        variance=(1-alpha)*(variance+alpha*(x-previous['mean'])**2)
        c.execute('UPDATE user_baseline SET mean=?,variance=?,n=n+1,last_ts=? WHERE source=?',(mean,variance,ts,source))
        return {'cold_start':cold,'baseline_delta':None if cold else z,'notable_change':not cold and z is not None and abs(z)>=cfg['change_z_threshold']}
