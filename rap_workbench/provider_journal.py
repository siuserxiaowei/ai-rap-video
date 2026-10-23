"""Offline, durable Sync action journal. Media inputs are private retry data.

No submission, polling, credential lookup or retention deletion happens here.
The public records contain output credentials; callers must redact output_url
when printing them. Event logs deliberately never contain any media URL.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import UUID, uuid4


DEFAULT_PATH = Path('.workbench/provider-submissions.sqlite3')
PROVIDER_STATES = frozenset(('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REJECTED'))
TERMINAL_STATES = frozenset(('COMPLETED', 'FAILED', 'REJECTED'))
_TOKEN = re.compile(r'[A-Za-z0-9._~-]{1,128}', re.ASCII)
_SNAPSHOT_FIELDS = {'id', 'status', 'output_url', 'output_available', 'error_code'}


class IdempotencyConflict(ValueError):
    """An existing action key cannot be rebound to another canonical payload."""


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _token(value, field, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(field + ': expected a safe 1–128 character token')
    return value


def _remote_id(value):
    value = _token(value, 'remote_id')
    if value in ('.', '..'):
        raise ValueError('remote_id: invalid path token')
    return value


def _local_id(value):
    if not isinstance(value, str):
        raise ValueError('local_id: expected a canonical UUID')
    try:
        valid = str(UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValueError('local_id: expected a canonical UUID')
    return value


def _output_url(value):
    if value is None:
        return None
    if (not isinstance(value, str) or not value or len(value) > 16384
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or '\\' in value):
        raise ValueError('output_url: expected a public HTTPS URL')
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').rstrip('.').lower()
        parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or host == 'localhost' or host.endswith(('.localhost', '.local'))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host, re.ASCII):
                raise ValueError()
            if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                   for label in host.split('.')):
                raise ValueError()
            # Reject ambiguous decimal/hex IP spellings rather than treat as DNS.
            if all(re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)', label) for label in host.split('.')):
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError('output_url: expected a public HTTPS URL') from None
    return value


def _snapshot(value):
    if not isinstance(value, dict) or set(value) - _SNAPSHOT_FIELDS:
        raise ValueError('snapshot: expected normalized generation fields')
    identifier = _remote_id(value.get('id'))
    state = value.get('status')
    if not isinstance(state, str) or state not in PROVIDER_STATES:
        raise ValueError('snapshot.status: unknown provider state')
    url = _output_url(value.get('output_url'))
    available = state == 'COMPLETED' and url is not None
    if 'output_available' in value and (type(value['output_available']) is not bool
                                      or value['output_available'] != available):
        raise ValueError('snapshot.output_available: inconsistent with status and output URL')
    return {'id': identifier, 'status': state, 'output_url': url,
            'output_available': available,
            'error_code': _token(value.get('error_code'), 'error_code', nullable=True)}


def _serialize_payload(payload):
    def check(value, depth=0):
        if depth > 64:
            raise ValueError('payload: JSON nesting exceeds limit')
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('payload: object keys must be strings')
            for item in value.values():
                check(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                check(item, depth + 1)
        elif type(value) is float:
            if not math.isfinite(value):
                raise ValueError('payload: nonfinite JSON number')
        elif value is not None and type(value) not in (str, int, bool):
            raise ValueError('payload: expected JSON values')
    if not isinstance(payload, dict):
        raise ValueError('payload: expected a JSON object')
    try:
        check(payload)
        original = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        canonical = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(',', ':')).encode('utf-8')
        if len(original.encode('utf-8')) > 1024 * 1024:
            raise ValueError('payload: exceeds 1 MiB')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError('payload: expected bounded, finite UTF-8 JSON') from None
    return original, canonical.decode('utf-8'), hashlib.sha256(canonical).hexdigest()


class SubmissionStore:
    """One SQLite transaction per action; no in-memory idempotency authority.

    Local records and keys are never expired automatically. ``prepare`` keeps
    the first request's JSON privately, even when an equivalent reordered
    object is supplied later. ``payload_for_retry`` is the explicit private
    recovery API. Mutators return public records; missing records raise
    KeyError. ``get`` alone returns None for an unknown valid local UUID.
    """

    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError('journal: expected a regular local SQLite file') from None
        else:
            os.close(descriptor)
        self._secure_files()
        with self._transaction() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS provider_submissions ('
                               'id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, '
                               'payload_digest TEXT NOT NULL, canonical_json TEXT NOT NULL, '
                               'payload_json TEXT NOT NULL, record_json TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS provider_submission_events ('
                               'event_id INTEGER PRIMARY KEY AUTOINCREMENT, '
                               'local_id TEXT NOT NULL, event_json TEXT NOT NULL)')

    def _secure_files(self):
        for name in (str(self.path), str(self.path) + '-journal', str(self.path) + '-wal', str(self.path) + '-shm'):
            try:
                os.chmod(name, 0o600)
            except OSError:
                pass  # Best effort on filesystems without POSIX permission support.

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=15)

    @contextmanager
    def _transaction(self):
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                yield connection
        finally:
            self._secure_files()

    @staticmethod
    def _load(connection, local_id):
        row = connection.execute('SELECT record_json FROM provider_submissions WHERE id=?', (local_id,)).fetchone()
        if row is None:
            raise KeyError('Submission not found')
        return json.loads(row[0])

    @staticmethod
    def _event(connection, record, kind, observed_state=None):
        event = {key: record[key] for key in ('id', 'updated_at', 'revision', 'state',
                                             'remote_id', 'output_available', 'last_error_code')}
        event['kind'] = kind
        if observed_state is not None:
            event['observed_state'] = observed_state
        connection.execute('INSERT INTO provider_submission_events(local_id,event_json) VALUES (?,?)',
                           (record['id'], json.dumps(event, ensure_ascii=False)))

    def _save(self, connection, record, kind, observed_state=None):
        record['revision'] += 1
        record['updated_at'] = _now()
        connection.execute('UPDATE provider_submissions SET record_json=? WHERE id=?',
                           (json.dumps(record, ensure_ascii=False), record['id']))
        self._event(connection, record, kind, observed_state)
        return record

    def prepare(self, idempotency_key, payload):
        key = _token(idempotency_key, 'idempotency_key')
        original, canonical, digest = _serialize_payload(payload)
        with self._transaction() as connection:
            row = connection.execute('SELECT canonical_json, record_json FROM provider_submissions '
                                     'WHERE idempotency_key=?', (key,)).fetchone()
            if row:
                if row[0] != canonical:
                    raise IdempotencyConflict('The action key already identifies different inputs')
                return json.loads(row[1]), False
            now = _now()
            record = {'id': str(uuid4()), 'created_at': now, 'updated_at': now,
                      'idempotency_key': key, 'payload_digest': digest, 'state': 'READY',
                      'remote_id': None, 'output_url': None, 'output_available': False,
                      'revision': 1, 'last_error_code': None}
            connection.execute('INSERT INTO provider_submissions VALUES (?,?,?,?,?,?)',
                               (record['id'], key, digest, canonical, original, json.dumps(record)))
            self._event(connection, record, 'prepared')
            return record, True

    def get(self, local_id):
        _local_id(local_id)
        with closing(self._connect()) as connection:
            try:
                return self._load(connection, local_id)
            except KeyError:
                return None

    def list(self):
        with closing(self._connect()) as connection:
            rows = connection.execute('SELECT record_json FROM provider_submissions ORDER BY rowid').fetchall()
        return [json.loads(row[0]) for row in rows]

    def payload_for_retry(self, local_id):
        _local_id(local_id)
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT payload_json FROM provider_submissions WHERE id=?', (local_id,)).fetchone()
        if row is None:
            raise KeyError('Submission not found')
        return json.loads(row[0])

    def mark_submitting(self, local_id):
        _local_id(local_id)
        with self._transaction() as connection:
            record = self._load(connection, local_id)
            # Retrying an unresolved action never clears its uncertainty; known
            # remote and terminal states also cannot be reset by a local mark.
            if record['state'] != 'READY':
                return record
            record['state'] = 'SUBMITTING'
            return self._save(connection, record, 'submitting')

    @staticmethod
    def _bind(record, remote_id):
        if record['remote_id'] is not None and record['remote_id'] != remote_id:
            raise ValueError('remote_id: does not match this submission')
        record['remote_id'] = remote_id

    def _record_snapshot(self, local_id, snapshot, kind):
        _local_id(local_id)
        normalized = _snapshot(snapshot)
        with self._transaction() as connection:
            record = self._load(connection, local_id)
            self._bind(record, normalized['id'])
            old, new = record['state'], normalized['status']
            stale = ((old in TERMINAL_STATES and new != old)
                     or (old == 'PROCESSING' and new == 'PENDING'))
            if not stale:
                record['state'] = new
                # A later COMPLETED response may enrich a missing output; a
                # sparse replay cannot erase an output already observed.
                preserve_output = (old == new == 'COMPLETED' and record['output_available']
                                   and normalized['output_url'] is None)
                if not preserve_output:
                    record['output_url'] = normalized['output_url']
                record['output_available'] = new == 'COMPLETED' and record['output_url'] is not None
                record['last_error_code'] = normalized['error_code']
            return self._save(connection, record, 'snapshot_ignored' if stale else kind, new)

    def record_acceptance(self, local_id, snapshot):
        return self._record_snapshot(local_id, snapshot, 'accepted')

    def apply_snapshot(self, local_id, snapshot):
        return self._record_snapshot(local_id, snapshot, 'observed')

    def record_submission_unknown(self, local_id, error_code=None, remote_id=None):
        _local_id(local_id)
        error_code = _token(error_code, 'error_code', nullable=True)
        if remote_id is not None:
            remote_id = _remote_id(remote_id)
        with self._transaction() as connection:
            record = self._load(connection, local_id)
            if remote_id is not None:
                self._bind(record, remote_id)
            if record['state'] in ('READY', 'SUBMITTING', 'SUBMISSION_UNKNOWN'):
                record['state'] = 'SUBMISSION_UNKNOWN'
            record['last_error_code'] = error_code
            return self._save(connection, record, 'submission_unknown')

    def record_observation_error(self, local_id, error_code):
        _local_id(local_id)
        error_code = _token(error_code, 'error_code', nullable=True)
        with self._transaction() as connection:
            record = self._load(connection, local_id)
            record['last_error_code'] = error_code
            return self._save(connection, record, 'observation_error')

    def events(self, local_id):
        _local_id(local_id)
        with closing(self._connect()) as connection:
            self._load(connection, local_id)
            rows = connection.execute('SELECT event_json FROM provider_submission_events '
                                      'WHERE local_id=? ORDER BY event_id', (local_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]
