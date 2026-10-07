def metrics(evaluations,skills,proposals):
    scored=[x for x in evaluations if x.get('human_validated')]
    adopted=[x for x in proposals if x.get('state')=='applied']
    return {'evaluated_cases':len(scored),'trusted_skills':sum(s.get('state')=='trusted' for s in skills),'proposal_adoption_rate':len(adopted)/len(proposals) if proposals else None,'recall_at_5':None,'deep_think_win_rate':None,'trend':[],'regressions':None,'growth_claim_supported':False}
