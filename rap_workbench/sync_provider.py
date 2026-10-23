"""Opt-in Sync REST boundary, based on the archived public docs (2026-10-24).

No uploads, media fetching, billing verification or automatic submission journal.
The public OpenAPI advertises multipart on create; quickstart and the common
CreateGenerationDto explicitly document the limited JSON shape used here.
"""
import ipaddress
import json
import math
import os
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

API_ORIGIN = 'https://api.sync.so'
MAX_RESPONSE_BYTES = 1024 * 1024
STATUSES = frozenset(('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REJECTED'))
_TOKEN = re.compile(r'[A-Za-z0-9._~-]{1,128}', re.ASCII)
_KEY = re.compile(r'[A-Za-z0-9._~-]{1,128}', re.ASCII)
_CODE = _TOKEN


class SyncConfigError(ValueError):
    """Invalid local input or explicit network gate not enabled."""


class SyncTransportError(RuntimeError):
    """Safe diagnostics only; never retain a response body or request URL."""
    def __init__(self, *, http_status=None, code='TRANSPORT_ERROR', generation_id=None,
                 outcome_unknown=False, retry_after=None):
        self.http_status = http_status if type(http_status) is int else None
        self.code = code if isinstance(code, str) and _CODE.fullmatch(code) else 'PROVIDER_ERROR'
        self.generation_id = generation_id if isinstance(generation_id, str) and _valid_id(generation_id) else None
        self.outcome_unknown = bool(outcome_unknown)
        self.retry_after = retry_after if _number(retry_after, positive=False) else None
        super().__init__('Sync request failed (' + self.code + ')')


class SyncProtocolError(SyncTransportError):
    """Malformed, oversized or incompatible provider response."""


def _valid_id(value):
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value)) and value not in ('.', '..')


def _number(value, positive=True):
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def _https(value):
    try:
        if not isinstance(value, str) or not value or len(value) > 16384:
            raise ValueError()
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or '\\' in value:
            raise ValueError()
        value.encode('utf-8')
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        host = host.lower().rstrip('.')
        if host == 'localhost' or host.endswith(('.localhost', '.local')) or '%' in host:
            raise ValueError()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            ascii_host = host.encode('idna').decode('ascii')
            if '.' not in ascii_host or re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*', ascii_host, re.I):
                raise ValueError()
            if not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in ascii_host.split('.')):
                raise ValueError()
        else:
            if not literal.is_global:
                raise ValueError()
    except (ValueError, UnicodeError, TypeError):
        raise SyncConfigError('Expected a public HTTPS media URL without credentials') from None
    return value


def validate_generation_request(payload):
    """Copy a strict documented subset without changing URL text or input order."""
    if not isinstance(payload, dict) or set(payload) - {'model', 'input', 'outputFileName'}:
        raise SyncConfigError('Unsupported generation fields')
    if payload.get('model') != 'sync-3':
        raise SyncConfigError('Only sync-3 is supported')
    inputs = payload.get('input')
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise SyncConfigError('Exactly one visual input and one audio input are required')
    copied = []
    types = []
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {'type', 'url'} or item.get('type') not in ('image', 'video', 'audio'):
            raise SyncConfigError('Unsupported generation input')
        types.append(item['type'])
        copied.append({'type': item['type'], 'url': _https(item['url'])})
    if types.count('audio') != 1 or sum(kind in ('image', 'video') for kind in types) != 1:
        raise SyncConfigError('Exactly one visual input and one audio input are required')
    result = {'model': 'sync-3', 'input': copied}
    if 'outputFileName' in payload:
        name = payload['outputFileName']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', name, re.ASCII):
            raise SyncConfigError('Invalid output filename')
        result['outputFileName'] = name
    return result


def build_generation_request(*, visual_type, visual_url, audio_url, model='sync-3', output_file_name=None):
    if visual_type not in ('image', 'video'):
        raise SyncConfigError('Visual type must be image or video')
    result = {'model': model, 'input': [{'type': visual_type, 'url': visual_url}, {'type': 'audio', 'url': audio_url}]}
    if output_file_name is not None:
        result['outputFileName'] = output_file_name
    return validate_generation_request(result)


def normalize_generation(payload):
    if not isinstance(payload, dict):
        raise SyncProtocolError(code='INVALID_GENERATION')
    identifier, status = payload.get('id'), payload.get('status')
    if not _valid_id(identifier) or not isinstance(status, str) or status not in STATUSES:
        raise SyncProtocolError(code='INVALID_GENERATION')
    output = payload.get('outputUrl')
    if output == '':
        output = None
    if output is not None:
        try:
            output = _https(output)
        except SyncConfigError:
            raise SyncProtocolError(code='INVALID_OUTPUT_URL') from None
    error_code = payload.get('errorCode')
    if error_code in (None, ''):
        error_code = None
    elif not isinstance(error_code, str) or not _CODE.fullmatch(error_code):
        raise SyncProtocolError(code='INVALID_ERROR_CODE')
    return {'id': identifier, 'status': status, 'output_url': output,
            'output_available': status == 'COMPLETED' and output is not None, 'error_code': error_code}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(method, url, headers, body, timeout):
    # Disable ambient proxies; never forward authenticated requests on redirect.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(url, data=body, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SyncProtocolError(code='RESPONSE_TOO_LARGE')
        return response.code, dict(response.headers), raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _reject_number(value):
    raise ValueError()


def _integer(value):
    # Bound conversion explicitly, including Python versions before 3.11.
    if len(value) > 128:
        raise ValueError()
    return int(value)


def _float(value):
    if len(value) > 128:
        raise ValueError()
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError()
    return parsed


def _decode(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise SyncProtocolError(code='INVALID_RESPONSE_SIZE')
    try:
        value = json.loads(raw.decode('utf-8'), parse_constant=_reject_number,
                           parse_float=_float, parse_int=_integer, object_pairs_hook=_pairs)
        if not isinstance(value, dict):
            raise ValueError()
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise SyncProtocolError(code='INVALID_JSON') from None


class SyncClient:
    def __init__(self, api_key=None, *, allow_live=False, transport=None, timeout=15, max_attempts=2, sleep=time.sleep):
        if type(allow_live) is not bool or not _number(timeout) or timeout > 120:
            raise SyncConfigError('Invalid client configuration')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 5 or not callable(sleep):
            raise SyncConfigError('Invalid retry configuration')
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip() or any(ord(c) < 33 or ord(c) > 126 for c in api_key)):
            raise SyncConfigError('Invalid API credential')
        if transport is not None and not callable(transport):
            raise SyncConfigError('Invalid transport')
        self._api_key, self._allow_live = api_key, allow_live
        self._transport, self._timeout = transport or _urllib_transport, timeout
        self._max_attempts, self._sleep = max_attempts, sleep

    @classmethod
    def from_env(cls):
        if os.environ.get('RAP_ENABLE_SYNC_CLIENT') != '1':
            raise SyncConfigError('Sync client network gate is disabled')
        key = os.environ.get('SYNC_API_KEY')
        if not key or not key.strip():
            raise SyncConfigError('SYNC_API_KEY is required')
        return cls(key, allow_live=True)

    def _request(self, method, path, payload=None, key=None, create=False):
        if not self._allow_live or not self._api_key:
            raise SyncConfigError('Sync client requires explicit network opt-in and a credential')
        headers = {'x-api-key': self._api_key, 'Accept': 'application/json'}
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if key is not None:
            headers['Idempotency-Key'] = key
        uncertain, remote = False, None
        for attempt in range(self._max_attempts):
            retry = False
            status = None
            try:
                status, response_headers, raw = self._transport(method, API_ORIGIN + path, dict(headers), body, self._timeout)
                if type(status) is not int or not 100 <= status <= 599 or not isinstance(response_headers, dict):
                    raise SyncProtocolError(code='INVALID_HTTP_RESPONSE')
                retry_after = next((value for name, value in response_headers.items() if str(name).lower() == 'retry-after'), None)
                try:
                    retry_after = float(retry_after)
                except (ValueError, TypeError, OverflowError):
                    retry_after = None
                if not _number(retry_after, positive=False):
                    retry_after = None
                if 300 <= status < 400:
                    raise SyncTransportError(http_status=status, code='REDIRECT_REJECTED', outcome_unknown=uncertain)
                data = _decode(raw)
                if status in ((200, 201) if create else (200,)):
                    return data
                code = data.get('errorCode') or data.get('code') or 'PROVIDER_ERROR'
                if not isinstance(code, str) or not _CODE.fullmatch(code) or self._api_key in code:
                    code = 'PROVIDER_ERROR'
                candidate = data.get('generationId')
                if _valid_id(candidate) and self._api_key not in candidate:
                    remote = candidate
                retry = status in (408, 429, 500, 502, 503, 504) or (status == 409 and code == 'IDEMPOTENCY_IN_PROGRESS')
                uncertain = uncertain or (create and (status in (408, 500, 502, 503, 504) or code == 'IDEMPOTENCY_OUTCOME_UNKNOWN'))
                failure = SyncTransportError(http_status=status, code=code, generation_id=remote,
                                             outcome_unknown=uncertain, retry_after=retry_after)
            except SyncTransportError as error:
                safe_code = error.code if self._api_key not in error.code else 'PROVIDER_ERROR'
                failure_type = SyncProtocolError if isinstance(error, SyncProtocolError) else SyncTransportError
                failure = failure_type(http_status=error.http_status or status, code=safe_code,
                                       generation_id=remote, outcome_unknown=uncertain or create,
                                       retry_after=error.retry_after)
                # Invalid data or redirects never trigger another request.
                retry = False
            except Exception:
                uncertain = uncertain or create
                failure = SyncTransportError(code='TRANSPORT_ERROR', generation_id=remote, outcome_unknown=uncertain)
                retry = True
            if not retry or attempt + 1 >= self._max_attempts or (failure.retry_after is not None and failure.retry_after > 30):
                raise failure from None
            try:
                self._sleep(min(failure.retry_after if failure.retry_after is not None else 0.25 * (2 ** attempt), 30))
            except Exception:
                raise failure from None
        raise SyncTransportError(code='RETRY_EXHAUSTED', outcome_unknown=uncertain)

    def _normalize(self, data):
        snapshot = normalize_generation(data)
        if self._api_key in snapshot['id']:
            raise SyncProtocolError(code='INVALID_GENERATION')
        if snapshot['error_code'] and self._api_key in snapshot['error_code']:
            snapshot['error_code'] = 'REDACTED'
        return snapshot

    def create(self, payload, idempotency_key):
        if not isinstance(idempotency_key, str) or not _KEY.fullmatch(idempotency_key):
            raise SyncConfigError('A valid persisted Idempotency-Key is required')
        payload = validate_generation_request(payload)
        data = self._request('POST', '/v2/generate', payload, idempotency_key, create=True)
        try:
            return self._normalize(data)
        except SyncProtocolError:
            raise SyncProtocolError(code='INVALID_GENERATION', outcome_unknown=True) from None

    def get(self, generation_id):
        if not _valid_id(generation_id) or (self._api_key and self._api_key in generation_id):
            raise SyncConfigError('Invalid generation identifier')
        snapshot = self._normalize(self._request('GET', '/v2/generate/' + generation_id))
        if snapshot['id'] != generation_id:
            raise SyncProtocolError(code='GENERATION_ID_MISMATCH', generation_id=generation_id)
        return snapshot

    def estimate(self, duration, fps=30, reasoning_enabled=False, model='sync-3'):
        if model != 'sync-3' or not _number(duration) or not _number(fps) or type(reasoning_enabled) is not bool:
            raise SyncConfigError('Invalid estimate parameters')
        data = self._request('POST', '/v2/generations/estimate',
                             {'model': model, 'duration': duration, 'fps': fps, 'reasoningEnabled': reasoning_enabled})
        fields = ('estimatedFrameCount', 'estimatedGenerationCost', 'estimatedCredits')
        if any(name not in data for name in fields):
            raise SyncProtocolError(code='INVALID_ESTIMATE')
        for name in fields:
            if name == 'estimatedCredits' and data[name] is None:
                continue
            if not _number(data[name], positive=False):
                raise SyncProtocolError(code='INVALID_ESTIMATE')
        return {name: data[name] for name in fields}
