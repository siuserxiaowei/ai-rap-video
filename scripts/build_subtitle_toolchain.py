#!/usr/bin/env python3
"""Build verified libass/FFmpeg sources locally; no downloads or global links."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'libass': ('0.17.5', '2dca25c0e0c837ddf00b52011b3f82cac1e4ddd3ad018227806b0c2288864acc',
               'https://github.com/libass/libass/releases/download/0.17.5/libass-0.17.5.tar.xz'),
    'ffmpeg': ('8.1.1', 'b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3',
               'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz'),
}


def sha256(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='Directory containing the two verified upstream .tar.xz archives')
    parser.add_argument('--prefix', type=Path,
                        default=ROOT / '.workbench/toolchains/ass-ffmpeg-8.1.1')
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('This recorded build recipe targets macOS arm64 with Homebrew libraries.')
    prefix, artifacts = args.prefix.resolve(), args.artifact_dir.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    sources = args.source_dir.resolve()
    work = sources.parent / 'sources'
    work.mkdir(parents=True, exist_ok=True)
    state = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
             'prefix': str(prefix), 'architecture': platform.machine(), 'sources': [], 'steps': []}
    state_path = artifacts / 'toolchain-build.json'

    def save():
        state_path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

    for name, (version, expected, url) in SOURCES.items():
        archive = sources / f'{name}-{version}.tar.xz'
        actual = sha256(archive)
        if actual != expected:
            raise ValueError(f'Upstream archive checksum mismatch: {name}')
        state['sources'].append({'name': name, 'version': version, 'url': url,
                                 'archive_sha256': actual, 'archive_bytes': archive.stat().st_size})
        folder = work / f'{name}-{version}'
        if not folder.exists():
            # Python3.12+ supplies the extraction data filter. The application's
            # Python3.10 minimum does not apply to this local build helper.
            with tarfile.open(archive) as packed:
                packed.extractall(work, filter='data')
        if not (folder / 'configure').is_file():
            raise ValueError(f'Verified source archive has no configure script: {name}')
    save()

    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([str(prefix / 'bin'), '/opt/homebrew/bin', env.get('PATH', '')])
    search = [prefix / 'lib/pkgconfig', Path('/opt/homebrew/lib/pkgconfig'),
              Path('/opt/homebrew/share/pkgconfig')]
    search.extend(sorted(Path('/opt/homebrew/opt').glob('*/lib/pkgconfig')))
    env['PKG_CONFIG_PATH'] = os.pathsep.join(str(item) for item in search if item.is_dir())
    env['PKG_CONFIG'] = shutil.which('pkg-config', path=env['PATH']) or ''
    if not env['PKG_CONFIG']:
        raise ValueError('Install the recorded pkgconf prerequisite before building.')

    def run(label, command, directory, timeout=1200):
        log = artifacts / (label + '.txt')
        step = {'name': label, 'argv': command, 'cwd': str(directory),
                'log': str(log), 'status': 'running'}
        state['steps'].append(step)
        save()
        print(label, flush=True)
        with log.open('w') as output:
            result = subprocess.run(command, cwd=directory, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        step['exit_code'] = result.returncode
        step['status'] = 'passed' if result.returncode == 0 else 'failed'
        save()
        result.check_returncode()

    try:
        libass = work / 'libass-0.17.5'
        run('libass-configure', ['./configure', '--prefix=' + str(prefix),
                                 '--disable-shared', '--enable-static'], libass)
        run('libass-make', ['make', '-j' + str(args.jobs)], libass)
        run('libass-install', ['make', 'install'], libass)
        # libass.pc appears only after install, so include its directory now.
        env['PKG_CONFIG_PATH'] = str(prefix / 'lib/pkgconfig') + os.pathsep + env['PKG_CONFIG_PATH']
        ffmpeg = work / 'ffmpeg-8.1.1'
        run('ffmpeg-configure', ['./configure', '--prefix=' + str(prefix),
                                 '--disable-autodetect', '--disable-ffplay', '--disable-doc',
                                 '--disable-debug', '--disable-shared', '--enable-static',
                                 '--disable-network', '--enable-gpl', '--enable-libass',
                                 '--enable-libx264', '--pkg-config-flags=--static'], ffmpeg)
        run('ffmpeg-make', ['make', '-j' + str(args.jobs)], ffmpeg)
        run('ffmpeg-install', ['make', 'install'], ffmpeg)
        binary = prefix / 'bin/ffmpeg'
        filters = subprocess.run([str(binary), '-hide_banner', '-filters'], check=True,
                                 capture_output=True, text=True, timeout=30).stdout
        names = {parts[1] for line in filters.splitlines() if len(parts := line.split()) >= 2}
        if not {'ass', 'subtitles'} <= names:
            raise ValueError('Built FFmpeg lacks the required subtitle filters')
        state.update(status='passed', completed_at=datetime.now(timezone.utc).isoformat(),
                     capabilities={'ass': True, 'subtitles': True, 'network_disabled': True},
                     binaries={name: {'path': str(prefix / 'bin' / name),
                                      'sha256': sha256(prefix / 'bin' / name)}
                               for name in ('ffmpeg', 'ffprobe')})
        save()
        print(json.dumps({'status': state['status'], 'prefix': str(prefix)}), flush=True)
    except Exception:
        state['status'] = 'failed'
        save()
        raise


if __name__ == '__main__':
    main()
