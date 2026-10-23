import copy
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from rap_workbench.sync_provider import (
    API_ORIGIN, MAX_RESPONSE_BYTES, SyncClient, SyncConfigError, SyncProtocolError,
    SyncTransportError, _NoRedirect, _urllib_transport, build_generation_request,
    normalize_generation, validate_generation_request,
)

DUMMY_KEY = 'fixture_dummy_key_only'
VISUAL = 'https://media.example.com/portrait.jpg?sig=private-test&expires=123'
AUDIO = 'https://media.example.com/voice.wav?sig=audio-test'


def request():
    return build_generation_request(visual_type='image', visual_url=VISUAL, audio_url=AUDIO)


def response(status=200, data=None, headers=None):
    return status, headers or {}, json.dumps(data if data is not None else {'id': 'generation-1', 'status': 'PENDING'}).encode()


class Fixture:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, *args):
        self.calls.append(copy.deepcopy(args))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def client(fixture, **kwargs):
    return SyncClient(DUMMY_KEY, allow_live=True, transport=fixture, sleep=lambda value: None, **kwargs)


class SyncClientTests(unittest.TestCase):
    def test_builder_camelcase_copy_and_url_order_preserved(self):
        payload = build_generation_request(visual_type='video', visual_url=VISUAL, audio_url=AUDIO, output_file_name='my_Clip-1')
        self.assertEqual(payload['outputFileName'], 'my_Clip-1')
        self.assertEqual(payload['input'], [{'type': 'video', 'url': VISUAL}, {'type': 'audio', 'url': AUDIO}])
        payload['input'].reverse()
        result = validate_generation_request(payload)
        self.assertEqual(result, payload)
        result['input'][0]['url'] = 'changed'
        self.assertEqual(payload['input'][0]['url'], AUDIO)

    def test_invalid_payload_urls_and_ids_are_rejected_safely(self):
        bad_urls = ['http://media.example.com/a', 'https://user:password@example.com/a', 'https://127.0.0.1/a',
                    'https://[::1]/a', 'https://169.254.169.254/a', 'https://localhost/a', 'https://a.localhost/a',
                    'https://10.0.0.1/a', 'https://127.1/a', 'https://0x7f.0.0.1/a', 'https://example.com\\@localhost/a',
                    'https://example.com/a\nheader', 'https://example.com:99999/a', 'https://example.com/a#fragment']
        for value in bad_urls:
            with self.subTest(url=value), self.assertRaises(SyncConfigError) as caught:
                build_generation_request(visual_type='image', visual_url=value, audio_url=AUDIO)
            self.assertNotIn(value, str(caught.exception))
        for payload in [dict(request(), options={}), dict(request(), model='other'), dict(request(), outputFileName='../bad'),
                        dict(request(), input=[{'type': 'audio', 'url': AUDIO}] * 2),
                        dict(request(), input=[{'type': 'image', 'assetId': 'asset'}, {'type': 'audio', 'url': AUDIO}])]:
            with self.assertRaises(SyncConfigError):
                validate_generation_request(payload)
        fixture = Fixture()
        for identifier in ['.', '..', '../x', 'https://evil.example/a', 'a/b', '', 'x' * 129]:
            with self.assertRaises(SyncConfigError):
                client(fixture).get(identifier)
        self.assertEqual(fixture.calls, [])

    def test_default_gate_and_from_env_only_exact_optin(self):
        fixture = Fixture()
        with self.assertRaises(SyncConfigError):
            SyncClient(DUMMY_KEY, transport=fixture).create(request(), 'saved-key')
        self.assertEqual(fixture.calls, [])
        for env in [{}, {'SYNC_API_KEY': DUMMY_KEY}, {'RAP_ENABLE_SYNC_CLIENT': 'true', 'SYNC_API_KEY': DUMMY_KEY}, {'RAP_ENABLE_SYNC_CLIENT': '1'}]:
            with patch.dict(os.environ, env, clear=True), self.assertRaises(SyncConfigError):
                SyncClient.from_env()
        with patch.dict(os.environ, {'RAP_ENABLE_SYNC_CLIENT': '1', 'SYNC_API_KEY': DUMMY_KEY}, clear=True):
            self.assertIsInstance(SyncClient.from_env(), SyncClient)

    def test_create_retries_identical_key_bytes_and_never_claims_replay_complete(self):
        fixture = Fixture(TimeoutError(VISUAL + DUMMY_KEY), response(200))
        result = client(fixture).create(request(), 'action-1')
        self.assertEqual(result['status'], 'PENDING')
        self.assertFalse(result['output_available'])
        self.assertEqual(fixture.calls[0], fixture.calls[1])
        method, url, headers, body, timeout = fixture.calls[0]
        self.assertEqual((method, url), ('POST', API_ORIGIN + '/v2/generate'))
        self.assertEqual(headers['Idempotency-Key'], 'action-1')
        self.assertEqual(headers['x-api-key'], DUMMY_KEY)
        self.assertEqual(json.loads(body), request())
        for key in ['', 'a b', 'a\nb', 'x' * 129, None]:
            with self.assertRaises(SyncConfigError):
                client(Fixture()).create(request(), key)

    def test_unknown_timeout_retains_remote_and_safe_diagnostics(self):
        fixture = Fixture(response(503, {'errorCode': 'IDEMPOTENCY_OUTCOME_UNKNOWN', 'generationId': 'known-1', 'message': VISUAL + DUMMY_KEY}), TimeoutError(VISUAL + DUMMY_KEY))
        with self.assertRaises(SyncTransportError) as caught:
            client(fixture).create(request(), 'persisted-key')
        error = caught.exception
        self.assertTrue(error.outcome_unknown)
        self.assertEqual(error.generation_id, 'known-1')
        self.assertEqual(fixture.calls[0][2]['Idempotency-Key'], fixture.calls[1][2]['Idempotency-Key'])
        for text in [str(error), repr(error), repr(error.__dict__)]:
            self.assertNotIn(DUMMY_KEY, text)
            self.assertNotIn(VISUAL, text)

    def test_conflicts_and_401_no_retry_inprogress_and_rate_retry(self):
        for status, code in [(401, 'unauthorized'), (409, 'IDEMPOTENCY_KEY_CONFLICT')]:
            fixture = Fixture(response(status, {'errorCode': code, 'message': DUMMY_KEY + VISUAL}))
            with self.assertRaises(SyncTransportError) as caught:
                client(fixture).create(request(), 'saved-key')
            self.assertEqual(len(fixture.calls), 1)
            self.assertEqual(caught.exception.http_status, status)
            self.assertFalse(caught.exception.outcome_unknown)
        for status, code in [(409, 'IDEMPOTENCY_IN_PROGRESS'), (429, 'rate_limit_exceeded')]:
            fixture = Fixture(response(status, {'errorCode': code}, {'Retry-After': '0'}), response(201))
            self.assertEqual(client(fixture).create(request(), 'saved-key')['id'], 'generation-1')
            self.assertEqual(fixture.calls[0], fixture.calls[1])

    def test_get_failure_never_posts_and_keeps_unknown_false(self):
        fixture = Fixture(TimeoutError(DUMMY_KEY), response(500, {'errorCode': 'internal_error'}))
        with self.assertRaises(SyncTransportError) as caught:
            client(fixture).get('existing-1')
        self.assertEqual([call[0] for call in fixture.calls], ['GET', 'GET'])
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertTrue(all(call[3] is None for call in fixture.calls))
        with self.assertRaises(SyncProtocolError):
            client(Fixture(response())).get('different-id')
        self.assertEqual(client(Fixture(response(data={'id': '~safe.ID', 'status': 'PENDING'}))).get('~safe.ID')['id'], '~safe.ID')

    def test_all_five_statuses_no_fabricated_url_or_raw_message(self):
        for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REJECTED']:
            result = normalize_generation({'id': 'remote', 'status': status, 'error': DUMMY_KEY + VISUAL})
            self.assertIsNone(result['output_url'])
            self.assertFalse(result['output_available'])
            self.assertNotIn('error', result)
        output = 'https://cdn.example.com/result.mp4?sig=keep-exact&expires=1'
        result = normalize_generation({'id': 'remote', 'status': 'COMPLETED', 'outputUrl': output, 'errorCode': None})
        self.assertTrue(result['output_available'])
        self.assertEqual(result['output_url'], output)
        for payload in [{'id': 'a', 'status': 'done'}, {'id': '../a', 'status': 'PENDING'},
                        {'id': 'a', 'status': 'COMPLETED', 'outputUrl': False},
                        {'id': 'a', 'status': 'COMPLETED', 'outputUrl': 'https://localhost/output'}]:
            with self.assertRaises(SyncProtocolError):
                normalize_generation(payload)

    def test_estimate_wire_fields_and_null_credits_no_idempotency_claim(self):
        expected = {'estimatedFrameCount': 300, 'estimatedGenerationCost': 1.5, 'estimatedCredits': None}
        fixture = Fixture(response(503, {'errorCode': 'internal_error'}), response(data=expected))
        self.assertEqual(client(fixture).estimate(10), expected)
        self.assertEqual(fixture.calls[0], fixture.calls[1])
        self.assertEqual(fixture.calls[0][1], API_ORIGIN + '/v2/generations/estimate')
        self.assertNotIn('Idempotency-Key', fixture.calls[0][2])
        self.assertEqual(json.loads(fixture.calls[0][3]), {'model': 'sync-3', 'duration': 10, 'fps': 30, 'reasoningEnabled': False})
        for number in [float('nan'), float('inf'), -1, 0, True, '1', 10 ** 1000]:
            with self.assertRaises(SyncConfigError):
                client(Fixture()).estimate(number)
        for name in expected:
            for number in [float('inf'), -1, True, '1']:
                with self.assertRaises(SyncProtocolError):
                    client(Fixture(response(data=dict(expected, **{name: number})))).estimate(10)

    def test_invalid_oversized_duplicate_nonfinite_json_and_redaction(self):
        for raw in [b'not json', b'[]', b'{"x":' + b'9' * 5000 + b'}', b'{"x":NaN}', b'{"x":1e400}', b'{"x":1,"x":2}', b'{"x":"\\ud800"}', b'x' * (MAX_RESPONSE_BYTES + 1)]:
            fixture = Fixture((201, {}, raw))
            with self.assertRaises(SyncProtocolError) as caught:
                client(fixture).create(request(), 'saved-key')
            self.assertTrue(caught.exception.outcome_unknown)
            self.assertEqual(len(fixture.calls), 1)
        fixture = Fixture(response(401, {'errorCode': DUMMY_KEY, 'error': VISUAL}))
        with self.assertRaises(SyncTransportError) as caught:
            client(fixture).get('remote')
        self.assertNotIn(DUMMY_KEY, repr(caught.exception.__dict__))
        with self.assertRaises(SyncConfigError):
            client(Fixture()).get(DUMMY_KEY)
        with self.assertRaises(SyncProtocolError) as caught:
            client(Fixture(response(data={'id': DUMMY_KEY, 'status': 'PENDING'}))).create(request(), 'saved-key')
        self.assertNotIn(DUMMY_KEY, repr(caught.exception.__dict__))
        fixture = Fixture(response(data={'id': 'remote', 'status': 'FAILED', 'errorCode': DUMMY_KEY}))
        self.assertEqual(client(fixture).get('remote')['error_code'], 'REDACTED')

    def test_redirect_no_follow_and_default_transport_bounded_reads(self):
        request_object = Request(API_ORIGIN + '/v2/generate', headers={'x-api-key': DUMMY_KEY})
        self.assertIsNone(_NoRedirect().redirect_request(request_object, None, 302, 'moved', {'Location': VISUAL}, VISUAL))
        fixture = Fixture((307, {'Location': VISUAL}, b''))
        with self.assertRaises(SyncTransportError) as caught:
            client(fixture).create(request(), 'saved-key')
        self.assertEqual(caught.exception.code, 'REDIRECT_REJECTED')
        self.assertEqual(len(fixture.calls), 1)
        with patch('rap_workbench.sync_provider.build_opener') as opener:
            error = HTTPError(API_ORIGIN, 302, DUMMY_KEY, {'Location': VISUAL}, io.BytesIO(b''))
            opener.return_value.open.side_effect = error
            result = _urllib_transport('GET', API_ORIGIN + '/v2/generate/remote', {'x-api-key': DUMMY_KEY}, None, 1)
            self.assertEqual(result[0], 302)
        with patch('rap_workbench.sync_provider.build_opener') as opener:
            answer = opener.return_value.open.return_value
            answer.read.return_value = b'x' * (MAX_RESPONSE_BYTES + 1)
            with self.assertRaises(SyncProtocolError):
                _urllib_transport('GET', API_ORIGIN + '/v2/generate/remote', {'x-api-key': DUMMY_KEY}, None, 1)
            answer.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)


if __name__ == '__main__':
    unittest.main()
