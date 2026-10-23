"""Local contract checks; dummy credentials, no live provider or browser."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from rap_workbench import provider_cli as cli
from rap_workbench.provider_journal import SubmissionStore
from rap_workbench.sync_provider import SyncClient


class ProviderCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / 'private' / 'submissions.sqlite3'
        self.manifest_path = Path(self.temp.name) / 'manifest.json'
        self.manifest = {
            'visual_type': 'image',
            'visual_url': 'https://media.example.net/photo.png?token=signed-visual-secret',
            'audio_url': 'https://media.example.net/audio.wav?signature=signed-audio-secret',
            'model': 'sync-3', 'output_file_name': 'test_output',
            'idempotency_key': 'local-action~1',
        }
        self.write_manifest(self.manifest)

    def write_manifest(self, value):
        self.manifest_path.write_text(json.dumps(value), encoding='utf-8')

    def invoke(self, *args, configured=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        env = {'RAP_ENABLE_SYNC_CLIENT': '1' if configured else '',
               'SYNC_API_KEY': 'dummy-cli-key' if configured else ''}
        with patch.dict(os.environ, env), redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main([*args, '--journal', str(self.journal)])
        return status, stdout.getvalue(), stderr.getvalue()

    def plan(self):
        status, output, error = self.invoke('plan', '--manifest', str(self.manifest_path))
        self.assertEqual((status, error), (0, ''))
        return json.loads(output)

    def accepted(self, remote_id='remote-generation-1'):
        planned = self.plan()
        store = SubmissionStore(self.journal)
        store.mark_submitting(planned['id'])
        store.record_acceptance(planned['id'], {
            'id': remote_id, 'status': 'PENDING', 'output_url': None,
            'output_available': False, 'error_code': None})
        return planned, store

    def fixture_client(self, snapshots):
        calls = []
        def transport(method, url, headers, body, timeout):
            calls.append((method, url, body))
            self.assertEqual({key.lower(): value for key, value in headers.items()}['x-api-key'], 'dummy-cli-key')
            value = snapshots.pop(0)
            if isinstance(value, Exception):
                raise value
            return 200, {}, json.dumps(value).encode('utf-8')
        return SyncClient('dummy-cli-key', allow_live=True, transport=transport,
                          max_attempts=1), calls

    def test_plan_is_local_persistent_and_resumes_exact_key_and_payload(self):
        with patch.object(SyncClient, 'from_env', side_effect=AssertionError('No provider access')):
            planned = self.plan()
            replay = self.plan()
        self.assertTrue(planned['created'])
        self.assertFalse(replay['created'])
        self.assertEqual(planned['id'], replay['id'])
        self.assertEqual(planned['payload_digest'], replay['payload_digest'])
        self.assertEqual(planned['idempotency_key'], 'local-action~1')
        self.assertEqual(planned['state'], 'READY')
        self.assertTrue(planned['no_generation_created'])
        self.assertTrue(planned['no_billing_submitted'])
        self.assertEqual(planned['input_types'], ['image', 'audio'])
        self.assertEqual(planned['target_endpoint'], 'https://api.sync.so/v2/generate')
        saved = SubmissionStore(self.journal).payload_for_retry(planned['id'])
        self.assertEqual(saved['input'][0]['url'], self.manifest['visual_url'])
        self.assertEqual(saved['input'][1]['url'], self.manifest['audio_url'])
        self.assertEqual(len(SubmissionStore(self.journal).list()), 1)
        self.assertNotIn('signed-', json.dumps(planned))
        self.assertNotIn('media.example.net', json.dumps(planned))

    def test_changed_signed_query_conflicts_without_new_action(self):
        original = self.plan()
        self.manifest['visual_url'] += '-changed'
        self.write_manifest(self.manifest)
        status, output, error = self.invoke('plan', '--manifest', str(self.manifest_path))
        self.assertEqual((status, output), (2, ''))
        self.assertNotIn('signed-', error)
        self.assertEqual(len(SubmissionStore(self.journal).list()), 1)
        self.assertEqual(SubmissionStore(self.journal).get(original['id'])['state'], 'READY')

    def test_generated_key_saved_and_show_recovers_it_after_restart(self):
        del self.manifest['idempotency_key']
        self.write_manifest(self.manifest)
        planned = self.plan()
        status, output, error = self.invoke('show', '--id', planned['id'])
        self.assertEqual((status, error), (0, ''))
        shown = json.loads(output)
        self.assertEqual(shown['idempotency_key'], planned['idempotency_key'])
        self.assertEqual(shown['payload_digest'], planned['payload_digest'])
        self.assertFalse(shown['network_used'])

    def test_invalid_and_oversized_manifests_are_safe_and_do_not_create_journal(self):
        valid = copy.deepcopy(self.manifest)
        invalid = [b'{bad', b'[]', b'{"visual_type":"image","visual_type":"video"}',
                   b'{"visual_type":NaN}', b'{"visual_type":"\\ud800"}', b'\xff',
                   b' ' * (cli.MAX_MANIFEST_BYTES + 1)]
        for field, value in [('api_key', 'dummy-cli-key'), ('headers', {'x-api-key': 'dummy-cli-key'}),
                             ('idempotency_key', ''), ('idempotency_key', 'x' * 129),
                             ('idempotency_key', 'bad key'), ('idempotency_key', None),
                             ('visual_url', 'https://user:dummy-cli-key@media.example.net/a'),
                             ('visual_url', 'https://127.0.0.1/a'), ('visual_url', 'http://media.example.net/a'),
                             ('model', 'unknown'), ('audio_url', {'api_key': 'dummy-cli-key'})]:
            invalid.append(json.dumps(dict(valid, **{field: value})).encode())
        for raw in invalid:
            with self.subTest(raw_length=len(raw)):
                self.manifest_path.write_bytes(raw)
                with patch.object(SyncClient, 'from_env', side_effect=AssertionError('No network')):
                    status, output, error = self.invoke('plan', '--manifest', str(self.manifest_path))
                self.assertEqual((status, output), (2, ''))
                self.assertEqual(json.loads(error)['error']['code'], 'INVALID_MANIFEST')
                self.assertNotIn('dummy-cli-key', error)
                self.assertNotIn('signed-', error)
                self.assertFalse(self.journal.exists())

    def test_show_redacts_signed_output_and_never_loads_client(self):
        planned, store = self.accepted()
        store.apply_snapshot(planned['id'], {
            'id': 'remote-generation-1', 'status': 'COMPLETED',
            'output_url': 'https://output.example.net/video.mp4?secret=signed-output-secret',
            'output_available': True, 'error_code': None})
        with patch.object(SyncClient, 'from_env', side_effect=AssertionError('No network')):
            status, output, error = self.invoke('show', '--id', planned['id'])
        self.assertEqual((status, error), (0, ''))
        self.assertTrue(json.loads(output)['has_output'])
        for secret in ('signed-', 'output.example.net', 'visual_url', 'audio_url', 'output_url'):
            self.assertNotIn(secret, output)

    def test_refresh_all_guards_fail_before_client_or_transport(self):
        planned, _ = self.accepted()
        ready_manifest = dict(self.manifest, idempotency_key='ready-key')
        self.write_manifest(ready_manifest)
        ready = self.plan()
        cases = [(['refresh', '--id', planned['id']], {}),
                 (['refresh', '--id', ready['id'], '--allow-network'], {}),
                 (['refresh', '--id', str(uuid4()), '--allow-network'], {}),
                 (['refresh', '--id', planned['id'], '--allow-network'], {'RAP_ENABLE_SYNC_CLIENT': '', 'SYNC_API_KEY': 'dummy-cli-key'}),
                 (['refresh', '--id', planned['id'], '--allow-network'], {'RAP_ENABLE_SYNC_CLIENT': '1', 'SYNC_API_KEY': ''})]
        for args, env in cases:
            with self.subTest(args=args, gate=env.get('RAP_ENABLE_SYNC_CLIENT')):
                with patch.dict(os.environ, {'RAP_ENABLE_SYNC_CLIENT': '', 'SYNC_API_KEY': '', **env}), \
                     patch.object(SyncClient, 'from_env', side_effect=AssertionError('Must not construct client')) as factory, \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main([*args, '--journal', str(self.journal)]), 2)
                    factory.assert_not_called()

    def test_refresh_only_gets_and_preserves_terminal_state_and_hides_output(self):
        planned, store = self.accepted()
        snapshots = [
            {'id': 'remote-generation-1', 'status': 'PROCESSING'},
            {'id': 'remote-generation-1', 'status': 'COMPLETED', 'outputUrl': 'https://output.example.net/a.mp4?token=signed-output-secret'},
            {'id': 'remote-generation-1', 'status': 'PENDING'},
        ]
        client, calls = self.fixture_client(snapshots)
        for state in ('PROCESSING', 'COMPLETED', 'COMPLETED'):
            with patch.object(SyncClient, 'from_env', return_value=client):
                status, output, error = self.invoke('refresh', '--id', planned['id'], '--allow-network', configured=True)
            self.assertEqual((status, error), (0, ''))
            result = json.loads(output)
            self.assertEqual(result['state'], state)
            self.assertEqual(result['request_method'], 'GET')
            self.assertFalse(result['generation_submitted'])
            self.assertFalse(result['output_downloaded'])
            self.assertNotIn('signed-', output)
            self.assertNotIn('dummy-cli-key', output)
        self.assertEqual(calls, [('GET', 'https://api.sync.so/v2/generate/remote-generation-1', None)] * 3)
        self.assertEqual(store.get(planned['id'])['idempotency_key'], planned['idempotency_key'])

    def test_observation_timeout_preserves_unknown_identity_and_state(self):
        planned = self.plan()
        store = SubmissionStore(self.journal)
        store.mark_submitting(planned['id'])
        store.record_submission_unknown(planned['id'], error_code='timeout', remote_id='remote-unknown')
        client, calls = self.fixture_client([TimeoutError('dummy-cli-key signed-output-secret')])
        with patch.object(SyncClient, 'from_env', return_value=client):
            status, output, error = self.invoke('refresh', '--id', planned['id'], '--allow-network', configured=True)
        self.assertEqual((status, output), (2, ''))
        self.assertEqual(json.loads(error)['error']['code'], 'OBSERVATION_FAILED')
        self.assertNotIn('dummy-cli-key', error)
        self.assertNotIn('signed-', error)
        saved = SubmissionStore(self.journal).get(planned['id'])
        self.assertEqual((saved['state'], saved['remote_id'], saved['idempotency_key']),
                         ('SUBMISSION_UNKNOWN', 'remote-unknown', planned['idempotency_key']))
        self.assertTrue(saved['last_error_code'])
        self.assertEqual(calls[0][0], 'GET')
        self.assertEqual(len(calls), 1)

    def test_completed_without_output_is_not_download_success(self):
        planned, _ = self.accepted()
        client, _ = self.fixture_client([{'id': 'remote-generation-1', 'status': 'COMPLETED'}])
        with patch.object(SyncClient, 'from_env', return_value=client):
            status, output, error = self.invoke('refresh', '--id', planned['id'], '--allow-network', configured=True)
        self.assertEqual((status, error), (0, ''))
        self.assertFalse(json.loads(output)['has_output'])
        self.assertFalse(json.loads(output)['output_downloaded'])

    def test_cli_has_no_submission_command_and_does_not_echo_bad_argv_or_secret_key(self):
        status, output, error = self.invoke('submit', '--api-key', 'dummy-cli-key?signature=signed-secret')
        self.assertEqual((status, output), (2, ''))
        self.assertNotIn('dummy-cli-key', error)
        self.assertNotIn('signed-secret', error)
        self.manifest['idempotency_key'] = 'dummy-cli-key'
        self.write_manifest(self.manifest)
        status, output, error = self.invoke('plan', '--manifest', str(self.manifest_path), configured=True)
        self.assertEqual((status, error), (0, ''))
        self.assertEqual(json.loads(output)['idempotency_key'], '[redacted]')

    def test_module_cli_process_restart_retains_local_record(self):
        env = dict(os.environ, RAP_ENABLE_SYNC_CLIENT='', SYNC_API_KEY='dummy-subprocess-key')
        base = [sys.executable, '-m', 'rap_workbench.provider_cli']
        planned = subprocess.run([*base, 'plan', '--manifest', str(self.manifest_path), '--journal', str(self.journal)],
                                 capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual((planned.returncode, planned.stderr), (0, ''))
        local = json.loads(planned.stdout)
        shown = subprocess.run([*base, 'show', '--id', local['id'], '--journal', str(self.journal)],
                               capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual((shown.returncode, shown.stderr), (0, ''))
        self.assertEqual(json.loads(shown.stdout)['payload_digest'], local['payload_digest'])
        self.assertNotIn('signed-', planned.stdout + shown.stdout)


if __name__ == '__main__':
    unittest.main()
