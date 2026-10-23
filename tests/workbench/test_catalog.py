import copy
import json
from pathlib import Path
import tempfile
import unittest

from rap_workbench.catalog import (CatalogValidationError, filter_sites,
                                   load_sites, stats, validate_site)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'research/sites').mkdir(parents=True)
        (self.root / 'research/evidence').mkdir()
        (self.root / 'research/evidence/home.txt').write_text(
            'Title: Example\n\nMarkdown Content:\nCreate a music video from your audio.', encoding='utf-8')
        self.site = dict(id='01', name='示例 Music', url='https://www.example.ai/tool',
                         category='rap', checked_at='2026-10-23', summary='创作说唱视频',
                         inputs=['audio'], outputs=['video'], features=['歌词'],
                         pricing=dict(summary='Paid credits', free_tier='Unknown',
                                      plans=[], source_url=''),
                         api=dict(status='unknown', summary='Not verified', url=''),
                         limitations=['No generation tested'], best_for='音乐创作',
                         evidence_status='full_page', observations=['推断：适合演示'],
                         sources=[dict(url='https://example.ai', title='Example', kind='official',
                                       local_path='research/evidence/home.txt', supports=['Product'])])

    def write(self, record, filename=None):
        (self.root / 'research/sites' / (filename or (record['id'] + '.json'))).write_text(
            json.dumps(record, ensure_ascii=False), encoding='utf-8')

    def test_load_filter_and_json_stats(self):
        self.write(self.site)
        sites = load_sites(self.root)
        self.assertEqual(filter_sites(sites, 'music', 'rap', 'unknown', 'full_page'), sites)
        self.assertEqual(filter_sites(sites, '说唱'), sites)
        self.assertEqual(filter_sites(sites, api_status='not_found'), [])
        counts = stats(sites)
        self.assertEqual(counts, dict(total=1, full_page=1, by_category={'rap': 1},
                                     by_evidence={'full_page': 1}, by_api={'unknown': 1},
                                     checked_at='2026-10-23'))
        json.dumps(counts)
        self.assertIsNone(stats([])['checked_at'])

    def test_schema_errors_are_field_specific(self):
        changes = [('id', 1), ('checked_at', '2026-02-30'), ('category', 'other'),
                   ('inputs', 'audio'), ('sources', {}), ('summary', '')]
        for field, value in changes:
            with self.subTest(field=field):
                record = copy.deepcopy(self.site)
                record[field] = value
                with self.assertRaisesRegex(CatalogValidationError, field):
                    validate_site(record, self.root)
        record = copy.deepcopy(self.site)
        del record['pricing']
        with self.assertRaisesRegex(CatalogValidationError, 'missing required fields: pricing'):
            validate_site(record, self.root)
        self.site['api']['status'] = 'none'
        with self.assertRaisesRegex(CatalogValidationError, 'api.status'):
            validate_site(self.site, self.root)

    def test_evidence_missing_traversal_absolute_and_symlink_rejected(self):
        outside = self.root.parent / (self.root.name + '-outside.txt')
        outside.write_text('Outside', encoding='utf-8')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.root / 'research/evidence/link.txt'
        link.symlink_to(outside)
        for path in ('missing.txt', '../../outside.txt', str(outside), 'research/evidence/link.txt'):
            with self.subTest(path=path):
                record = copy.deepcopy(self.site)
                record['sources'][0]['local_path'] = path
                with self.assertRaisesRegex(CatalogValidationError, 'local_path'):
                    validate_site(record, self.root)

    def test_full_page_needs_successful_primary_source(self):
        evidence = self.root / self.site['sources'][0]['local_path']
        for content in ('', 'Title: 404: Not Found\nMarkdown Content: Error',
                        'Warning: Target URL returned error 403: Forbidden',
                        'Title: Sign in\nPlease log in'):
            with self.subTest(content=content):
                evidence.write_text(content, encoding='utf-8')
                with self.assertRaisesRegex(CatalogValidationError, 'full_page'):
                    validate_site(self.site, self.root)
        evidence.write_text('Official product details', encoding='utf-8')
        self.site['sources'][0]['kind'] = 'secondary'
        with self.assertRaisesRegex(CatalogValidationError, 'full_page'):
            validate_site(self.site, self.root)
        self.site['evidence_status'] = 'partial'
        self.assertEqual(validate_site(self.site, self.root), self.site)

    def test_duplicate_primary_domain_rejected_and_stats_deduplicated(self):
        self.write(self.site)
        second = copy.deepcopy(self.site)
        second.update(id='02', url='https://docs.example.ai/reference')
        self.write(second)
        with self.assertRaisesRegex(CatalogValidationError, 'duplicate primary domain'):
            load_sites(self.root)
        self.assertEqual(stats([self.site, second])['total'], 1)
        second['url'] = 'https://example.com'
        self.assertEqual(stats([self.site, second])['total'], 2)

    def test_loading_reports_filename_and_invalid_json(self):
        self.write(self.site, '02.json')
        with self.assertRaisesRegex(CatalogValidationError, '02.json: id'):
            load_sites(self.root)
        (self.root / 'research/sites/02.json').write_text('{bad', encoding='utf-8')
        with self.assertRaisesRegex(CatalogValidationError, '02.json'):
            load_sites(self.root)

    def test_price_numbers_and_credit_labels(self):
        self.site['pricing']['plans'] = [{'credits': '1,000 / month', 'amount': 5}]
        validate_site(self.site, self.root)
        for amount in (float('nan'), float('inf'), -1, True):
            with self.subTest(amount=amount):
                self.site['pricing']['plans'][0]['amount'] = amount
                with self.assertRaisesRegex(CatalogValidationError, 'amount'):
                    validate_site(self.site, self.root)

    def test_repository_records_validate_without_assuming_final_count(self):
        root = Path(__file__).resolve().parents[2]
        sites = load_sites(root)
        self.assertEqual(len(sites), len(list((root / 'research/sites').glob('*.json'))))
        self.assertEqual(stats(sites)['total'], len(sites))


if __name__ == '__main__':
    unittest.main()
