"""Durable local storyboard jobs; deliberately no simulated media generation."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .briefs import validate_brief, validate_id
from .providers import ProviderUnavailable, require_render_provider


class IdempotencyConflict(ValueError):
    """The supplied key already identifies a different normalized request."""


def _key(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('idempotency_key: expected 1–200 nonblank characters')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('idempotency_key: expected valid UTF-8 text') from exc
    return value


def _normalize(payload, idempotency_key):
    if not isinstance(payload, dict):
        raise ValueError('job: expected an object')
    unknown = set(payload) - {'mode', 'brief', 'idempotency_key'}
    if unknown:
        raise ValueError('job: unknown fields: ' + ', '.join(sorted(map(str, unknown))))
    if payload.get('mode') not in ('brief_preview', 'provider_render'):
        raise ValueError('mode: expected brief_preview or provider_render')
    brief = validate_brief(payload.get('brief'))
    body_key = _key(payload['idempotency_key']) if 'idempotency_key' in payload else None
    argument_key = _key(idempotency_key) if idempotency_key is not None else None
    if body_key is not None and argument_key is not None and body_key != argument_key:
        raise ValueError('idempotency_key: argument and payload must match')
    return {'mode': payload['mode'], 'brief': brief}, argument_key or body_key


def _preview(brief):
    duration = brief['duration_seconds']
    cut = duration // 3
    lengths = (cut, cut, duration - 2 * cut)
    directions = ('开场：建立场景与主题', '主段：安排表演与歌词', '收束：主题定格')
    storyboard = []
    start = 0
    for index, (length, direction) in enumerate(zip(lengths, directions), 1):
        storyboard.append({'shot': index, 'start_seconds': start,
                           'end_seconds': start + length, 'duration_seconds': length,
                           'stage': brief['stage'],
                           'performers': 1 if brief['mode'] == 'solo' else 2,
                           'direction': direction})
        start += length
    return {'storyboard': storyboard, 'parameters': dict(brief), 'is_generated_video': False}


class JobStore:
    """SQLite transactions and a unique key serialize retries across instances.

    Each operation owns its connection, including when used by threaded HTTP
    handlers. BEGIN IMMEDIATE covers key lookup and insert as one operation;
    no in-memory cache is part of the idempotency guarantee.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS jobs ('
                'id TEXT PRIMARY KEY, created_at TEXT NOT NULL, '
                'idempotency_key TEXT UNIQUE, normalized_input TEXT NOT NULL, '
                'record TEXT NOT NULL)'
            )

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=15)

    def create(self, payload, idempotency_key=None):
        normalized, key = _normalize(payload, idempotency_key)
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False)
        with closing(self._connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if key is not None:
                row = connection.execute(
                    'SELECT normalized_input, record FROM jobs WHERE idempotency_key = ?',
                    (key,)
                ).fetchone()
                if row:
                    if row[0] != canonical:
                        raise IdempotencyConflict('This idempotency key already identifies a different job input')
                    return json.loads(row[1]), False
            if normalized['mode'] == 'provider_render':
                require_render_provider()
            record = {'id': str(uuid4()),
                      'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                      'mode': 'brief_preview', 'kind': 'brief_preview', 'status': 'completed',
                      'result': _preview(normalized['brief'])}
            connection.execute(
                'INSERT INTO jobs (id, created_at, idempotency_key, normalized_input, record) '
                'VALUES (?, ?, ?, ?, ?)',
                (record['id'], record['created_at'], key, canonical,
                 json.dumps(record, ensure_ascii=False, allow_nan=False))
            )
        return record, True

    def get(self, identifier):
        validate_id(identifier)
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT record FROM jobs WHERE id = ?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with closing(self._connect()) as connection:
            rows = connection.execute('SELECT record FROM jobs ORDER BY created_at DESC, id').fetchall()
        return [json.loads(row[0]) for row in rows]
