"""Local-only research workbench HTTP entry point (Python 3.10+ stdlib)."""
import argparse
import importlib
import json
import mimetypes
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .briefs import BriefStore, validate_id
from .catalog import filter_sites, load_sites, stats

MAX_BODY_BYTES = 1024 * 1024
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


class HTTPProblem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def _module(name):
    try:
        return importlib.import_module('.' + name, __package__)
    except ImportError as exc:
        raise HTTPProblem(503, 'MODULE_UNAVAILABLE', name + ' is not available') from exc


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field: ' + key)
        result[key] = value
    return result


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root, db_path=None):
        self.root = Path(root).resolve()
        self.web_root = (self.root / 'web').resolve()
        self.sites = load_sites(self.root)
        self.brief_store = BriefStore(db_path or self.root / '.workbench' / 'briefs.sqlite3')
        self.jobs_path = self.brief_store.path.with_name('jobs.sqlite3')
        self.job_store = None
        super().__init__(address, WorkbenchHandler)

    def get_jobs(self):
        if self.job_store is None:
            self.job_store = _module('jobs').JobStore(self.jobs_path)
        return self.job_store


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = 'RapWorkbench/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Do not log incoming paths, queries, or user brief content.
        pass

    def _send(self, status, content, content_type='application/json; charset=utf-8', filename=None):
        if isinstance(content, str):
            content = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False, allow_nan=False))

    def send_error(self, code, message=None, explain=None):
        self._json(code, {'error': {'code': 'HTTP_' + str(code), 'message': message or 'HTTP request error'}})

    def _error(self, status, code, message):
        self._json(status, {'error': {'code': code, 'message': message}})

    def _url(self):
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise ValueError('expected a local absolute path')
            if re.search(r'%(?![0-9a-fA-F]{2})', parsed.path):
                raise ValueError('invalid URL encoding')
            path = unquote(parsed.path, encoding='utf-8', errors='strict')
            if not path.startswith('/') or '\\' in path or '\x00' in path:
                raise ValueError('invalid path')
            if any(part.startswith('.') for part in path.split('/') if part):
                raise HTTPProblem(403, 'FORBIDDEN', 'Hidden paths and traversal are forbidden')
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False, max_num_fields=30)
            if any(len(values) != 1 for values in query.values()):
                raise ValueError('duplicate query parameters are not allowed')
            return path, {key: values[0] for key, values in query.items()}
        except (ValueError, UnicodeError) as exc:
            raise HTTPProblem(400, 'INVALID_URL', str(exc)) from exc

    def _read_json(self):
        if self.headers.get('Transfer-Encoding'):
            raise HTTPProblem(400, 'INVALID_BODY', 'Transfer-Encoding is not supported')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]+', lengths[0]):
            raise HTTPProblem(400, 'INVALID_BODY', 'A single valid Content-Length is required')
        length = int(lengths[0])
        if length > MAX_BODY_BYTES:
            raise HTTPProblem(413, 'BODY_TOO_LARGE', 'JSON body exceeds 1 MiB')
        if self.headers.get_content_type() != 'application/json':
            raise HTTPProblem(415, 'UNSUPPORTED_MEDIA_TYPE', 'Content-Type must be application/json')
        if self.headers.get_content_charset('utf-8').lower() not in ('utf-8', 'utf8'):
            raise HTTPProblem(415, 'UNSUPPORTED_MEDIA_TYPE', 'JSON must use UTF-8')
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('incomplete JSON body')
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON number')))
            if not isinstance(value, dict):
                raise ValueError('expected a JSON object')
            # JSON permits escaped surrogate code points; UTF-8 responses do not.
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            return value
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise HTTPProblem(400, 'INVALID_JSON', 'Invalid JSON: ' + str(exc)) from exc

    def _decisions(self):
        try:
            decisions = json.loads((self.server.root / 'docs' / 'decisions.json').read_text(encoding='utf-8'))
            if not isinstance(decisions, list):
                raise ValueError('expected a decisions array')
            return decisions
        except (OSError, ValueError) as exc:
            raise HTTPProblem(503, 'DECISIONS_UNAVAILABLE', 'Decision catalog cannot be read') from exc

    @staticmethod
    def _query(query, allowed):
        unknown = set(query) - set(allowed)
        if unknown:
            raise ValueError('unknown query parameters: ' + ', '.join(sorted(unknown)))

    def _get(self):
        path, query = self._url()
        if path == '/api/sites':
            self._query(query, ('q', 'category', 'api_status', 'evidence_status'))
            sites = filter_sites(self.server.sites, query.get('q', ''), query.get('category', ''),
                                 query.get('api_status', ''), query.get('evidence_status', ''))
            return self._json(200, {'sites': sites, 'total': len(self.server.sites), 'filtered': len(sites)})
        if path.startswith('/api/sites/'):
            self._query(query, ())
            identifier = path[len('/api/sites/'):]
            if not re.fullmatch(r'[0-9]{2}', identifier):
                raise ValueError('site id: expected two ASCII digits')
            site = next((site for site in self.server.sites if site['id'] == identifier), None)
            if site is None:
                raise HTTPProblem(404, 'NOT_FOUND', 'Site not found')
            return self._json(200, {'site': site})
        if path == '/api/stats':
            self._query(query, ())
            return self._json(200, stats(self.server.sites))
        if path == '/api/decisions':
            self._query(query, ())
            return self._json(200, {'decisions': self._decisions()})
        if path == '/api/briefs':
            self._query(query, ())
            return self._json(200, {'briefs': self.server.brief_store.list()})
        if path.startswith('/api/briefs/') or path.startswith('/api/jobs/'):
            self._query(query, ())
            identifier = path.rsplit('/', 1)[1]
            validate_id(identifier)
            kind = 'brief' if path.startswith('/api/briefs/') else 'job'
            if path != '/api/' + kind + 's/' + identifier:
                raise HTTPProblem(404, 'NOT_FOUND', 'Route not found')
            store = self.server.brief_store if kind == 'brief' else self.server.get_jobs()
            record = store.get(identifier)
            if record is None:
                raise HTTPProblem(404, 'NOT_FOUND', kind.capitalize() + ' not found')
            return self._json(200, {kind: record})
        if path == '/api/report':
            self._query(query, ('format',))
            fmt = query.get('format', 'markdown')
            if fmt not in ('json', 'csv', 'markdown'):
                raise ValueError('format: expected json, csv, or markdown')
            exports = _module('exports')
            if fmt == 'markdown':
                content = exports.export_markdown(self.server.sites, self._decisions())
            else:
                content = getattr(exports, 'export_' + fmt)(self.server.sites)
            mime, suffix = {'json': ('application/json', 'json'), 'csv': ('text/csv', 'csv'),
                            'markdown': ('text/markdown', 'md')}[fmt]
            return self._send(200, content, mime + '; charset=utf-8', 'rap-research.' + suffix)
        if path.startswith('/api/'):
            raise HTTPProblem(404, 'NOT_FOUND', 'Route not found')
        self._query(query, ())
        relative = 'index.html' if path == '/' else path.lstrip('/')
        target = (self.server.web_root / relative).resolve()
        if not target.is_relative_to(self.server.web_root):
            raise HTTPProblem(403, 'FORBIDDEN', 'Static path escapes web directory')
        if any(part.startswith('.') for part in target.relative_to(self.server.web_root).parts):
            raise HTTPProblem(403, 'FORBIDDEN', 'Hidden static files are forbidden')
        if not target.is_file():
            raise HTTPProblem(404, 'NOT_FOUND', 'Static file not found')
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if mime.startswith('text/') or mime in ('application/javascript', 'application/json'):
            mime += '; charset=utf-8'
        return self._send(200, target.read_bytes(), mime)

    def _post(self):
        path, query = self._url()
        self._query(query, ())
        if path not in ('/api/briefs', '/api/quote', '/api/jobs'):
            raise HTTPProblem(404, 'NOT_FOUND', 'Route not found')
        payload = self._read_json()
        if path == '/api/briefs':
            return self._json(201, {'brief': self.server.brief_store.create(payload)})
        if path == '/api/quote':
            return self._json(200, {'quote': _module('quotes').quote(payload)})
        jobs = _module('jobs')
        header_key = self.headers.get('Idempotency-Key')
        if header_key and payload.get('idempotency_key') and header_key != payload['idempotency_key']:
            raise ValueError('Idempotency-Key header and payload must match')
        try:
            job, created = self.server.get_jobs().create(payload, header_key or payload.get('idempotency_key'))
        except jobs.IdempotencyConflict as exc:
            raise HTTPProblem(409, 'IDEMPOTENCY_CONFLICT', str(exc)) from exc
        except jobs.ProviderUnavailable as exc:
            raise HTTPProblem(503, 'PROVIDER_UNAVAILABLE', str(exc)) from exc
        return self._json(201 if created else 200, {'job': job})

    def _dispatch(self, handler):
        try:
            handler()
        except HTTPProblem as exc:
            self.close_connection = True
            self._error(exc.status, exc.code, exc.message)
        except ValueError as exc:
            self.close_connection = True
            self._error(400, 'INVALID_INPUT', str(exc))
        except Exception:
            self.close_connection = True
            self._error(500, 'INTERNAL_ERROR', 'The request could not be completed')

    def do_GET(self):
        self._dispatch(self._get)

    def do_HEAD(self):
        self._dispatch(self._get)

    def do_POST(self):
        self._dispatch(self._post)

    def _method_not_allowed(self):
        self._error(405, 'METHOD_NOT_ALLOWED', 'Supported methods: GET, HEAD, POST')

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _method_not_allowed


def make_server(host='127.0.0.1', port=8787, root=DEFAULT_ROOT, db_path=None):
    return WorkbenchServer((host, port), root, db_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args(argv)
    try:
        server = make_server(args.host, args.port)
    except (OSError, ValueError) as exc:
        parser.exit(1, 'Unable to start workbench: ' + str(exc) + '\n')
    print('Rap Research Studio: http://{}:{}'.format(args.host, server.server_address[1]), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
