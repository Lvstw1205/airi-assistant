"""Read-only dashboard adapter for the actual control plane and existing workers."""
import json
from pathlib import Path
import time
import urllib.request
import mac_cluster
import status_widgets
import pixel_floor
from airi_node.auth import header


def snapshot(app):
    node=None;error=None
    try:
        key=(app.DATA/'node/pair-secret').read_bytes().strip()
        request=urllib.request.Request('http://127.0.0.1:8740/status',headers={'Authorization':header(key,'AIRI_PRIME','GET','/status')})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=1) as r:
            node=json.load(r)
    except Exception as e:
        error=type(e).__name__
    cluster=mac_cluster.status(app)
    metrics=status_widgets.mac_snapshot(app)
    try:
        import orchestration
        execution=orchestration.service(app).status()
    except (ImportError,OSError,ValueError):execution=None
    return {'as_of':time.time(),'node':node,'node_error':error,'cluster':cluster,'metrics':metrics,
            'pixel':pixel_floor.service(app).status(),'stock101':status_widgets.stock_snapshot(app),'execution':execution,
            'implementation':{'node_plane':bool(node),'distributed_executor':bool(node and node.get('executor')),'redis':bool(node and (node.get('executor') or {}).get('redis')=='ONLINE'),
                'm1_legacy_worker':cluster.get('connected') is True,'pixel_local_ai':True,
                'note':'공통 작업 큐·두 Mac 연결·픽셀 작업실이 적용됨. 부서 분석은 아래에서 직접 요청하며 기존 PDF 보고서·영상·Telegram 작업은 기존 실행 경로를 유지해.'}}
