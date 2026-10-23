from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from rap_workbench.provider_journal import IdempotencyConflict, SubmissionStore


class SubmissionJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'private' / 'submissions.sqlite3'
        self.store = SubmissionStore(self.path)
        self.payload = {'model': 'sync-3', 'input': [
            {'type': 'image', 'url': 'https://media.example/photo.png?sig=PRIVATE-input-123'},
            {'type': 'audio', 'url': 'https://media.example/audio.wav?sig=PRIVATE-audio-456'}],
            'outputFileName': 'rap-demo'}

    @staticmethod
    def snapshot(status, output_url=None, remote_id='Gen-1', error_code=None):
        return {'id': remote_id, 'status': status, 'output_url': output_url,
                'output_available': status == 'COMPLETED' and output_url is not None,
                'error_code': error_code}

    def prepare(self, key='action-one'):
        return self.store.prepare(key, self.payload)[0]

    def test_restart_exact_retry_private_payload_and_permissions(self):
        original = copy.deepcopy(self.payload)
        record, created = self.store.prepare('Action_case-1', self.payload)
        self.assertTrue(created)
        self.assertEqual(record['state'], 'READY')
        self.assertEqual(set(record), {'id', 'created_at', 'updated_at', 'idempotency_key',
                                     'payload_digest', 'state', 'remote_id', 'output_url',
                                     'output_available', 'revision', 'last_error_code'})
        canonical = json.dumps(original, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(record['payload_digest'], hashlib.sha256(canonical).hexdigest())
        self.payload['input'][0]['url'] = 'https://changed.example/media'
        retry = SubmissionStore(self.path).payload_for_retry(record['id'])
        self.assertEqual(retry, original)
        self.assertEqual(list(retry), list(original))
        retry['input'].reverse()
        self.assertEqual(self.store.payload_for_retry(record['id']), original)
        self.assertEqual(SubmissionStore(self.path).get(record['id']), record)
        self.assertEqual(self.store.list(), [record])
        public = json.dumps([record, self.store.list(), self.store.events(record['id'])])
        for secret in ('PRIVATE-input-123', 'PRIVATE-audio-456', 'media.example', 'outputFileName'):
            self.assertNotIn(secret, public)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.path.parent).st_mode & 0o777, 0o700)
        with sqlite3.connect(str(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT payload_json FROM provider_submissions').fetchone()[0],
                             json.dumps(original, ensure_ascii=False, separators=(',', ':')))

    def test_canonical_object_order_but_array_or_signed_url_changes_conflict(self):
        record = self.prepare()
        reordered = {'outputFileName': self.payload['outputFileName'], 'input': [
            {'url': item['url'], 'type': item['type']} for item in self.payload['input']], 'model': 'sync-3'}
        self.assertEqual(self.store.prepare('action-one', reordered), (record, False))
        self.assertEqual(len(self.store.events(record['id'])), 1)
        changes = []
        reversed_inputs = copy.deepcopy(self.payload)
        reversed_inputs['input'].reverse()
        changes.append(reversed_inputs)
        signed_url = copy.deepcopy(self.payload)
        signed_url['input'][0]['url'] += '&renewed=1'
        changes.append(signed_url)
        for changed in changes:
            with self.assertRaises(IdempotencyConflict) as caught:
                SubmissionStore(self.path).prepare('action-one', changed)
            self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(self.store.get(record['id']), record)
        self.assertTrue(self.store.prepare('ACTION-ONE', self.payload)[1])

    def test_concurrent_independent_instances_create_one_action_and_one_submitting_event(self):
        barrier = threading.Barrier(12)
        def worker(_):
            store = SubmissionStore(self.path)
            barrier.wait(timeout=10)
            record, created = store.prepare('concurrent', self.payload)
            return store.mark_submitting(record['id']), created
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(12)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({record['id'] for record, _ in results}), 1)
        self.assertEqual(len(self.store.list()), 1)
        record = results[0][0]
        self.assertEqual(record['state'], 'SUBMITTING')
        self.assertEqual([e['kind'] for e in self.store.events(record['id'])], ['prepared', 'submitting'])

    def test_acceptance_progress_stale_order_output_enrichment_and_terminal_preservation(self):
        record = self.prepare()
        local_id = record['id']
        self.store.mark_submitting(local_id)
        pending = self.store.record_acceptance(local_id, self.snapshot('PENDING'))
        self.assertEqual((pending['state'], pending['remote_id']), ('PENDING', 'Gen-1'))
        processing = self.store.apply_snapshot(local_id, self.snapshot('PROCESSING'))
        stale = self.store.apply_snapshot(local_id, self.snapshot('PENDING'))
        self.assertEqual(stale['state'], processing['state'])
        missing = self.store.apply_snapshot(local_id, self.snapshot('COMPLETED'))
        self.assertEqual((missing['state'], missing['output_url'], missing['output_available']),
                         ('COMPLETED', None, False))
        output = 'https://cdn.example/output.mp4?sig=PRIVATE-output-789'
        complete = self.store.apply_snapshot(local_id, self.snapshot('COMPLETED', output))
        self.assertTrue(complete['output_available'])
        self.assertEqual(complete['output_url'], output)
        sparse = self.store.apply_snapshot(local_id, self.snapshot('COMPLETED'))
        self.assertEqual((sparse['output_url'], sparse['output_available']), (output, True))
        for status in ('PENDING', 'PROCESSING', 'FAILED', 'REJECTED'):
            latest = self.store.apply_snapshot(local_id, self.snapshot(status))
            self.assertEqual((latest['state'], latest['output_url'], latest['output_available']),
                             ('COMPLETED', output, True))
        self.assertEqual(self.store.mark_submitting(local_id), latest)
        self.assertNotIn(output, json.dumps(self.store.events(local_id)))
        self.assertNotIn('PRIVATE', json.dumps(self.store.events(local_id)))
        events = self.store.events(local_id)
        self.assertEqual([e['revision'] for e in events], list(range(1, latest['revision'] + 1)))
        self.assertEqual(SubmissionStore(self.path).get(local_id), latest)

    def test_unknown_and_observation_error_do_not_infer_failure_or_reset_known_state(self):
        record = self.prepare()
        local_id = record['id']
        unknown = self.store.record_submission_unknown(local_id, 'IDEMPOTENCY_OUTCOME_UNKNOWN', 'remote-ABC')
        self.assertEqual((unknown['state'], unknown['remote_id']), ('SUBMISSION_UNKNOWN', 'remote-ABC'))
        self.assertEqual(self.store.mark_submitting(local_id), unknown)
        diagnostic = self.store.record_observation_error(local_id, 'HTTP_404')
        self.assertEqual(diagnostic['state'], 'SUBMISSION_UNKNOWN')
        self.assertEqual(diagnostic['idempotency_key'], record['idempotency_key'])
        self.assertEqual(self.store.payload_for_retry(local_id), self.payload)
        self.assertEqual(self.store.prepare(record['idempotency_key'], self.payload), (diagnostic, False))
        self.store.record_acceptance(local_id, self.snapshot('PROCESSING', remote_id='remote-ABC'))
        known = self.store.record_submission_unknown(local_id, 'TIMEOUT')
        self.assertEqual((known['state'], known['remote_id']), ('PROCESSING', 'remote-ABC'))
        for status in ('FAILED', 'REJECTED'):
            terminal = self.prepare('terminal-' + status)
            self.store.record_acceptance(terminal['id'], self.snapshot(status, error_code='generation_failed'))
            errored = self.store.record_observation_error(terminal['id'], 'HTTP_503')
            self.assertEqual((errored['state'], errored['last_error_code']), (status, 'HTTP_503'))
            self.assertEqual(self.store.record_submission_unknown(terminal['id'], 'TIMEOUT')['state'], status)
            self.assertEqual(self.store.apply_snapshot(terminal['id'], self.snapshot('COMPLETED'))['state'], status)

    def test_wrong_remote_ids_unknown_states_and_malformed_snapshots_are_atomic(self):
        record = self.prepare()
        local_id = record['id']
        baseline = self.store.record_acceptance(local_id, self.snapshot('PENDING'))
        invalid = [self.snapshot('ALIEN'), self.snapshot('pending'), self.snapshot('COMPLETED', remote_id='../secret'),
                   self.snapshot('PROCESSING', remote_id='Other-ID'), {'id': 'Gen-1', 'status': []},
                   dict(self.snapshot('COMPLETED'), output_available=True),
                   dict(self.snapshot('PENDING'), output_available=0),
                   dict(self.snapshot('FAILED'), error_code='https://secret.example/?sig=PRIVATE'),
                   dict(self.snapshot('PENDING'), raw_message='PRIVATE')]
        for snapshot in invalid:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(ValueError) as caught:
                    self.store.apply_snapshot(local_id, snapshot)
                self.assertNotIn('PRIVATE', str(caught.exception))
                self.assertEqual(self.store.get(local_id), baseline)
        with self.assertRaises(ValueError):
            self.store.record_submission_unknown(local_id, 'TIMEOUT', 'Other-ID')
        self.assertEqual(self.store.get(local_id), baseline)
        self.assertEqual(len(self.store.events(local_id)), 2)

    def test_output_urls_are_independently_validated_without_exposing_input(self):
        record = self.prepare()
        bad_urls = ['http://cdn.example/a.mp4', 'https://user:PRIVATE@cdn.example/a',
                    'https://127.0.0.1/a', 'https://[::1]/a', 'https://10.1.2.3/a',
                    'https://169.254.169.254/a', 'https://0x7f.0.0.1/a',
                    'https://localhost/a', 'https://machine.local/a',
                    'https://cdn.example:bad/a', 'https://cdn.example/a\nPRIVATE',
                    'https://cdn.example/a#PRIVATE', 'file:///PRIVATE', '', 1]
        for output in bad_urls:
            with self.subTest(output=output):
                with self.assertRaises(ValueError) as caught:
                    self.store.record_acceptance(record['id'], self.snapshot('COMPLETED', output))
                self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(self.store.get(record['id']), record)

    def test_incomplete_output_reference_cannot_become_completed_download_claim(self):
        record = self.prepare()
        pending = self.store.record_acceptance(record['id'], self.snapshot('PENDING', 'https://cdn.example/preview'))
        self.assertFalse(pending['output_available'])
        completed = self.store.apply_snapshot(record['id'], self.snapshot('COMPLETED'))
        self.assertFalse(completed['output_available'])
        self.assertIsNone(completed['output_url'])

    def test_keys_payloads_diagnostics_local_ids_and_missing_records(self):
        for key in ('', 'x' * 129, 'with space', 'bad/key', 'bad\nheader', None, 3):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.prepare(key, self.payload)
        for payload in ([], None, {1: 'PRIVATE'}, {'x': float('nan')}, {'x': float('inf')},
                        {'x': '\ud800'}, {'x': b'PRIVATE'}, {'x': ('tuple',)}, {'x': 'x' * (1024 * 1024)}):
            with self.assertRaises(ValueError):
                self.store.prepare('invalid-payload', payload)
        self.assertEqual(self.store.list(), [])
        record = self.prepare()
        for bad_code in ('PRIVATE human message', 'https://secret.example', 'x' * 129, [], 1):
            with self.assertRaises(ValueError):
                self.store.record_observation_error(record['id'], bad_code)
        self.assertEqual(self.store.get(record['id']), record)
        for invalid_id in ('../anything', 'not-a-uuid', str(uuid4()).upper(), None):
            with self.assertRaises(ValueError):
                self.store.get(invalid_id)
        absent = str(uuid4())
        self.assertIsNone(self.store.get(absent))
        for operation in (self.store.events, self.store.payload_for_retry, self.store.mark_submitting):
            with self.assertRaises(KeyError):
                operation(absent)

    def test_local_key_retention_does_not_delete_old_or_unresolved_actions(self):
        record = self.prepare()
        with sqlite3.connect(str(self.path)) as connection:
            row = json.loads(connection.execute('SELECT record_json FROM provider_submissions').fetchone()[0])
            row['created_at'] = '2000-01-01T00:00:00Z'
            connection.execute('UPDATE provider_submissions SET record_json=?', (json.dumps(row),))
        reopened = SubmissionStore(self.path)
        self.assertEqual(reopened.prepare('action-one', self.payload), (row, False))
        self.assertEqual(reopened.record_submission_unknown(record['id'], 'TIMEOUT')['state'], 'SUBMISSION_UNKNOWN')
        self.assertEqual(len(SubmissionStore(self.path).list()), 1)


if __name__ == '__main__':
    unittest.main()
