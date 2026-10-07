import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import threading
import time
import urllib.request
import urllib.parse
import uuid
from .config import load
from .auth import Auth
from .network import Peer


def utc():
    return datetime.now(timezone.utc).isoformat()


class Node:
    def __init__(self, path):
        self.path = Path(path)
        self.config = load(path)
        if self.config.secret_file.stat().st_mode & 0o077:
            raise ValueError('Node secret must be private (0600)')
        self.secret = self.config.secret_file.read_bytes().strip()
        if len(self.secret) < 32:
            raise ValueError('Node secret must have at least 32 bytes')
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.auth = Auth(self.config, self.secret)
        self.started = time.monotonic()
        self.peer = Peer(self.config, self.secret, self.event)
        self.lock, self.events = threading.Lock(), []
        self.models = {'available':[], 'loaded':[], 'checked_at':None, 'error':None}
        self.servers = []
        self.serving = False
        self.executor = None
        if self.config.queue_enabled:
            from .executor import Runtime
            self.executor = Runtime(self)

    def event(self, type_, data):
        value = {'event_id':str(uuid.uuid4()), 'type':type_, 'ts':utc(), 'node_id':self.config.node_id,
                 'task_id':None, 'correlation_id':None, 'data':data}
        with self.lock:
            self.events = (self.events+[value])[-200:]
        with (self.config.state_dir/'node-events.jsonl').open('a') as file:
            file.write(json.dumps(value)+'\n')

    def envelope(self, value):
        return {'schema_version':1, 'node_id':self.config.node_id, 'ts':utc(), **value}

    def model_loop(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not self.peer.stop.is_set():
            try:
                with opener.open(self.config.ollama_url+'/api/tags', timeout=2) as res:
                    tags = json.load(res)['models']
                with opener.open(self.config.ollama_url+'/api/ps', timeout=2) as res:
                    loaded = json.load(res)['models']
                self.models = {'available':[{'name':m['name'],'size':m.get('size')} for m in tags],
                               'loaded':[{'name':m['name'],'size':m.get('size'),'size_vram':m.get('size_vram')} for m in loaded],
                               'checked_at':utc(), 'error':None}
            except Exception as e:
                self.models = {**self.models, 'error':type(e).__name__}
            self.peer.stop.wait(15)

    def get(self, path):
        if path == '/health':
            # Liveness does not depend on the peer, preventing circular DEGRADED feedback.
            return self.envelope({'status':'OK', 'checks':{'config':'OK', 'service':'OK'}})
        if path == '/status':
            return self.envelope({'uptime':round(time.monotonic()-self.started),
                'mode':'NORMAL' if self.peer.state=='ONLINE' else 'DEGRADED',
                'peer':self.peer.snapshot(), 'active_tasks':self.executor.active_tasks if self.executor else [],
                'tasks_owner':'common execution ledger; legacy workroom remains its own adapter',
                'phase':2 if self.executor else 1, 'models':self.models, 'new_distributed_executor':bool(self.executor),
                'executor':self.executor.status() if self.executor else None})
        if path == '/models':
            return self.envelope(self.models)
        if path == '/capabilities':
            return self.envelope({'services':['node-health','authenticated-peer-status','model-discovery'],
                'enabled_agents':self.config.enabled_agents, 'stage_b':False, 'tasks_supported':bool(self.executor),
                'task_tools':['system.health','system.storage'] if self.executor else []})
        if urllib.parse.urlsplit(path).path == '/tasks' and self.executor:
            if not self.executor.primary:return self.envelope({'tasks':[],'authoritative_node':'AIRI_PRIME'})
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            return self.envelope({'tasks':self.executor.ledger.tasks(query.get('state',[None])[0])})
        if path == '/metrics':
            usage = shutil.disk_usage(self.config.state_dir)
            return self.envelope({'load_average':list(os.getloadavg()), 'cpu_count':os.cpu_count(),
                'disk_free_bytes':usage.free, 'disk_total_bytes':usage.total, 'latency_ms':self.peer.latency_ms,
                'cpu_percent':None, 'ram_bytes':None, 'gpu_percent':None,
                'detailed_metrics_source':'existing /api/mac-metrics'})
        if path == '/events':
            with self.lock:
                return self.envelope({'events':list(self.events)})
        return None

    def start(self):
        node = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send(self, value, code=200):
                data = json.dumps(value).encode()
                self.send_response(code)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if not (self.path=='/health' and self.client_address[0]=='127.0.0.1') and not node.auth.verify(self.headers.get('Authorization',''),'GET',self.path,b''):
                    return self.send(node.envelope({'error':'Unauthorized'}),401)
                if urllib.parse.urlsplit(self.path).path in ('/pixel/status','/pixel/snapshot','/pixel/events','/system','/execution/status'):
                    return self.proxy('GET',b'')
                result = node.get(self.path)
                self.send(result or node.envelope({'error':'Not found'}),200 if result else 404)
            def do_POST(self):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 <= length <= 65536:
                        raise ValueError()
                except ValueError:
                    return self.send(node.envelope({'error':'Invalid request size'}),413)
                self.connection.settimeout(3)
                body = self.rfile.read(length)
                if not node.auth.verify(self.headers.get('Authorization',''),'POST',self.path,body):
                    return self.send(node.envelope({'error':'Unauthorized'}),401)
                if self.path in ('/pixel/analyze','/pixel/cancel','/execution/plan','/execution/cancel','/execution/approve'):
                    return self.proxy('POST',body)
                if node.executor:
                    try:
                        value=json.loads(body)
                        if not isinstance(value,dict):raise ValueError('Object required')
                        if self.path=='/tasks':result=node.executor.submit(value)
                        elif self.path=='/worker/tick':result=node.executor.receive(value)
                        elif self.path.startswith('/tasks/') and self.path.endswith('/cancel') and node.executor.primary:
                            result=node.executor.ledger.cancel(self.path.split('/')[2])
                        else:return self.send(node.envelope({'error':'Not found'}),404)
                        return self.send(node.envelope(result))
                    except (ValueError,KeyError,TypeError):
                        return self.send(node.envelope({'error':'Invalid task request'}),400)
                self.send(node.envelope({'error':'New distributed executor is not enabled; existing workroom owns tasks.'}),409)
            def proxy(self,method,body):
                if node.config.node_id!='AIRI_PRIME':
                    return self.send(node.envelope({'error':'Primary only'}),409)
                # Narrow adapter to the existing local AIRI API. No arbitrary URL forwarding.
                path='/api/expansion/status' if self.path=='/system' else '/api'+self.path
                token=Path(__file__).resolve().parents[1]/'data/session-token'
                try:
                    req=urllib.request.Request('http://127.0.0.1:8766'+path,
                        data=body if method=='POST' else None,
                        headers={'X-AIRI-Token':token.read_text().strip(),'Content-Type':'application/json'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=45) as r:
                        data=json.load(r)
                    self.send(data)
                except urllib.error.HTTPError as error:
                    try:value=json.loads(error.read(10000))
                    except Exception:value={'error':'Primary request failed'}
                    self.send(value,error.code)
                except Exception:
                    self.send({'error':'Primary AIRI application unavailable'},503)
        try:
            for address in self.config.bind:
                server = ThreadingHTTPServer((address,self.config.port),Handler)
                server.daemon_threads = True
                self.servers.append(server)
            for server in self.servers:
                threading.Thread(target=server.serve_forever,daemon=True).start()
            self.serving = True
            threading.Thread(target=self.peer.run,daemon=True).start()
            threading.Thread(target=self.model_loop,daemon=True).start()
            if self.executor:self.executor.start()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.peer.close()
        for server in self.servers:
            if self.serving:server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    node = Node(args.config)
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig,lambda *_:stopped.set())
    # Validate first; a bad reload preserves the running configuration.
    def reload_config(*_):
        try:
            candidate = load(args.config)
            if candidate == node.config:
                node.event('CONFIG_VALIDATED', {})
            else:
                node.event('CONFIG_RESTART_REQUIRED', {'reason':'Network identity changes require controlled service restart'})
        except Exception as error:
            node.event('CONFIG_REJECTED', {'reason':type(error).__name__})
    signal.signal(signal.SIGHUP,reload_config)
    node.start()
    print(json.dumps(node.envelope({'service':'airi_node','status':'started'})),flush=True)
    stopped.wait()
    node.close()


if __name__ == '__main__':
    main()
