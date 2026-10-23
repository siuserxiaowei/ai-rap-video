"""Repository integration checks using real HTTP, SQLite and static HTML parsing.

These are deliberately not browser, visual, or keyboard interaction tests.
"""
import copy
import csv
from html.parser import HTMLParser
import http.client
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from rap_workbench.briefs import BriefStore, validate_brief
from rap_workbench.catalog import load_sites, validate_site
from rap_workbench.jobs import JobStore
from rap_workbench.server import MAX_BODY_BYTES, make_server


ROOT = Path(__file__).resolve().parents[2]


class PageParser(HTMLParser):
    """Collect static references and label ancestry without executing scripts."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
            'meta', 'param', 'source', 'track', 'wbr', 'path'}

    def __init__(self, text):
        super().__init__()
        self.nodes, self.stack, self.words = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'parents': list(self.stack), 'text': ''}
        self.nodes.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        self.words.append(value)
        for node in self.stack:
            node['text'] += value


class RepositoryEvidenceIntegrationTests(unittest.TestCase):
    def test_46_unique_primary_domains_and_real_primary_bodies(self):
        sites = load_sites(ROOT)
        self.assertEqual(len(sites), 46)
        self.assertEqual({s['id'] for s in sites}, {f'{i:02d}' for i in range(1, 47)})
        # These 46 samples use ordinary registrable domains, with no co.uk etc.
        domains = {'.'.join(urlsplit(s['url']).hostname.lower().split('.')[-2:]) for s in sites}
        self.assertEqual(len(domains), 46)
        rejected_heading = re.compile(r'^(?:title:\s*|#{1,3}\s*)(?:404|403|502|503|'
                                      r'page not found|access denied|forbidden|just a moment|'
                                      r'sign in|log in|security checkpoint)\b', re.I | re.M)
        for site in sites:
            with self.subTest(site=site['id']):
                self.assertEqual(validate_site(site, ROOT), site)
                valid_primary = []
                for source in site['sources']:
                    path = ROOT / source['local_path']
                    self.assertTrue(path.resolve().is_relative_to(ROOT.resolve()))
                    body = path.read_text(encoding='utf-8')
                    self.assertTrue(source['supports'])
                    if (source['kind'] != 'secondary' and len(body.strip()) >= 100
                            and not rejected_heading.search(body[:3000])
                            and 'Warning: Target URL returned error' not in body):
                        valid_primary.append(source)
                if site['evidence_status'] == 'full_page':
                    self.assertTrue(valid_primary, 'full_page needs a substantive non-error primary body')


class RealWorkbenchHTTPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp.name) / 'state' / 'briefs.sqlite3'
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.server = make_server(port=0, root=ROOT, db_path=cls.db_path)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    @classmethod
    def tearDownClass(cls):
        cls.stop_server()
        cls.temp.cleanup()

    def request(self, method, path, payload=None, raw=None, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else raw
        request_headers = {'Content-Type': 'application/json'} if body is not None else {}
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def json_request(self, *args, **kwargs):
        status, body, headers = self.request(*args, **kwargs)
        self.assertIn('application/json', headers['Content-Type'])
        return status, json.loads(body), headers

    def assert_error(self, result, status, code=None):
        self.assertEqual(result[0], status, result)
        self.assertEqual(set(result[1]), {'error'})
        self.assertEqual(set(result[1]['error']), {'code', 'message'})
        self.assertTrue(result[1]['error']['message'])
        if code:
            self.assertEqual(result[1]['error']['code'], code)

    def test_01_catalog_filters_stats_details_and_empty_search(self):
        status, data, headers = self.json_request('GET', '/api/sites')
        self.assertEqual((status, data['total'], data['filtered']), (200, 46, 46))
        self.assertEqual(data['sites'], load_sites(ROOT))
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        for category in ('rap', 'music_video', 'lip_sync', 'music', 'video', 'editor'):
            result = self.json_request('GET', '/api/sites?' + urlencode({'category': category}))[1]
            self.assertTrue(result['sites'])
            self.assertTrue(all(s['category'] == category for s in result['sites']))
        filtered = self.json_request('GET', '/api/sites?' + urlencode({
            'category': 'lip_sync', 'api_status': 'documented', 'evidence_status': 'full_page'}))[1]
        self.assertTrue(filtered['sites'])
        self.assertTrue(all(s['api']['status'] == 'documented' and s['category'] == 'lip_sync'
                            and s['evidence_status'] == 'full_page' for s in filtered['sites']))
        empty = self.json_request('GET', '/api/sites?q=definitely-no-such-tool-987654321')[1]
        self.assertEqual((empty['filtered'], empty['sites'], empty['total']), (0, [], 46))
        for site in data['sites']:
            self.assertEqual(self.json_request('GET', '/api/sites/' + site['id'])[1]['site'], site)
        stats = self.json_request('GET', '/api/stats')[1]
        self.assertEqual(stats['total'], 46)
        self.assertEqual(sum(stats['by_category'].values()), 46)
        self.assertEqual(stats['full_page'], sum(s['evidence_status'] == 'full_page' for s in data['sites']))
        self.assertEqual(len(self.json_request('GET', '/api/decisions')[1]['decisions']), 50)

    def test_02_brief_create_get_sqlite_reopen_and_server_restart(self):
        payload = {'topic': "  中文庆祝 '); DROP TABLE briefs; --  ", 'mode': 'duo',
                   'stage': 'rooftop', 'duration_seconds': 15, 'aspect_ratio': '16:9',
                   'quality': '1080p', 'lyrics': '第一行\n第二行', 'language': 'zh'}
        status, data, _ = self.json_request('POST', '/api/briefs', payload)
        self.assertEqual(status, 201)
        brief = data['brief']
        UUID(brief['id'])
        self.assertEqual({key: brief[key] for key in payload}, validate_brief(payload))
        self.assertEqual(self.json_request('GET', '/api/briefs/' + brief['id'])[1], data)
        self.assertIn(brief, self.json_request('GET', '/api/briefs')[1]['briefs'])
        self.assertEqual(BriefStore(self.db_path).get(brief['id']), brief)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.json_request('GET', '/api/briefs/' + brief['id'])[:2], (200, data))

    def test_03_jobs_real_idempotency_conflict_provider_and_sqlite(self):
        payload = {'mode': 'brief_preview', 'brief': {'topic': '  持久任务  ', 'mode': 'duo', 'duration_seconds': 10}}
        key = 'c49-complete-http-roundtrip'
        status, data, _ = self.json_request('POST', '/api/jobs', payload, headers={'Idempotency-Key': key})
        self.assertEqual(status, 201)
        job = data['job']
        self.assertEqual((job['kind'], job['status']), ('brief_preview', 'completed'))
        self.assertIs(job['result']['is_generated_video'], False)
        self.assertEqual(job['result']['parameters'], validate_brief(payload['brief']))
        self.assertEqual(sum(s['duration_seconds'] for s in job['result']['storyboard']), 10)
        self.assertNotRegex(json.dumps(job), r'(?i)(media_url|video_url|\.mp4)')
        replay = dict(payload, brief=validate_brief(payload['brief']))
        self.assertEqual(self.json_request('POST', '/api/jobs', replay, headers={'Idempotency-Key': key})[:2], (200, data))
        self.assertEqual(self.json_request('GET', '/api/jobs/' + job['id'])[:2], (200, data))
        self.assertEqual(JobStore(self.server.jobs_path).get(job['id']), job)
        conflict = dict(payload, brief={'topic': 'different'})
        self.assert_error(self.json_request('POST', '/api/jobs', conflict, headers={'Idempotency-Key': key}), 409, 'IDEMPOTENCY_CONFLICT')
        unavailable = dict(payload, mode='provider_render')
        self.assert_error(self.json_request('POST', '/api/jobs', unavailable, headers={'Idempotency-Key': 'c49-render'}), 503, 'PROVIDER_UNAVAILABLE')
        self.assertEqual(JobStore(self.server.jobs_path).list(), [job])

    def test_04_real_quote_is_sourced_or_explicitly_incomparable(self):
        for duration in (10, 12, 15):
            status, data, _ = self.json_request('POST', '/api/quote', {
                'duration_seconds': duration, 'quality': '720p', 'aspect_ratio': '9:16'})
            self.assertEqual(status, 200, data)
            quote = data['quote']
            self.assertIs(quote['is_vendor_quote'], False)
            for field in ('estimate', 'currency', 'basis', 'assumptions'):
                self.assertIn(field, quote)
            self.assertTrue(quote['basis'])
            self.assertTrue(quote['assumptions'])
            if quote['estimate'] is not None:
                self.assertGreater(quote['estimate'], 0)
                self.assertIn('rapreel', json.dumps(quote, ensure_ascii=False).lower())

    def test_05_all_three_downloads_keep_full_data_sources_and_boundaries(self):
        sites = load_sites(ROOT)
        decoded = {}
        for fmt, mime, suffix in (('json', 'application/json', 'json'), ('csv', 'text/csv', 'csv'),
                                  ('markdown', 'text/markdown', 'md')):
            status, raw, headers = self.request('GET', '/api/report?format=' + fmt)
            self.assertEqual(status, 200, raw[:300])
            self.assertIn(mime, headers['Content-Type'])
            self.assertIn('charset=utf-8', headers['Content-Type'].lower())
            self.assertEqual(headers['Content-Disposition'], f'attachment; filename="rap-research.{suffix}"')
            self.assertEqual(int(headers['Content-Length']), len(raw))
            decoded[fmt] = raw.decode('utf-8-sig')
            for site in sites:
                with self.subTest(format=fmt, site=site['id']):
                    self.assertIn(site['name'], decoded[fmt])
                    self.assertIn(site['url'], decoded[fmt])
                    self.assertIn(site['checked_at'], decoded[fmt])
                    for source in site['sources']:
                        self.assertIn(source['url'], decoded[fmt])
                        self.assertIn(source['local_path'], decoded[fmt])
        data = json.loads(decoded['json'])
        exported_sites = data if isinstance(data, list) else data['sites']
        self.assertEqual(exported_sites, sites)
        rows = list(csv.DictReader(io.StringIO(decoded['csv'])))
        self.assertEqual(len(rows), 46)
        self.assertEqual({r['id'] for r in rows}, {s['id'] for s in sites})
        by_id = {row['id']: row for row in rows}
        for site in sites:
            row = by_id[site['id']]
            for field in ('inputs', 'outputs', 'features', 'limitations', 'sources', 'observations'):
                self.assertEqual(json.loads(row[field]), site[field], (site['id'], field))
            self.assertEqual(json.loads(row['pricing_plans']), site['pricing']['plans'])
            for column, value in (('summary', site['summary']), ('evidence_status', site['evidence_status']),
                                  ('pricing_summary', site['pricing']['summary']),
                                  ('free_tier', site['pricing']['free_tier']),
                                  ('api_status', site['api']['status']), ('api_summary', site['api']['summary'])):
                self.assertEqual(row[column], value, (site['id'], column))
        markdown = decoded['markdown']
        for site in sites:
            self.assertIn(site['evidence_status'], markdown)
        self.assertRegex(markdown, r'(?i)(未实测|不代表|not.*test|unverified)')
        for decision in json.loads((ROOT / 'docs/decisions.json').read_text()):
            self.assertIn(str(decision['id']), markdown)

    def test_06_csv_injection_newlines_and_unicode_are_safe_without_lost_records(self):
        from rap_workbench.exports import export_csv
        sites = copy.deepcopy(load_sites(ROOT)[:7])
        hazards = ['=1+1', '+SUM(A1:A2)', '-2+3', '@SUM(1,2)', '\t=1+1', '\r=1+1', '\n=1+1']
        for site, text in zip(sites, hazards):
            site['name'] = text
            site['summary'] = text + '\n中文,"保留"'
        raw = export_csv(sites)
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(raw)))
        self.assertEqual(len(rows), 7)
        for row, hazard in zip(rows, hazards):
            self.assertTrue(row['name'].startswith("'"), repr(row['name']))
            self.assertIn(hazard, row['name'])
            self.assertIn('中文,"保留"', row['summary'])

    def test_07_invalid_inputs_and_paths_are_structured_and_do_not_write(self):
        before = len(BriefStore(self.db_path).list())
        for payload in ({}, {'topic': ''}, {'topic': 'x', 'duration_seconds': True},
                        {'topic': 'x', 'quality': '4k'}, {'topic': 'x', 'photo': '/tmp/photo'},
                        {'topic': 'x', 'lyrics': '词' * 4001}):
            self.assert_error(self.json_request('POST', '/api/briefs', payload), 400, 'INVALID_INPUT')
        for raw in (b'[]', b'{bad', b'{"topic":"x","topic":"y"}', b'{"topic":NaN}',
                    b'{"topic":"\\ud800"}', b'{"topic":"\xff"}'):
            self.assert_error(self.json_request('POST', '/api/briefs', raw=raw), 400, 'INVALID_JSON')
        self.assert_error(self.json_request('POST', '/api/briefs', raw=b'{}', headers={'Content-Type': 'text/plain'}), 415)
        self.assert_error(self.json_request('POST', '/api/briefs', raw=b'{}', headers={'Content-Length': str(MAX_BODY_BYTES + 1)}), 413)
        self.assertEqual(len(BriefStore(self.db_path).list()), before)
        for path in ('/../README.md', '/%2e%2e/README.md', '/.git/config', '/%2eenv', '/a/../../README.md'):
            self.assert_error(self.json_request('GET', path), 403)
        for path in ('/research/sites/01.json', '/docs/decisions.json', '/api/no-such-route'):
            self.assert_error(self.json_request('GET', path), 404)
        for path in ('/api/sites?category=unknown', '/api/sites?api_status=bad', '/api/sites?q=a&q=b',
                     '/api/sites?file=/etc/passwd', '/api/briefs/not-uuid', '/api/sites/999', '/bad%XX', '/bad%00'):
            self.assert_error(self.json_request('GET', path), 400)

    def test_08_actual_static_pages_and_assets_get_and_head(self):
        for path, expected_mime in (('/', 'text/html'), ('/create.html', 'text/html'),
                                    ('/app.js', 'javascript'), ('/create.js', 'javascript'),
                                    ('/styles.css', 'text/css'), ('/create.css', 'text/css')):
            with self.subTest(path=path):
                status, body, headers = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn(expected_mime, headers['Content-Type'])
                self.assertIn('utf-8', headers['Content-Type'])
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                head_status, head_body, head_headers = self.request('HEAD', path)
                self.assertEqual((head_status, head_body), (200, b''))
                self.assertEqual(int(head_headers['Content-Length']), len(body))


class StaticFrontendIntegrationTests(unittest.TestCase):
    def test_html_labels_ids_navigation_assets_and_javascript_references(self):
        for filename, script in (('index.html', 'app.js'), ('create.html', 'create.js')):
            with self.subTest(page=filename):
                page = PageParser((ROOT / 'web' / filename).read_text())
                ids = [n['attrs']['id'] for n in page.nodes if 'id' in n['attrs']]
                self.assertEqual(len(ids), len(set(ids)), 'duplicate DOM ids')
                explicit = {n['attrs']['for']: n for n in page.nodes
                            if n['tag'] == 'label' and 'for' in n['attrs']}
                for node in page.nodes:
                    attrs = node['attrs']
                    if node['tag'] in ('input', 'select', 'textarea'):
                        labels = [p for p in node['parents'] if p['tag'] == 'label']
                        labels += [explicit[attrs['id']]] if attrs.get('id') in explicit else []
                        self.assertTrue(any(label['text'].strip() for label in labels), node)
                    for attribute in ('aria-labelledby', 'aria-describedby'):
                        for target in attrs.get(attribute, '').split():
                            self.assertIn(target, ids, (attribute, target))
                    if node['tag'] == 'a' and attrs.get('href', '').startswith('#'):
                        self.assertIn(attrs['href'][1:], ids)
                    if node['tag'] in ('script', 'link'):
                        value = attrs.get('src') or attrs.get('href')
                        self.assertTrue(value and value.startswith('/'))
                        self.assertTrue((ROOT / 'web' / value.lstrip('/')).is_file())
                navlinks = {n['attrs'].get('href') for n in page.nodes if n['tag'] == 'a'
                            and any(p['tag'] == 'nav' for p in n['parents'])}
                self.assertTrue({'/', '/create.html'} <= navlinks)
                source = (ROOT / 'web' / script).read_text()
                self.assertFalse(re.search(r'\.innerHTML\s*=|insertAdjacentHTML|document\.write\(', source))
                for identifier in re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", source):
                    self.assertIn(identifier, ids, ('script DOM reference', identifier))
                check = subprocess.run(['node', '--check', str(ROOT / 'web' / script)], capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stderr)

    def test_honesty_copy_and_responsive_focus_rules_present(self):
        index = (ROOT / 'web/index.html').read_text()
        create = (ROOT / 'web/create.html').read_text()
        for text in ('“已读正文”不代表功能或授权已验证', '积分', '年付折月', '单次', '未实测'):
            self.assertIn(text, index)
        for text in ('不包含 AI 人声、口型、音轨或成片', '当前浏览器本地预览', '不是供应商实时报价', '不代表 0 元'):
            self.assertIn(text, create)
        for filename in ('styles.css', 'create.css'):
            css_text = (ROOT / 'web' / filename).read_text()
            self.assertIn('focus-visible', css_text)
            self.assertIn('prefers-reduced-motion', css_text)
            self.assertRegex(css_text, r'@media\s*\(max-width:\s*760px\)')
            self.assertIn('44px', css_text)


if __name__ == '__main__':
    unittest.main()
