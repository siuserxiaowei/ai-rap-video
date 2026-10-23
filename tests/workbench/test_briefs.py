from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from uuid import UUID, uuid4

from rap_workbench.briefs import BriefStore, validate_brief


class BriefTests(unittest.TestCase):
    def test_defaults_are_normalized_without_mutating_input(self):
        payload = {'topic': '  中文生日祝福  '}
        result = validate_brief(payload)
        self.assertEqual(result, {'topic': '中文生日祝福', 'mode': 'solo', 'stage': 'studio',
                                  'duration_seconds': 12, 'aspect_ratio': '9:16', 'quality': '720p',
                                  'lyrics': '', 'language': 'zh'})
        self.assertEqual(payload, {'topic': '  中文生日祝福  '})

    def test_invalid_fields_rejected(self):
        invalid = [None, [], {}, {'topic': ''}, {'topic': ' '}, {'topic': 'x' * 241},
                   {'topic': True}, {'topic': '\ud800'}, {'topic': 'hi', 'path': '/tmp/x'}]
        for field, values in {'mode': ['trio', None, []], 'stage': ['hotel', 1],
                              'duration_seconds': [True, 12.0, '12', 0, 30],
                              'aspect_ratio': ['2:3', None], 'quality': ['4k', 720],
                              'language': ['fr', None], 'lyrics': [None, [], 'x' * 4001]}.items():
            invalid.extend({'topic': 'hi', field: value} for value in values)
        for payload in invalid:
            with self.subTest(payload=repr(payload)[:100]):
                with self.assertRaises(ValueError):
                    validate_brief(payload)

    def test_all_supported_options_and_boundaries(self):
        result = validate_brief({'topic': '中' * 240, 'mode': 'duo', 'stage': 'rooftop',
                                 'duration_seconds': 15, 'aspect_ratio': '16:9', 'quality': '1080p',
                                 'lyrics': '词' * 4000, 'language': 'en'})
        self.assertEqual(len(result['lyrics']), 4000)
        for duration in (10, 12, 15):
            self.assertEqual(validate_brief({'topic': 'test', 'duration_seconds': duration})['duration_seconds'], duration)

    def test_sqlite_reopen_roundtrip_and_unknown_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'briefs.sqlite3'
            store = BriefStore(path)
            record = store.create({'topic': "中文 ' ); DROP TABLE briefs; --", 'lyrics': '第一行\n第二行'})
            UUID(record['id'])
            self.assertTrue(record['created_at'].endswith('Z'))
            reopened = BriefStore(path)
            self.assertEqual(reopened.get(record['id']), record)
            self.assertEqual(reopened.list(), [record])
            self.assertIsNone(reopened.get(str(uuid4())))
            with self.assertRaisesRegex(ValueError, 'UUID'):
                reopened.get('../../anything')
            with self.assertRaises(ValueError):
                store.create({'topic': 'bad', 'id': str(uuid4())})
            self.assertEqual(len(reopened.list()), 1)

    def test_threaded_creates_are_durable_and_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BriefStore(Path(directory) / 'briefs.db')
            with ThreadPoolExecutor(max_workers=4) as executor:
                records = list(executor.map(lambda index: store.create({'topic': str(index)}), range(12)))
            self.assertEqual(len({record['id'] for record in records}), 12)
            self.assertEqual(len(BriefStore(store.path).list()), 12)


if __name__ == '__main__':
    unittest.main()
