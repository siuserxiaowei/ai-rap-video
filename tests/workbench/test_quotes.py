import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from rap_workbench.quotes import quote
from rap_workbench.server import make_server


def parameters(**changes):
    return dict({'duration_seconds': 12, 'quality': '720p', 'aspect_ratio': '9:16'}, **changes)


class QuoteTests(unittest.TestCase):
    def test_all_exact_official_packages(self):
        for duration, quality, amount, name in (
                (8, '480p', 2.99, 'Lite'), (12, '720p', 3.99, 'HD'), (15, '720p', 5.99, 'Pro')):
            with self.subTest(plan=name):
                result = quote(parameters(duration_seconds=duration, quality=quality, site_id='03'))
                self.assertEqual(result['estimate'], amount)
                self.assertGreater(result['estimate'], 0)
                self.assertEqual(result['currency'], 'USD')
                self.assertEqual(result['source_url'], 'https://rapreel.com/pricing')
                self.assertEqual(result['checked_at'], '2026-10-23')
                self.assertEqual(result['matched_spec']['plan'], name)
                self.assertEqual(result['matched_spec']['duration_seconds'], duration)
                self.assertEqual(result['matched_spec']['quality'], quality)
                self.assertEqual(result['matched_spec']['orientation'], 'vertical')
                self.assertEqual(result['matched_spec']['billing_period'], 'per_video')
                self.assertFalse(result['is_vendor_quote'])
                self.assertEqual(result['quote_kind'], 'competitor_reference')
                self.assertIn('历史官网', result['basis'])
                self.assertIn('推断', result['basis'])
                self.assertTrue(any('非实时' in note and '非结账' in note for note in result['assumptions']))

    def test_no_interpolation_or_unverified_spec(self):
        for changes in ({'duration_seconds': 10}, {'duration_seconds': 8}, {'duration_seconds': 13},
                        {'duration_seconds': 15, 'quality': '480p'}, {'quality': '1080p'},
                        {'quality': '4k'}, {'aspect_ratio': '1:1'}, {'aspect_ratio': '16:9'},
                        {'aspect_ratio': '4:5'}, {'site_id': '01'}, {'site_id': '06'},
                        {'site_id': '12'}, {'site_id': 'unknown'}):
            with self.subTest(changes=changes):
                result = quote(parameters(**changes))
                self.assertIsNone(result['estimate'])
                self.assertIsNone(result['matched_spec'])
                self.assertIn('无可比报价', result['basis'])
                self.assertIn('不代表免费或零价', result['basis'])
                self.assertFalse(result['is_vendor_quote'])
                if changes.get('site_id', '03') != '03':
                    self.assertIsNone(result['currency'])
                    self.assertIsNone(result['source_url'])

    def test_strict_fields_and_types(self):
        for payload in (None, [], '12', {}, {'duration_seconds': 12},
                        parameters(duration_seconds=True), parameters(duration_seconds=False),
                        parameters(duration_seconds=12.0), parameters(duration_seconds='12'),
                        parameters(duration_seconds=None), parameters(duration_seconds=0),
                        parameters(duration_seconds=-1), parameters(duration_seconds=float('nan')),
                        parameters(duration_seconds=float('inf')), parameters(quality=None),
                        parameters(quality=720), parameters(quality=[]), parameters(quality=''),
                        parameters(aspect_ratio=None), parameters(aspect_ratio=9 / 16),
                        parameters(site_id=3), parameters(site_id=None), parameters(site_id=True),
                        parameters(site_id=''), parameters(path='/tmp/private'),
                        parameters(currency='USD'), parameters(estimate=0),
                        {**parameters(), 1: 'unknown'}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                quote(payload)

    def test_json_roundtrip_and_independent_results(self):
        payload = parameters()
        original = payload.copy()
        result = quote(payload)
        self.assertEqual(payload, original)
        self.assertEqual(json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False)), result)
        unmatched = quote(parameters(duration_seconds=10))
        self.assertEqual(json.loads(json.dumps(unmatched, allow_nan=False)), unmatched)
        result['assumptions'].clear()
        self.assertTrue(quote(payload)['assumptions'])
        notes = ' '.join(quote(payload)['assumptions'])
        for disclaimer in ('credits', '不能跨站换算', '年付折月', '自建服务', '静态舞台预览', '未声明精确 9:16'):
            self.assertIn(disclaimer, notes)


class QuoteHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[2]
        cls.server = make_server(port=0, root=root, db_path=Path(cls.temp.name) / 'briefs.sqlite3')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def post(self, payload):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        try:
            connection.request('POST', '/api/quote', body=json.dumps(payload).encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_real_server_packages_and_no_match(self):
        for duration, quality, amount in ((8, '480p', 2.99), (12, '720p', 3.99), (15, '720p', 5.99)):
            status, body = self.post(parameters(duration_seconds=duration, quality=quality))
            self.assertEqual(status, 200)
            self.assertEqual(body['quote']['estimate'], amount)
            self.assertFalse(body['quote']['is_vendor_quote'])
        for changes in ({'duration_seconds': 10}, {'aspect_ratio': '16:9'}, {'site_id': '01'}):
            status, body = self.post(parameters(**changes))
            self.assertEqual(status, 200)
            self.assertIsNone(body['quote']['estimate'])

    def test_real_server_invalid_input_is_400(self):
        for payload in (parameters(duration_seconds=True), parameters(duration_seconds=12.0),
                        parameters(quality=None), parameters(unexpected=True), {}):
            with self.subTest(payload=payload):
                status, body = self.post(payload)
                self.assertEqual(status, 400)
                self.assertEqual(body['error']['code'], 'INVALID_INPUT')


if __name__ == '__main__':
    unittest.main()
