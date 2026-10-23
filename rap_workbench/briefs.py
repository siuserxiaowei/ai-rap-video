"""Validated creative briefs saved as JSON in a local SQLite database."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4


DEFAULTS = {'mode': 'solo', 'stage': 'studio', 'duration_seconds': 12,
            'aspect_ratio': '9:16', 'quality': '720p', 'lyrics': '', 'language': 'zh'}
CHOICES = {'mode': ('solo', 'duo'), 'stage': ('rooftop', 'studio', 'street', 'lobby'),
           'aspect_ratio': ('9:16', '1:1', '16:9'),
           'quality': ('480p', '720p', '1080p'), 'language': ('zh', 'en')}


def validate_brief(payload):
    """Return a new normalized brief, rejecting unknown or invalid fields."""
    if not isinstance(payload, dict):
        raise ValueError('brief: expected an object')
    unknown = set(payload) - {'topic', *DEFAULTS}
    if unknown:
        raise ValueError('brief: unknown fields: ' + ', '.join(sorted(map(str, unknown))))
    result = dict(DEFAULTS, **payload)
    topic = result.get('topic')
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 240:
        raise ValueError('topic: expected 1–240 nonblank characters')
    result['topic'] = topic.strip()
    for field, choices in CHOICES.items():
        if not isinstance(result[field], str) or result[field] not in choices:
            raise ValueError(field + ': expected one of ' + ', '.join(choices))
    duration = result['duration_seconds']
    if type(duration) is not int or duration not in (10, 12, 15):
        raise ValueError('duration_seconds: expected an integer: 10, 12, or 15')
    if not isinstance(result['lyrics'], str) or len(result['lyrics']) > 4000:
        raise ValueError('lyrics: expected a string of at most 4000 characters')
    # Reject lone surrogates that cannot be written as UTF-8 in API responses.
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError('brief: expected valid UTF-8 JSON text') from exc
    return result


def validate_id(identifier):
    if not isinstance(identifier, str):
        raise ValueError('id: expected a UUID')
    try:
        parsed = UUID(identifier)
    except (ValueError, AttributeError) as exc:
        raise ValueError('id: expected a UUID') from exc
    if str(parsed) != identifier:
        raise ValueError('id: expected a canonical lowercase UUID')
    return identifier


class BriefStore:
    """A fresh connection per operation supports ThreadingHTTPServer safely."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS briefs '
                               '(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)')

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=10)

    def create(self, payload):
        record = validate_brief(payload)
        record.update(id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
        with self._connect() as connection:
            connection.execute('INSERT INTO briefs (id, created_at, payload) VALUES (?, ?, ?)',
                               (record['id'], record['created_at'], json.dumps(record, ensure_ascii=False)))
        return record

    def list(self):
        with self._connect() as connection:
            rows = connection.execute('SELECT payload FROM briefs ORDER BY created_at DESC, id').fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, identifier):
        validate_id(identifier)
        with self._connect() as connection:
            row = connection.execute('SELECT payload FROM briefs WHERE id = ?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None
