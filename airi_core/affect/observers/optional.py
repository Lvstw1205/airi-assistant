"""Integration contracts only. No camera, microphone, model download or inference."""
class DisabledObserver:
    def observe(self,*args,**kwargs):
        raise RuntimeError('This observer requires explicit enablement and measured local latency/memory before use.')

VoiceObserver=DisabledObserver
FaceObserver=DisabledObserver
