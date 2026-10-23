"""Actual loopback HTTP contract tests, not paid-provider or browser tests."""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

from rap_workbench.provider_journal import SubmissionStore
from rap_workbench.sync_provider import SyncClient, SyncTransportError, build_generation_request


REMOTE_ID = 'contract-generation_1'
KEY = 'fixture-key-not-a-real-credential'
OUTPUT = 'https://media.example.test/contract-output.mp4?signature=OUTPUT_ONLY'


def generation(status):
    return {'id': REMOTE_ID, 'createdAt': datetime.now(timezone.utc).isoformat(),
            'model': 'sync-3', 'input': [], 'status': status,
            'outputUrl': OUTPUT if status == 'COMPLETED' else None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, payload, extra=None):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def capture(self, body):
        with self.server.lock:
            self.server.requests.append({'method': self.command, 'path': self.path,
                                         'key': self.headers.get('Idempotency-Key'), 'body': body})
        if self.headers.get('x-api-key') != KEY:
            self.reply(401, {'statusCode': 401, 'errorCode': 'invalid_key', 'message': 'fixture only'})
            return False
        return True

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if not self.capture(raw):
            return
        body = json.loads(raw)
        if self.path == '/v2/generations/estimate':
            if body != {'model': 'sync-3', 'duration': 12, 'fps': 25, 'reasoningEnabled': False}:
                return self.reply(400, {'statusCode': 400, 'errorCode': 'invalid_estimate', 'message': 'fixture only'})
            return self.reply(200, {'estimatedFrameCount': 300, 'estimatedGenerationCost': 0.15,
                                    'estimatedCredits': None})
        if self.path != '/v2/generate':
            return self.reply(404, {'statusCode': 404, 'errorCode': 'unknown_route', 'message': 'fixture only'})
        if self.server.unknown_submission:
            return self.reply(503, {'statusCode': 503, 'errorCode': 'IDEMPOTENCY_OUTCOME_UNKNOWN',
                                    'message': 'fixture only', 'generationId': REMOTE_ID}, {'Retry-After': '0'})
        return self.reply(201, generation('PENDING'))

    def do_GET(self):
        if not self.capture(None):
            return
        if self.path != '/v2/generate/' + REMOTE_ID:
            return self.reply(404, {'statusCode': 404, 'errorCode': 'unknown_generation', 'message': 'fixture only'})
        if self.server.fail_get:
            return self.reply(503, {'statusCode': 503, 'errorCode': 'temporary_observation_error',
                                    'message': 'fixture only'}, {'Retry-After': '0'})
        status = self.server.statuses.popleft() if self.server.statuses else 'COMPLETED'
        return self.reply(200, generation(status))


@contextmanager
def fixture():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.requests = []
    server.lock = threading.Lock()
    server.statuses = deque(('PENDING', 'PROCESSING', 'COMPLETED'))
    server.unknown_submission = False
    server.fail_get = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def transport(method, url, headers, body, timeout):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.sync.so':
            raise AssertionError('Client attempted an unexpected provider origin')
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=timeout)
        try:
            connection.request(method, parsed.path + ('?' + parsed.query if parsed.query else ''),
                               body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    try:
        yield server, SyncClient(KEY, allow_live=True, transport=transport, sleep=lambda _: None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class SyncContractFlowTests(unittest.TestCase):
    def request(self):
        return build_generation_request(visual_type='image',
                                        visual_url='https://media.example.test/portrait.png?sig=INPUT_ONLY',
                                        audio_url='https://media.example.test/voice.wav')

    def test_loopback_http_estimate_submission_observation_and_restart(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as (server, client):
            path = Path(directory) / 'journal.sqlite3'
            store = SubmissionStore(path)
            payload = self.request()
            record, created = store.prepare('contract-action-1', payload)
            self.assertTrue(created)
            self.assertNotIn('INPUT_ONLY', json.dumps(record))
            self.assertEqual(store.payload_for_retry(record['id']), payload)
            self.assertEqual(client.estimate(12, fps=25)['estimatedGenerationCost'], 0.15)
            store.mark_submitting(record['id'])
            pending = client.create(payload, record['idempotency_key'])
            self.assertEqual(pending['status'], 'PENDING')
            store.record_acceptance(record['id'], pending)
            for expected in ('PENDING', 'PROCESSING', 'COMPLETED'):
                snapshot = client.get(REMOTE_ID)
                self.assertEqual(snapshot['status'], expected)
                store.apply_snapshot(record['id'], snapshot)
            completed = SubmissionStore(path).get(record['id'])
            self.assertEqual(completed['state'], 'COMPLETED')
            self.assertEqual(completed['output_url'], OUTPUT)
            self.assertTrue(completed['output_available'])
            store.apply_snapshot(record['id'], dict(pending))
            store.record_observation_error(record['id'], 'temporary_observation_error')
            self.assertEqual(store.get(record['id'])['state'], 'COMPLETED')
            replay, fresh = SubmissionStore(path).prepare('contract-action-1', dict(payload))
            self.assertFalse(fresh)
            self.assertEqual(replay['id'], record['id'])
            self.assertNotIn('INPUT_ONLY', json.dumps(store.events(record['id'])))
            posts = [item for item in server.requests if item['path'] == '/v2/generate']
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]['key'], 'contract-action-1')
            self.assertEqual(json.loads(posts[0]['body']), payload)

    def test_unknown_submission_and_failed_get_never_create_another_action(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as (server, client):
            server.unknown_submission = True
            store = SubmissionStore(Path(directory) / 'journal.sqlite3')
            payload = self.request()
            record, _ = store.prepare('contract-uncertain-1', payload)
            store.mark_submitting(record['id'])
            with self.assertRaises(SyncTransportError) as failed:
                client.create(payload, record['idempotency_key'])
            self.assertTrue(failed.exception.outcome_unknown)
            self.assertEqual(failed.exception.generation_id, REMOTE_ID)
            store.record_submission_unknown(record['id'], error_code=failed.exception.code, remote_id=REMOTE_ID)
            before = len([r for r in server.requests if r['method'] == 'POST'])
            self.assertGreaterEqual(before, 1)
            self.assertLessEqual(before, 2)
            self.assertEqual({r['key'] for r in server.requests}, {'contract-uncertain-1'})
            self.assertEqual(len({r['body'] for r in server.requests}), 1)
            server.fail_get = True
            with self.assertRaises(SyncTransportError) as error:
                client.get(REMOTE_ID)
            store.record_observation_error(record['id'], error.exception.code)
            self.assertEqual(store.get(record['id'])['state'], 'SUBMISSION_UNKNOWN')
            self.assertEqual(len([r for r in server.requests if r['method'] == 'POST']), before)
            server.fail_get = False
            server.statuses = deque(('PROCESSING', 'COMPLETED'))
            for _ in range(2):
                store.apply_snapshot(record['id'], client.get(REMOTE_ID))
            self.assertEqual(store.get(record['id'])['state'], 'COMPLETED')
            replay, created = store.prepare('contract-uncertain-1', payload)
            self.assertFalse(created)
            self.assertEqual(replay['id'], record['id'])
            self.assertEqual(len([r for r in server.requests if r['method'] == 'POST']), before)


if __name__ == '__main__':
    unittest.main()
