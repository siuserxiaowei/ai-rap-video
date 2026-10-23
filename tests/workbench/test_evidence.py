import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('collector', Path(__file__).resolve().parents[2] / 'scripts/collect_candidate_evidence.py')
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class EvidenceTests(unittest.TestCase):
    def test_response_classification(self):
        product = 'Title: Rap Studio\n\n# Create your music video\n' + 'Generate rap. ' * 100
        self.assertEqual(collector.classify_content(product), 'readable')
        self.assertEqual(collector.classify_content(product + '\n## How do I sign in?'), 'readable')
        for body in ('Title: 404 Not Found\n' + 'x' * 1000,
                     'Title: Just a moment...\n' + 'x' * 1000,
                     'Title: Example\nWarning: Target URL returned error 403', 'Forbidden'):
            self.assertEqual(collector.classify_content(body), 'error_page')
        self.assertEqual(collector.classify_content('Title: Sign in to Rap Studio\n' + 'x' * 1200), 'login_required')
        self.assertEqual(collector.classify_content(product, http_status=503), 'error_page')
        self.assertEqual(collector.classify_content(product, returncode=28), 'inaccessible')
        self.assertEqual(collector.classify_content(''), 'inaccessible')
        self.assertEqual(collector.classify_content('Login required'), 'login_required')
        self.assertEqual(collector.classify_content('Title: Rap Studio\nShort body'), 'needs_review')

    def test_selection_validation(self):
        sites = [dict(id='41', url='https://example.com/'), dict(id='42', url='https://other.example/rap')]
        self.assertEqual(collector.parse_ids('41, 42'), ['41', '42'])
        self.assertEqual(collector.select_candidates(sites, ['42']), [sites[1]])
        for ids in ('', '4', '41,', '41,41', '../41'):
            with self.assertRaises(argparse.ArgumentTypeError):
                collector.parse_ids(ids)
        with self.assertRaises(ValueError):
            collector.validate_candidate(dict(id=41, url='https://example.com/'))
        with self.assertRaisesRegex(ValueError, 'unknown candidate'):
            collector.select_candidates(sites, ['49'])
        for url in ('file:///etc/passwd', 'https://user:secret@example.com/', 'https://127.0.0.1/',
                    'http://localhost/', 'https://x.local/', 'https://example.com/#a', 'https://example.com:bad/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                collector.validate_candidate(dict(id='41', url=url))

    def test_incremental_cli_preserves_index_and_collects_only_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'research').mkdir()
            sites = [dict(id='41', url='https://example.com/'), dict(id='42', url='https://other.example/')]
            (root / 'research/candidates.json').write_text(json.dumps(sites))
            output = root / 'snapshots'
            output.mkdir()
            (output / 'index.json').write_text(json.dumps([dict(id='01', sha256='old'), dict(id='41', sha256='replace')]))
            with mock.patch.object(collector, 'ROOT', root), mock.patch.object(collector, 'collect', side_effect=lambda site, dest: {**site, 'sha256': 'new'}) as collect:
                collector.main(['--ids', '42', '--output-dir', str(output)])
            self.assertEqual(collect.call_count, 1)
            self.assertEqual(collect.call_args.args[0]['id'], '42')
            self.assertEqual(json.loads((output / 'index.json').read_text()),
                             [dict(id='01', sha256='old'), dict(id='41', sha256='replace'), {**sites[1], 'sha256': 'new'}])

    def test_collect_keeps_metadata_and_error_body(self):
        with tempfile.TemporaryDirectory() as directory:
            result = mock.Mock(stdout='Title: 404 Not Found\nMissing\n__EVIDENCE_HTTP_STATUS__:404', stderr='transport detail', returncode=0)
            with mock.patch.object(collector.subprocess, 'run', return_value=result), contextlib.redirect_stdout(io.StringIO()):
                meta = collector.collect(dict(id='41', url='https://example.com/'), Path(directory))
            self.assertEqual(meta['status'], 'error_page')
            self.assertEqual(meta['http_status'], 404)
            self.assertEqual(meta['error'], 'transport detail')
            self.assertEqual(len(meta['sha256']), 64)
            self.assertIn('+00:00', meta['fetched_at'])
            self.assertEqual(Path(meta['local_path']).read_text(), 'Title: 404 Not Found\nMissing')


if __name__ == '__main__':
    unittest.main()
