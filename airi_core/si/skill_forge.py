"""Proposals only; no generated code execution or tool registration."""
from .constitution import validate_candidate

def eligible(repetitions,age_days,cfg):
    return repetitions>=cfg['proposal_min_repeats'] and age_days<=cfg['proposal_window_days']

def draft(candidate,cfg,allowed_tools):
    return {'state':'draft','digest':validate_candidate(candidate,cfg,allowed_tools),'candidate':candidate,'applied':False,'evaluation_required':True}
