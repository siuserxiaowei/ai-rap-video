import copy
import csv
from datetime import datetime
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from rap_workbench.catalog import load_sites
from rap_workbench.exports import export_csv, export_json, export_markdown
from rap_workbench.server import make_server

ROOT = Path(__file__).resolve().parents[2]


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = load_sites(ROOT)
        cls.decisions = json.loads((ROOT / 'docs/decisions.json').read_text(encoding='utf-8'))

    def test_json_preserves_all_original_records_and_sources(self):
        original = copy.deepcopy(self.sites)
        result = json.loads(export_json(self.sites).encode('utf-8').decode('utf-8'))
        self.assertEqual(len(result['sites']), 46)
        self.assertEqual(result['sites'], original)
        self.assertEqual(self.sites, original)
        self.assertTrue(datetime.fromisoformat(result['generated_at']).tzinfo)
        self.assertIn('未', result['method'])
        self.assertTrue(result['limitations'])

    def test_csv_all_rows_nested_fields_and_sources_roundtrip(self):
        rows = list(csv.DictReader(io.StringIO(export_csv(self.sites))))
        self.assertEqual(len(rows), 46)
        for row, site in zip(rows, self.sites):
            self.assertEqual(row['id'], site['id'])
            self.assertEqual(row['checked_at'], site['checked_at'])
            self.assertEqual(row['evidence_status'], site['evidence_status'])
            self.assertEqual(row['api_status'], site['api']['status'])
            self.assertEqual(row['free_tier'], site['pricing']['free_tier'])
            self.assertEqual(json.loads(row['pricing_plans']), site['pricing']['plans'])
            self.assertEqual(json.loads(row['sources']), site['sources'])
            self.assertEqual(json.loads(row['source_urls']), [s['url'] for s in site['sources']])
            self.assertEqual(json.loads(row['limitations']), site['limitations'])

    def test_csv_special_characters_and_formula_neutralization(self):
        special = '中文,含"引号"\n第二行'
        values = [special, '=1+1', '+SUM(A1)', '-42', '@IMPORT', '  =1', '\t+1', '\n@x', '\r-x', '\u00a0=1']
        for value in values:
            with self.subTest(value=value):
                row = list(csv.DictReader(io.StringIO(export_csv([{'name': value}]))))[0]
                self.assertEqual(row['name'], value if value == special else "'" + value)

    def test_markdown_complete_sites_decisions_and_api_unknown_boundary(self):
        report = export_markdown(self.sites, self.decisions)
        self.assertEqual(len(self.decisions), 50)
        self.assertEqual(report.count('\n### '), 96)
        for site in self.sites:
            self.assertIn(site['url'], report)
            self.assertIn(site['checked_at'], report)
            for source in site['sources']:
                self.assertIn(source['url'], report)
        for decision in self.decisions:
            self.assertIn(decision['id'], report)
        self.assertIn('不能推断为不提供 API', report)
        self.assertIn('未验证结账', report)
        self.assertIn('供应商宣称', report)
        unknown = {'id': '99', 'api': {'status': 'unknown', 'summary': '尚未核查', 'url': None}}
        self.assertEqual(json.loads(export_json([unknown]))['sites'], [unknown])
        self.assertIn('unknown', export_markdown([unknown]))
        self.assertIn('未记录', export_markdown([unknown]))

    def test_empty_exports(self):
        self.assertEqual(json.loads(export_json([]))['sites'], [])
        self.assertEqual(list(csv.DictReader(io.StringIO(export_csv([])))), [])
        self.assertIn('0 个站点', export_markdown([]))
        self.assertIn('未提供决策记录', export_markdown([]))

    def test_real_http_all_export_mime_attachment_data(self):
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(port=0, root=ROOT, db_path=Path(directory) / 'briefs.db')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for fmt, mime, suffix in [('json', 'application/json', 'json'), ('csv', 'text/csv', 'csv'), ('markdown', 'text/markdown', 'md')]:
                    with self.subTest(format=fmt):
                        connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=3)
                        try:
                            connection.request('GET', '/api/report?format=' + fmt)
                            response = connection.getresponse()
                            raw = response.read()
                            body = raw.decode('utf-8')
                            self.assertEqual(response.status, 200, body)
                            self.assertEqual(response.getheader('Content-Type'), mime + '; charset=utf-8')
                            self.assertEqual(response.getheader('Content-Disposition'), 'attachment; filename="rap-research.' + suffix + '"')
                            self.assertEqual(int(response.getheader('Content-Length')), len(raw))
                            if fmt == 'json':
                                self.assertEqual(json.loads(body)['sites'], self.sites)
                            elif fmt == 'csv':
                                self.assertEqual(len(list(csv.DictReader(io.StringIO(body)))), len(self.sites))
                            else:
                                self.assertIn('产品决策（50 项）', body)
                                self.assertIn(self.sites[-1]['url'], body)
                        finally:
                            connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
