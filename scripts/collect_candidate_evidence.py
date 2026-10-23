#!/usr/bin/env python3
"""Public snapshots via Agent Reach/Jina; --ids limits incremental collection."""
import argparse
import concurrent.futures
import datetime
import hashlib
import ipaddress
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUT = Path.home() / '.agent-reach' / 'ai-rap-video-20261023'


def validate_candidate(site):
    if (not isinstance(site, dict) or not isinstance(site.get('id'), str)
            or not re.fullmatch(r'[0-9]{2}', site['id'])):
        raise ValueError('candidate id must contain two ASCII digits')
    url = site.get('url')
    if not isinstance(url, str) or re.search(r'[\s\\\x00-\x1f\x7f]', url):
        raise ValueError('candidate URL must be an absolute public HTTP(S) URL')
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').rstrip('.').lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError('invalid candidate URL') from exc
    if (parsed.scheme not in ('http', 'https') or not host or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port == 0):
        raise ValueError('candidate URL requires HTTP(S), host, and no credentials or fragment')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        labels = host.encode('idna').decode('ascii').split('.')
        if (len(labels) < 2 or host.endswith(('.localhost', '.local', '.internal'))
                or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
            raise ValueError('candidate URL requires a public hostname')
    else:
        if not address.is_global:
            raise ValueError('candidate URL cannot use a non-public IP address')
    return site


def parse_ids(value):
    values = [part.strip() for part in value.split(',')]
    if not values or any(not re.fullmatch(r'[0-9]{2}', item) for item in values):
        raise argparse.ArgumentTypeError('--ids must be comma-separated two-digit IDs, e.g. 41,42')
    if len(set(values)) != len(values):
        raise argparse.ArgumentTypeError('--ids contains duplicate IDs')
    return values


def select_candidates(sites, ids=None):
    known = {}
    for site in sites:
        validate_candidate(site)
        if site['id'] in known:
            raise ValueError('duplicate candidate id: ' + site['id'])
        known[site['id']] = site
    if ids is None:
        return list(known.values())
    missing = set(ids) - known.keys()
    if missing:
        raise ValueError('unknown candidate IDs: ' + ', '.join(sorted(missing)))
    return [known[site_id] for site_id in ids]


def classify_content(content, returncode=0, http_status=None):
    """Classify response bodies, never treating HTTP success as product evidence."""
    if returncode or not content.strip():
        return 'inaccessible'
    if http_status is not None and http_status >= 400:
        return 'error_page'
    if re.search(r'Warning: Target URL returned error|SecurityCompromiseError|AuthenticationRequiredError|HTTP Error [45][0-9]{2}', content, re.I):
        return 'error_page'
    headings = '\n'.join(line for line in content[:5000].splitlines()
                         if re.match(r'^\s*(Title:|#{1,3}\s)', line, re.I))
    errors = r'(?:404|403|500|502|503|page not found|not found|access denied|forbidden|bad gateway|service unavailable|security checkpoint|vercel security checkpoint|just a moment|please enable javascript|cloudflare)'
    if re.search(r'^\s*(?:Title:|#{1,3})\s*(?:Error[:\s-]*)?' + errors + r'\b', headings, re.I | re.M):
        return 'error_page'
    if re.search(r'^\s*(?:Title:|#{1,3})\s*(?:sign in|log in|login|authentication required)\b', headings, re.I | re.M):
        return 'login_required'
    if len(content.strip()) < 900:
        if re.fullmatch(r'\s*(?:sign in|log in|login required)[.!\s]*', content, re.I):
            return 'login_required'
        if re.fullmatch(r'\s*(?:' + errors + r')[.!\s]*', content, re.I):
            return 'error_page'
        return 'needs_review'
    return 'readable'


def collect(site, output_dir=OUT):
    validate_candidate(site)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    content, error, code, http_status = '', '', 1, None
    marker = '\n__EVIDENCE_HTTP_STATUS__:'
    try:
        result = subprocess.run(['curl', '-L', '--max-time', '55', '-sS', '--write-out',
                                 marker + '%{http_code}', 'https://r.jina.ai/' + site['url']],
                                capture_output=True, text=True, timeout=60)
        content, error, code = result.stdout, result.stderr, result.returncode
        if marker in content:
            content, raw_status = content.rsplit(marker, 1)
            if raw_status.strip().isdigit():
                http_status = int(raw_status.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
        raw = getattr(exc, 'stdout', '') or ''
        content = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
    path = output_dir / (site['id'] + '.txt')
    path.write_text(content, encoding='utf-8')
    meta = {**site, 'started_at': started,
            'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': classify_content(content, code, http_status), 'returncode': code,
            'http_status': http_status, 'bytes': len(content.encode('utf-8')),
            'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
            'local_path': str(path), 'error': error}
    (output_dir / (site['id'] + '.meta.json')).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'id': site['id'], 'status': meta['status'], 'bytes': meta['bytes']}), flush=True)
    return meta


def merge_index(existing, results):
    merged = {entry['id']: entry for entry in existing}
    merged.update({entry['id']: entry for entry in results})
    return [merged[key] for key in sorted(merged)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', type=parse_ids, help='Only fetch these IDs, e.g. 41,42')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 32:
        parser.error('--workers must be between 1 and 32')
    try:
        sites = select_candidates(json.loads((ROOT / 'research/candidates.json').read_text(encoding='utf-8')), args.ids)
        index_path = args.output_dir / 'index.json'
        existing = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else []
        if not isinstance(existing, list):
            raise ValueError('existing index must be an array')
        # Validate the index before networking, so malformed history is never overwritten.
        merge_index(existing, [])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda site: collect(site, args.output_dir), sites))
    index_path.write_text(json.dumps(merge_index(existing, results), ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
