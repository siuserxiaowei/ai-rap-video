"""Local preparation and explicit GET-only observation; never submits media."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from .briefs import validate_id
from .provider_journal import SubmissionStore
from .sync_provider import (SyncClient, SyncConfigError, SyncTransportError,
                            build_generation_request)

MAX_MANIFEST_BYTES = 64 * 1024
DEFAULT_JOURNAL = '.workbench/provider-submissions.sqlite3'
TARGET_ENDPOINT = 'https://api.sync.so/v2/generate'
MANIFEST_FIELDS = frozenset(('visual_type', 'visual_url', 'audio_url', 'model',
                             'output_file_name', 'idempotency_key'))
class CLIError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error text can echo arbitrary argv, including keys.
        raise CLIError('INVALID_ARGUMENTS', 'Use plan, show, or refresh; see --help.')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest field')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON is not supported')


def read_manifest(path):
    """Read a bounded UTF-8 JSON object, without displaying any media URL."""
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest must be a bounded regular file')
        with path.open('rb') as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest is too large')
        manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                              parse_constant=_reject_constant)
        if not isinstance(manifest, dict) or set(manifest) - MANIFEST_FIELDS:
            raise ValueError('Unsupported manifest fields')
        # Reject surrogate escapes as well as invalid raw UTF-8.
        json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode('utf-8')
        key = manifest.pop('idempotency_key', str(uuid4()))
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{1,128}', key):
            raise ValueError('Invalid idempotency key')
        payload = build_generation_request(**manifest)
        return key, payload
    except (OSError, ValueError, TypeError, RecursionError):
        raise CLIError('INVALID_MANIFEST', 'Manifest is unreadable, oversized, or invalid.') from None


def _code(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_~-]{1,80}', value) else 'OBSERVATION_ERROR'


def _metadata(record):
    """Whitelist metadata; original request and signed output never escape."""
    return {
        'id': record['id'], 'created_at': record['created_at'],
        'updated_at': record['updated_at'], 'idempotency_key': record['idempotency_key'],
        'payload_digest': record['payload_digest'], 'state': record['state'],
        'remote_id': record.get('remote_id'), 'revision': record['revision'],
        'has_output': bool(record.get('output_available') and record.get('output_url')),
        'last_error_code': _code(record['last_error_code']) if record.get('last_error_code') else None,
    }


def _emit(payload, stream):
    # Defense in depth: even a supplied action key must not echo the API secret.
    secret = os.environ.get('SYNC_API_KEY')
    def scrub(value):
        if isinstance(value, str):
            return value.replace(secret, '[redacted]') if secret else value
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value
    print(json.dumps(scrub(payload), ensure_ascii=False, allow_nan=False), file=stream)


def _load(store, identifier):
    validate_id(identifier)
    record = store.get(identifier)
    if record is None:
        raise CLIError('NOT_FOUND', 'Local submission was not found.')
    return record


def _parser():
    parser = Parser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('plan', 'show', 'refresh'):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument('--journal', default=DEFAULT_JOURNAL)
        if name == 'plan':
            command.add_argument('--manifest', required=True)
        else:
            command.add_argument('--id', required=True)
        if name == 'refresh':
            command.add_argument('--allow-network', action='store_true',
                                 help='Allow a status GET; requires the environment gate and key.')
    return parser


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.command == 'plan':
            key, payload = read_manifest(args.manifest)
            record, created = SubmissionStore(args.journal).prepare(key, payload)
            result = _metadata(record)
            result.update(command='plan', created=created, target_endpoint=TARGET_ENDPOINT,
                          model=payload['model'], input_types=[item['type'] for item in payload['input']],
                          no_generation_created=True, no_billing_submitted=True,
                          message='Saved locally only; no remote generation or billing request was sent.')
        else:
            validate_id(args.id)
            if args.command == 'refresh' and not args.allow_network:
                raise CLIError('NETWORK_NOT_ALLOWED', 'Refresh requires explicit --allow-network.')
            store = SubmissionStore(args.journal)
            record = _load(store, args.id)
            if args.command == 'show':
                result = dict(_metadata(record), command='show', network_used=False)
            else:
                if not record.get('remote_id'):
                    raise CLIError('REMOTE_ID_REQUIRED', 'Refresh requires an existing remote generation id.')
                # Enforce both prerequisites even when a test injects the client.
                if (os.environ.get('RAP_ENABLE_SYNC_CLIENT') != '1'
                        or not os.environ.get('SYNC_API_KEY', '').strip()):
                    raise CLIError('SYNC_NOT_CONFIGURED', 'Refresh requires the explicit environment gate and API key.')
                client = SyncClient.from_env()
                try:
                    snapshot = client.get(record['remote_id'])
                except SyncTransportError as exc:
                    store.record_observation_error(args.id, _code(getattr(exc, 'code', None)))
                    raise CLIError('OBSERVATION_FAILED', 'Status lookup failed; saved submission identity and state are retained.') from None
                record = store.apply_snapshot(args.id, snapshot)
                result = dict(_metadata(record), command='refresh', request_method='GET',
                              generation_submitted=False, output_downloaded=False)
        _emit(result, sys.stdout)
        return 0
    except CLIError as exc:
        _emit({'error': {'code': exc.code, 'message': exc.message}}, sys.stderr)
    except SyncConfigError:
        _emit({'error': {'code': 'SYNC_NOT_CONFIGURED', 'message': 'Sync client is not configured for observation.'}}, sys.stderr)
    except (ValueError, KeyError):
        _emit({'error': {'code': 'INVALID_INPUT_OR_STATE', 'message': 'Invalid input or conflicting saved submission.'}}, sys.stderr)
    except Exception:
        # Never serialize OS paths, SQL, provider messages, bodies, or URLs.
        _emit({'error': {'code': 'LOCAL_OPERATION_FAILED', 'message': 'Operation failed; no generation was submitted by this CLI.'}}, sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
