from .constitution import validate_candidate,version_diff,may_apply

def propose(old,new,cfg,allowed_tools,regressions,evaluation_days):
    import json
    digest=validate_candidate(new,cfg,allowed_tools)
    return {'state':'review_required','digest':digest,'diff':version_diff(json.dumps(old,ensure_ascii=False,indent=2)+'\n',json.dumps(new,ensure_ascii=False,indent=2)+'\n'),'regressions':regressions,'evaluation_days':evaluation_days,'eligible_after_approval':may_apply(owner_approved=True,regressions=regressions,evaluation_days=evaluation_days,cfg=cfg),'applied':False}
