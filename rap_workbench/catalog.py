"""Validated research catalog. No network access or third-party dependencies."""
import datetime
import ipaddress
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

CATEGORIES = ('rap', 'music_video', 'lip_sync', 'music', 'video', 'editor')
API_STATUSES = ('documented', 'not_found', 'unknown')
EVIDENCE_STATUSES = ('full_page', 'partial', 'inaccessible')
SOURCE_KINDS = ('official', 'documentation', 'pricing', 'secondary')
REQUIRED = ('id', 'name', 'url', 'category', 'checked_at', 'summary', 'inputs',
            'outputs', 'features', 'pricing', 'api', 'limitations', 'best_for',
            'evidence_status', 'sources', 'observations')
# A bounded stdlib approximation, not a Public Suffix List implementation.
MULTIPART_SUFFIXES = {'co.uk', 'org.uk', 'com.au', 'net.au', 'co.jp', 'co.nz',
                      'com.cn', 'com.hk', 'com.tw', 'co.in', 'com.br', 'co.kr',
                      'github.io', 'pages.dev', 'vercel.app', 'netlify.app'}


class CatalogValidationError(ValueError):
    """A record or evidence file violates the research contract."""


def _fail(field, message):
    raise CatalogValidationError('{}: {}'.format(field, message))


def _text(value, field, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail(field, 'expected {}string'.format('' if empty else 'nonempty '))


def _strings(value, field):
    if not isinstance(value, list):
        _fail(field, 'expected array of strings')
    for index, item in enumerate(value):
        _text(item, '{}[{}]'.format(field, index))


def _url(value, field, empty=False):
    _text(value, field, empty=empty)
    if empty and not value:
        return
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        _fail(field, 'invalid HTTP(S) URL')
    if parsed.scheme not in ('http', 'https') or not hostname or parsed.username or parsed.password:
        _fail(field, 'expected absolute HTTP(S) URL without credentials')


def _domain(record):
    host = (urlsplit(record['url']).hostname or '').lower().rstrip('.')
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.split('.')
    suffix = '.'.join(labels[-2:])
    count = 3 if suffix in MULTIPART_SUFFIXES else 2
    return '.'.join(labels[-count:])


def _error_page(title, content):
    # Restrict error detection to page metadata/headings so a legitimate pricing
    # FAQ mentioning an error or login does not invalidate its whole source.
    bad = r'(?:404|403|502|503|page not found|not found|access denied|forbidden|bad gateway|service unavailable|security checkpoint|just a moment|sign in|log in|login required)'
    if re.search(r'^\s*(?:title:\s*)?(?:error[ :\-]*)?' + bad + r'\b', title, re.I):
        return True
    if re.fullmatch(r'\s*' + bad + r'[.!\s]*', content, re.I):
        return True
    if re.search(r'(?:Warning: Target URL returned error|HTTP/[\d.]+\s+[45]\d\d|^HTTP Error\s+[45]\d\d)', content, re.I | re.M):
        return True
    for line in content[:3000].splitlines():
        if re.match(r'^\s*(?:Title:|#{1,3})\s*' + bad + r'\b', line, re.I):
            return True
    return False


def validate_site(record, root):
    """Return record unchanged, or raise CatalogValidationError with its field.

    ``root`` is the repository directory. Evidence must be a relative path to
    an existing regular file whose resolved target remains inside that root.
    """
    if not isinstance(record, dict):
        _fail('record', 'expected object')
    missing = [field for field in REQUIRED if field not in record]
    if missing:
        _fail('record', 'missing required fields: ' + ', '.join(missing))
    if not isinstance(record['id'], str) or not re.fullmatch(r'\d{2}', record['id'], re.ASCII):
        _fail('id', 'expected two ASCII digits')
    for field in ('name', 'summary', 'best_for'):
        _text(record[field], field)
    _url(record['url'], 'url')
    for field, choices in (('category', CATEGORIES), ('evidence_status', EVIDENCE_STATUSES)):
        if record[field] not in choices:
            _fail(field, 'expected one of ' + ', '.join(choices))
    _text(record['checked_at'], 'checked_at')
    try:
        parsed_date = datetime.date.fromisoformat(record['checked_at'])
        if parsed_date.isoformat() != record['checked_at']:
            raise ValueError()
    except ValueError:
        _fail('checked_at', 'expected ISO date YYYY-MM-DD')
    for field in ('inputs', 'outputs', 'features', 'limitations', 'observations'):
        _strings(record[field], field)
    pricing = record['pricing']
    if not isinstance(pricing, dict):
        _fail('pricing', 'expected object')
    for field in ('summary', 'free_tier'):
        _text(pricing.get(field), 'pricing.' + field)
    _url(pricing.get('source_url'), 'pricing.source_url', empty=True)
    if not isinstance(pricing.get('plans'), list):
        _fail('pricing.plans', 'expected array')
    for index, plan in enumerate(pricing['plans']):
        prefix = 'pricing.plans[{}]'.format(index)
        if not isinstance(plan, dict):
            _fail(prefix, 'expected object')
        for field in ('name', 'currency', 'billing_period', 'notes'):
            if field in plan:
                _text(plan[field], prefix + '.' + field)
        if 'credits' in plan and isinstance(plan['credits'], str):
            _text(plan['credits'], prefix + '.credits')
        for field in ('amount', 'credits'):
            if field in plan:
                value = plan[field]
                if field == 'credits' and isinstance(value, str):
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    _fail(prefix + '.' + field, 'expected finite nonnegative number')
    api = record['api']
    if not isinstance(api, dict):
        _fail('api', 'expected object')
    if api.get('status') not in API_STATUSES:
        _fail('api.status', 'expected documented, not_found, or unknown')
    _text(api.get('summary'), 'api.summary')
    if 'url' not in api:
        _fail('api.url', 'missing required field')
    if api['url'] is not None or api['status'] == 'documented':
        _url(api['url'], 'api.url', empty=api['status'] != 'documented')
    sources = record['sources']
    if not isinstance(sources, list):
        _fail('sources', 'expected array')
    root = Path(root).resolve()
    primary = False
    for index, source in enumerate(sources):
        prefix = 'sources[{}]'.format(index)
        if not isinstance(source, dict):
            _fail(prefix, 'expected object')
        _url(source.get('url'), prefix + '.url')
        _text(source.get('title'), prefix + '.title')
        if source.get('kind') not in SOURCE_KINDS:
            _fail(prefix + '.kind', 'unknown source kind')
        _strings(source.get('supports'), prefix + '.supports')
        _text(source.get('local_path'), prefix + '.local_path')
        path = Path(source['local_path'])
        if path.is_absolute():
            _fail(prefix + '.local_path', 'must be relative to repository')
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            _fail(prefix + '.local_path', 'escapes repository')
        if not resolved.is_file():
            _fail(prefix + '.local_path', 'evidence file does not exist')
        try:
            content = resolved.read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            _fail(prefix + '.local_path', 'cannot read evidence: ' + str(exc))
        if source['kind'] != 'secondary' and content.strip() and not _error_page(source['title'], content):
            primary = True
    if record['evidence_status'] == 'full_page' and not primary:
        _fail('evidence_status', 'full_page requires a non-error primary source file')
    try:
        json.dumps(record, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        _fail('record', 'not JSON serializable: ' + str(exc))
    return record


def load_sites(root):
    """Load every site, fail clearly on malformed data or duplicate identity."""
    root = Path(root).resolve()
    directory = root / 'research' / 'sites'
    if not directory.is_dir():
        _fail('research/sites', 'catalog directory does not exist')
    sites, ids, domains = [], set(), set()
    for path in sorted(directory.glob('*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            validate_site(record, root)
            if path.stem != record['id']:
                _fail('id', 'does not match filename ' + path.name)
            domain = _domain(record)
            if record['id'] in ids:
                _fail('id', 'duplicate ' + record['id'])
            if domain in domains:
                _fail('url', 'duplicate primary domain ' + domain)
            ids.add(record['id'])
            domains.add(domain)
            sites.append(record)
        except (OSError, ValueError) as exc:
            raise CatalogValidationError('{}: {}'.format(path.name, exc)) from exc
    return sorted(sites, key=lambda site: site['id'])


def filter_sites(sites, query='', category='', api_status='', evidence_status=''):
    """Case-insensitive text search plus exact AND-combined filters."""
    for field, value, choices in (('category', category, CATEGORIES), ('api_status', api_status, API_STATUSES),
                                   ('evidence_status', evidence_status, EVIDENCE_STATUSES)):
        if value and value not in choices:
            _fail(field, 'unknown filter value')
    if not isinstance(query, str):
        _fail('query', 'expected string')
    needle = query.strip().casefold()
    return [site for site in sites
            if (not category or site['category'] == category)
            and (not api_status or site['api']['status'] == api_status)
            and (not evidence_status or site['evidence_status'] == evidence_status)
            and (not needle or needle in json.dumps(site, ensure_ascii=False).casefold())]


def stats(sites):
    """Wire-format counts by primary domain, with the latest checked date.

    If called with duplicates directly, the first entry per domain wins.
    load_sites rejects duplicates so normal catalog data is unambiguous.
    """
    unique = {}
    for site in sites:
        unique.setdefault(_domain(site), site)
    values = list(unique.values())
    return {'total': len(values),
            'full_page': sum(site['evidence_status'] == 'full_page' for site in values),
            'by_category': dict(Counter(site['category'] for site in values)),
            'by_evidence': dict(Counter(site['evidence_status'] for site in values)),
            'by_api': dict(Counter(site['api']['status'] for site in values)),
            'checked_at': max((site['checked_at'] for site in values), default=None)}
