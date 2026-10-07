import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import device_transport as transport
import devices
import llm_client


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        payload = json.dumps({'models': [{'name': 'demo:1b', 'digest': 'weights-a'},
                                        {'name': 'remote:cloud', 'remote_host': 'https://example.test'}]}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.received.append(request)
        if request.get('stream'):
            payload = b'data: {"choices":[{"delta":{"content":"worker answer"}}]}\n\ndata: [DONE]\n\n'
        else:
            payload = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'worker answer'},
                                              'finish_reason': 'stop'}]}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.ollama = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
        self.ollama.received = []
        self.base = 'http://127.0.0.1:' + str(self.ollama.server_port)
        self.start(self.ollama)
        self.worker = transport.make_worker(Path(self.tmp.name)/'worker', '127.0.0.1', 0, ollama=self.base)
        self.start(self.worker)
        self.item = dict(self.worker.identity)

    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)

    def test_pairing_roundtrip_and_secret_stays_out_of_public_status(self):
        code = transport.encode_pairing(self.item)
        self.assertEqual(transport.decode_pairing(code), self.item)
        registry = devices.Registry(Path(self.tmp.name)/'main', self.base+'/v1')
        registry.add(code, 'Test worker')
        status = registry.status('demo:1b')
        self.assertEqual(len(status['devices']), 2)
        self.assertNotIn(self.item['secret'], json.dumps(status))
        self.assertNotIn('remote:cloud', json.dumps(status))
        self.assertEqual(os.stat(registry.path).st_mode & 0o777, 0o600)
        reloaded = devices.Registry(Path(self.tmp.name)/'main', self.base+'/v1')
        self.assertEqual(reloaded.load()[0]['name'], 'Test worker')

    def test_wrong_certificate_and_wrong_pairing_key_are_rejected(self):
        for key in ('fingerprint', 'secret'):
            bad = {**self.item, key: secrets.token_hex(32)}
            with self.assertRaises(ValueError): transport.remote_open(bad, '/status')
        self.assertEqual(self.ollama.received, [])

    def test_signed_requests_cannot_be_replayed(self):
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        headers = {'X-AIRI-Time': stamp, 'X-AIRI-Nonce': nonce,
                   'X-AIRI-Signature': transport.signature(self.item['secret'], 'GET', '/status', stamp, nonce, b'')}
        statuses = []
        for _ in range(2):
            connection = transport.PinnedConnection(self.item, 3)
            connection.request('GET', '/status', headers=headers)
            response = connection.getresponse(); statuses.append(response.status); response.read(); connection.close()
        self.assertEqual(statuses, [200, 403])

    def test_stream_reaches_paired_worker_without_uploading_a_directory(self):
        endpoint = {'base_url': 'https://127.0.0.1:'+str(self.worker.server_port)+'/v1',
                    'device': self.item, 'device_id': 'test', 'device_name': 'Test worker',
                    'installed_models': ['demo:1b']}
        with patch.object(llm_client, 'endpoints_for', return_value=[endpoint]):
            result = list(llm_client.stream([{'role': 'user', 'content': 'test request'}], 'demo:1b'))
        self.assertEqual(''.join(p['text'] for p in result if p['type']=='token'), 'worker answer')
        self.assertEqual(result[0]['device_name'], 'Test worker')
        self.assertEqual(len(self.ollama.received), 1)

    def test_worker_does_not_accept_cloud_model_or_file_api(self):
        with self.assertRaises(ValueError):
            transport.remote_open(self.item, '/v1/chat/completions', {'model':'remote:cloud','messages':[]})
        with self.assertRaises(ValueError): transport.remote_open(self.item, '/files')
        self.assertFalse(self.ollama.received)

    def test_remove_and_disable_prevent_routing_without_erasing_records(self):
        registry = devices.Registry(Path(self.tmp.name)/'main', self.base+'/v1')
        identifier = registry.add(transport.encode_pairing(self.item))
        registry.change(identifier, enabled=False)
        self.assertEqual([e['device_id'] for e in registry.endpoints('demo:1b')], ['local'])
        registry.change(identifier, remove=True)
        self.assertEqual(registry.load(), [])
        with self.assertRaises(ValueError): registry.change('local', remove=True)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.registry = devices.Registry(self.tmp.name)
        self.registry.checked_at = time.time()
        for identifier, memory in [('local', 8), ('small', 16), ('large', 64)]:
            self.registry.observations[identifier] = {
                'id':identifier, 'name':identifier, 'online':True, 'enabled':True, 'state':'ready',
                'models':[{'name':'demo:1b','digest':'same'}], 'hardware':{'memory_gb':memory,'cpu_count':8},
                'active_jobs':0, 'latency_ms':5}

    def test_automatic_main_uses_available_capacity_and_same_model_weights(self):
        self.assertEqual(self.registry.candidates('demo:1b')[0]['id'], 'large')
        self.registry.observations['large']['models'][0]['digest']='different'
        self.assertEqual(self.registry.candidates('demo:1b')[0]['id'], 'small')

    def test_disconnected_main_is_replaced_without_changing_the_model(self):
        self.registry.candidates('demo:1b')
        self.registry.failure('large')
        self.assertEqual(self.registry.candidates('demo:1b')[0]['id'], 'small')
        self.registry.observations['small']['online']=False
        self.assertEqual(self.registry.candidates('demo:1b')[0]['id'], 'local')
        self.assertEqual(self.registry.candidates('missing:1b'), [])

    def test_small_score_changes_do_not_flip_main_repeatedly(self):
        self.registry.candidates('demo:1b')
        self.registry.observations['small']['hardware']['memory_gb']=66
        self.assertEqual(self.registry.candidates('demo:1b')[0]['id'], 'large')

    def test_single_computer_needs_no_registration(self):
        self.registry.observations={k:v for k,v in self.registry.observations.items() if k=='local'}
        self.assertEqual(self.registry.status('demo:1b')['main']['id'], 'local')
        self.assertFalse(self.registry.path.exists())

    def test_public_hosts_and_malformed_pairing_are_rejected(self):
        for address in ('8.8.8.8', '0.0.0.0', 'example.com', '169.254.169.254'):
            with self.assertRaises(ValueError): transport.private_address(address)
        with self.assertRaises(ValueError): transport.decode_pairing('not a code')

    def test_no_stream_retry_after_first_token(self):
        class BrokenStream:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
                raise OSError('disconnected')
        endpoints=[{'base_url':'http://127.0.0.1:1/v1','installed_models':['demo:1b']},
                   {'base_url':'http://127.0.0.1:2/v1','installed_models':['demo:1b']}]
        with patch.object(llm_client,'endpoints_for',return_value=endpoints), patch.object(llm_client,'open_url',return_value=BrokenStream()) as request:
            with self.assertRaises(ValueError): list(llm_client.stream([], 'demo:1b'))
        self.assertEqual(request.call_count,1)


if __name__ == '__main__': unittest.main()
