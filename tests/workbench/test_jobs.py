from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from uuid import UUID, uuid4

from rap_workbench.briefs import validate_brief
from rap_workbench.jobs import IdempotencyConflict, JobStore, ProviderUnavailable
from rap_workbench.server import make_server


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state/jobs.sqlite3'
        self.store = JobStore(self.path)
        self.payload = {'mode': 'brief_preview', 'brief': {'topic': '  中文庆祝  '}}

    def test_preview_is_a_complete_downloadable_plan_for_each_duration(self):
        for duration in (10, 12, 15):
            payload = {'mode': 'brief_preview', 'brief': {'topic': '测试', 'duration_seconds': duration,
                       'mode': 'duo', 'lyrics': '用户提供的歌词'}}
            job, created = self.store.create(payload)
            self.assertTrue(created)
            UUID(job['id'])
            self.assertTrue(job['created_at'].endswith('Z'))
            self.assertEqual((job['status'], job['kind']), ('completed', 'brief_preview'))
            result = job['result']
            self.assertEqual(result['parameters'], validate_brief(payload['brief']))
            self.assertIs(result['is_generated_video'], False)
            self.assertEqual(sum(shot['duration_seconds'] for shot in result['storyboard']), duration)
            position = 0
            for shot in result['storyboard']:
                self.assertEqual(shot['start_seconds'], position)
                self.assertGreater(shot['duration_seconds'], 0)
                self.assertEqual(shot['performers'], 2)
                position = shot['end_seconds']
            self.assertEqual(position, duration)
            self.assertNotIn('url', json.dumps(result))
            self.assertEqual(self.store.get(job['id']), job)
        self.assertEqual(len(self.store.list()), 3)

    def test_normalized_idempotency_reopen_and_independent_results(self):
        original, created = self.store.create(self.payload, 'key-1')
        self.assertTrue(created)
        normalized = {'mode': 'brief_preview', 'brief': validate_brief(self.payload['brief']),
                      'idempotency_key': 'key-1'}
        replay, created = JobStore(self.path).create(normalized)
        self.assertFalse(created)
        self.assertEqual(replay, original)
        replay['result']['parameters']['topic'] = 'local mutation'
        self.assertEqual(self.store.get(original['id']), original)
        self.assertEqual(JobStore(self.path).list(), [original])
        self.assertIsNone(self.store.get(str(uuid4())))
        with self.assertRaises(ValueError):
            self.store.get('../../file')
        self.assertEqual(self.payload['brief'], {'topic': '  中文庆祝  '})

    def test_conflicting_payload_or_mode_does_not_write(self):
        original, _ = self.store.create(self.payload, 'fixed')
        for payload in ({'mode': 'brief_preview', 'brief': {'topic': 'different'}},
                        {'mode': 'provider_render', 'brief': {'topic': '中文庆祝'}}):
            with self.assertRaises(IdempotencyConflict):
                JobStore(self.path).create(payload, 'fixed')
        self.assertEqual(self.store.list(), [original])

    def test_concurrent_retries_across_stores_only_create_one_job(self):
        barrier = threading.Barrier(8)
        def retry(index):
            store = JobStore(self.path)
            barrier.wait(timeout=5)
            return store.create(self.payload, 'concurrent')
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(retry, range(8)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({job['id'] for job, _ in results}), 1)
        self.assertEqual(len(JobStore(self.path).list()), 1)

    def test_no_key_creates_independent_jobs(self):
        first, _ = self.store.create(self.payload)
        second, _ = self.store.create(self.payload)
        self.assertNotEqual(first['id'], second['id'])

    def test_provider_unavailable_creates_nothing_and_does_not_consume_key(self):
        render = {'mode': 'provider_render', 'brief': {'topic': 'test'}, 'idempotency_key': 'unused'}
        for _ in range(2):
            with self.assertRaises(ProviderUnavailable):
                self.store.create(render)
        self.assertEqual(JobStore(self.path).list(), [])
        self.assertTrue(self.store.create(self.payload, 'unused')[1])

    def test_invalid_payloads_never_write(self):
        bad = [None, [], {}, {'mode': 'pretend', 'brief': {'topic': 'x'}},
               {'mode': 'brief_preview'}, {'mode': 'brief_preview', 'brief': []},
               dict(self.payload, file='/tmp/picture'),
               {'mode': 'brief_preview', 'brief': {'topic': 'x', 'id': str(uuid4())}},
               {'mode': 'brief_preview', 'brief': {'topic': 'x', 'duration_seconds': True}},
               {'mode': 'brief_preview', 'brief': {'topic': 'x', 'quality': '4k'}},
               {'mode': 'brief_preview', 'brief': {'topic': '\ud800'}}]
        bad.extend(dict(self.payload, idempotency_key=key) for key in (None, '', ' ', 1, [], 'x' * 201, '\ud800'))
        for payload in bad:
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(ValueError):
                    self.store.create(payload)
        with self.assertRaises(ValueError):
            self.store.create(dict(self.payload, idempotency_key='body'), 'header')
        self.assertEqual(self.store.list(), [])


class JobHTTPTests(unittest.TestCase):
    def test_real_server_201_200_409_503_and_get(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'research/sites').mkdir(parents=True)
            server = make_server(port=0, root=root, db_path=root / 'briefs.sqlite3')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, path, payload=None, key=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                headers = {'Content-Type': 'application/json'}
                if key is not None:
                    headers['Idempotency-Key'] = key
                try:
                    connection.request(method, path, json.dumps(payload) if payload is not None else None, headers)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()
            try:
                payload = {'mode': 'brief_preview', 'brief': {'topic': '  HTTP  '}}
                status, body = request('POST', '/api/jobs', payload, 'http')
                self.assertEqual(status, 201)
                job = body['job']
                payload['brief'] = validate_brief(payload['brief'])
                self.assertEqual(request('POST', '/api/jobs', payload, 'http'), (200, body))
                self.assertEqual(request('GET', '/api/jobs/' + job['id']), (200, body))
                status, error = request('POST', '/api/jobs', dict(payload, brief={'topic': 'other'}), 'http')
                self.assertEqual((status, error['error']['code']), (409, 'IDEMPOTENCY_CONFLICT'))
                status, error = request('POST', '/api/jobs', dict(payload, mode='provider_render'), 'render')
                self.assertEqual((status, error['error']['code']), (503, 'PROVIDER_UNAVAILABLE'))
                status, error = request('POST', '/api/jobs', dict(payload, brief={'topic': 'x', 'photo': '/tmp/x'}))
                self.assertEqual((status, error['error']['code']), (400, 'INVALID_INPUT'))
                self.assertEqual(server.get_jobs().list(), [job])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
