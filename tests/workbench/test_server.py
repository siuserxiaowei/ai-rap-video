import http.client
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from uuid import uuid4

from rap_workbench.server import HTTPProblem, MAX_BODY_BYTES, make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'research/sites').mkdir(parents=True)
        (self.root / 'docs').mkdir()
        (self.root / 'docs/decisions.json').write_text('[{"id":"D01"}]', encoding='utf-8')
        (self.root / 'evidence.txt').write_text('Real product details', encoding='utf-8')
        site = {'id': '01', 'name': '中文 Rap', 'url': 'https://example.ai', 'category': 'rap',
                'checked_at': '2026-10-23', 'summary': 'Create a video', 'inputs': ['topic'],
                'outputs': ['video'], 'features': [], 'pricing': {'summary': 'Unknown', 'free_tier': 'Unknown',
                'plans': [], 'source_url': ''}, 'api': {'status': 'unknown', 'summary': 'Unknown', 'url': ''},
                'limitations': ['Untested'], 'best_for': 'Research', 'evidence_status': 'full_page',
                'sources': [{'url': 'https://example.ai', 'title': 'Example', 'kind': 'official',
                             'local_path': 'evidence.txt', 'supports': ['product']}], 'observations': []}
        (self.root / 'research/sites/01.json').write_text(json.dumps(site), encoding='utf-8')
        (self.root / 'web').mkdir()
        (self.root / 'web/index.html').write_text('<h1>工作台</h1>', encoding='utf-8')
        (self.root / 'web/.env').write_text('SECRET', encoding='utf-8')
        (self.root / 'web/escape.txt').symlink_to(self.root / 'evidence.txt')
        (self.root / 'web/alias.txt').symlink_to(self.root / 'web/.env')
        self.server = make_server(port=0, root=self.root, db_path=self.root / 'state/briefs.db')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, payload=None, raw=None, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else raw
        request_headers = {'Content-Type': 'application/json'} if body is not None else {}
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            response_headers = dict(response.getheaders())
            data = json.loads(content) if 'application/json' in response.getheader('Content-Type', '') and content else content
            return response.status, data, response_headers
        finally:
            connection.close()

    def assert_error(self, result, status, code=None):
        self.assertEqual(result[0], status, result)
        self.assertEqual(set(result[1]), {'error'})
        self.assertEqual(set(result[1]['error']), {'code', 'message'})
        if code:
            self.assertEqual(result[1]['error']['code'], code)

    def test_real_http_brief_roundtrip_and_restart(self):
        status, body, _ = self.request('POST', '/api/briefs', {'topic': '  团队庆祝  ', 'mode': 'duo'})
        self.assertEqual(status, 201)
        brief = body['brief']
        self.assertEqual(brief['topic'], '团队庆祝')
        self.assertEqual(brief['quality'], '720p')
        self.assertEqual(self.request('GET', '/api/briefs/' + brief['id'])[:2], (200, {'brief': brief}))
        self.assertEqual(self.request('GET', '/api/briefs')[1], {'briefs': [brief]})
        self.stop()
        self.server = make_server(port=0, root=self.root, db_path=self.root / 'state/briefs.db')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.assertEqual(self.request('GET', '/api/briefs/' + brief['id'])[1], {'brief': brief})
        self.assert_error(self.request('GET', '/api/briefs/' + str(uuid4())), 404)

    def test_catalog_queries_stats_decisions(self):
        response = self.request('GET', '/api/sites?q=rap&category=rap&api_status=unknown&evidence_status=full_page')
        self.assertEqual(response[0], 200)
        self.assertEqual((response[1]['total'], response[1]['filtered']), (1, 1))
        self.assertEqual(self.request('GET', '/api/sites?q=no-results')[1]['filtered'], 0)
        self.assertEqual(self.request('GET', '/api/sites/01')[1]['site']['name'], '中文 Rap')
        self.assertEqual(self.request('GET', '/api/stats')[1], {'total': 1, 'full_page': 1,
                         'by_category': {'rap': 1}, 'by_evidence': {'full_page': 1},
                         'by_api': {'unknown': 1}, 'checked_at': '2026-10-23'})
        self.assertEqual(self.request('GET', '/api/decisions')[1], {'decisions': [{'id': 'D01'}]})
        self.assert_error(self.request('GET', '/api/sites/99'), 404)
        for path in ('/api/sites/nope', '/api/sites?category=oops', '/api/sites?q=a&q=b',
                     '/api/sites?path=/etc/passwd', '/api/briefs/no-uuid', '/bad%XX'):
            self.assert_error(self.request('GET', path), 400)

    def test_bad_json_fields_mime_and_body_limit(self):
        for raw in (b'{bad', b'[]', b'{"topic":"one","topic":"two"}',
                    b'{"topic":NaN}', b'{"topic":"\xff"}', b'{"topic":"\\ud800"}'):
            self.assert_error(self.request('POST', '/api/briefs', raw=raw), 400, 'INVALID_JSON')
        self.assert_error(self.request('POST', '/api/briefs', {'topic': 'x', 'quality': '4k'}), 400, 'INVALID_INPUT')
        self.assert_error(self.request('POST', '/api/briefs', {'topic': 'x', 'file': '/tmp/photo'}), 400)
        self.assert_error(self.request('POST', '/api/briefs', raw=b'{}', headers={'Content-Type': 'text/plain'}), 415)
        self.assert_error(self.request('POST', '/api/briefs', raw=b'{}', headers={'Content-Length': str(MAX_BODY_BYTES + 1)}), 413)
        self.assert_error(self.request('POST', '/api/briefs', raw=b'{}', headers={'Content-Length': '-1'}), 400)
        self.assert_error(self.request('POST', '/api/briefs', raw=b'{}', headers={'Transfer-Encoding': 'chunked'}), 400)
        self.assert_error(self.request('PUT', '/api/briefs', {'topic': 'x'}), 405)

    def test_static_files_confined_to_web_no_cors(self):
        status, content, headers = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('工作台', content.decode('utf-8'))
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.request('HEAD', '/')[1], b'')
        for path in ('/../evidence.txt', '/%2e%2e/evidence.txt', '/.git/config', '/%2egit/config',
                     '/.env', '/escape.txt', '/alias.txt'):
            self.assert_error(self.request('GET', path), 403)
        for path in ('/research/sites/01.json', '/docs/decisions.json', '/missing', '/api/missing'):
            self.assert_error(self.request('GET', path), 404)

    def test_optional_modules_unavailable_are_honest_503(self):
        with patch('rap_workbench.server._module', side_effect=HTTPProblem(503, 'MODULE_UNAVAILABLE', 'Not installed')):
            self.assert_error(self.request('POST', '/api/quote', {'duration_seconds': 12}), 503, 'MODULE_UNAVAILABLE')
            self.assert_error(self.request('POST', '/api/jobs', {'mode': 'provider_render'}), 503, 'MODULE_UNAVAILABLE')
            self.assert_error(self.request('GET', '/api/report?format=csv'), 503, 'MODULE_UNAVAILABLE')

    def test_optional_module_wire_adapters(self):
        class IdempotencyConflict(ValueError):
            pass
        class ProviderUnavailable(RuntimeError):
            pass
        identifier = str(uuid4())
        job = {'id': identifier, 'status': 'completed', 'kind': 'brief_preview',
               'result': {'storyboard': [], 'parameters': {}, 'is_generated_video': False}}
        class JobStore:
            def __init__(self, path):
                self.keys = {}
            def create(self, payload, key):
                if payload['mode'] == 'provider_render':
                    raise ProviderUnavailable('No adapter configured')
                if key in self.keys and self.keys[key] != payload:
                    raise IdempotencyConflict('Different payload for the same key')
                created = key not in self.keys
                self.keys[key] = payload
                return job, created
            def get(self, key):
                return job if key == identifier else None
        modules = {'jobs': types.SimpleNamespace(JobStore=JobStore, IdempotencyConflict=IdempotencyConflict,
                                                ProviderUnavailable=ProviderUnavailable),
                   'quotes': types.SimpleNamespace(quote=lambda payload: {'estimate': None, 'is_vendor_quote': False}),
                   'exports': types.SimpleNamespace(export_json=lambda sites: '[]', export_csv=lambda sites: 'id\n01\n',
                                                    export_markdown=lambda sites, decisions: '# Research\nD01')}
        with patch('rap_workbench.server._module', side_effect=lambda name: modules[name]):
            payload = {'mode': 'brief_preview', 'brief': {'topic': 'test'}}
            self.assertEqual(self.request('POST', '/api/jobs', payload, headers={'Idempotency-Key': 'one'})[0], 201)
            self.assertEqual(self.request('POST', '/api/jobs', payload, headers={'Idempotency-Key': 'one'})[0], 200)
            self.assertEqual(self.request('GET', '/api/jobs/' + identifier)[1], {'job': job})
            self.assert_error(self.request('POST', '/api/jobs', {'mode': 'brief_preview', 'brief': {'topic': 'other'}},
                                           headers={'Idempotency-Key': 'one'}), 409, 'IDEMPOTENCY_CONFLICT')
            self.assert_error(self.request('POST', '/api/jobs', {'mode': 'provider_render'}), 503, 'PROVIDER_UNAVAILABLE')
            self.assert_error(self.request('POST', '/api/jobs', dict(payload, idempotency_key='two'),
                                           headers={'Idempotency-Key': 'one'}), 400)
            self.assertFalse(self.request('POST', '/api/quote', {'duration_seconds': 12})[1]['quote']['is_vendor_quote'])
            for fmt, mime in [('json', 'application/json'), ('csv', 'text/csv'), ('markdown', 'text/markdown')]:
                result = self.request('GET', '/api/report?format=' + fmt)
                self.assertEqual(result[0], 200)
                self.assertIn(mime, result[2]['Content-Type'])
                self.assertIn('attachment;', result[2]['Content-Disposition'])
            self.assert_error(self.request('GET', '/api/report?format=html'), 400)


if __name__ == '__main__':
    unittest.main()
