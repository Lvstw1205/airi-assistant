"""Shared-resource gating contract. No independent scheduler is installed."""
from datetime import datetime
from zoneinfo import ZoneInfo

def allowed(cfg,*,voice_idle,gpu_slot_granted,now=None):
    if not cfg['enabled'] or not cfg['background_enabled'] or not voice_idle or not gpu_slot_granted:return False
    current=(now or datetime.now(ZoneInfo(cfg['timezone']))).astimezone(ZoneInfo(cfg['timezone'])).strftime('%H:%M')
    start,end=cfg['night_start'],cfg['night_end']
    return start<=current<end if start<end else current>=start or current<end

def prepared_valid(created,now,cfg):return 0<=now-created<cfg['prepared_context_ttl_hours']*3600
