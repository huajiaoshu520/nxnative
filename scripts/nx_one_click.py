#!/usr/bin/env python3
"""Double-click frontend for the upstream all-in-one IPA pipeline."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dm/local_one_click'))


def catalog(root=ROOT):
    # Read only shipped profiles. External/provisional profiles are not support claims.
    result = {}
    for path in sorted((root / 'dm/games').glob('*/game.tsv')):
        if not re.fullmatch(r'[0-9A-Fa-f]{16}', path.parent.name):
            continue
        rows = [line.split('\t') for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#')]
        fields = {r[0]: r[1:] for r in rows}
        builds = {r[1]: r[2] for r in rows if r[0] == 'build' and len(r) >= 3}
        if not builds:
            continue
        tid = fields['title_id'][0].upper()
        result[tid] = dict(id=tid, name=fields['name'][0], builds=builds,
                           shader_versions=fields.get('shader_versions', [''])[0].split(),
                           ipa=fields['ipa'][0], marker=fields.get('romfs_marker', [''])[0])
    return result


def pipeline():
    spec = importlib.util.spec_from_file_location('nx_official_pipeline', ROOT / 'scripts/build_ipa_from_nsp.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_inputs(game_dir, package=None):
    official = pipeline()
    tid, family = official.scan_nsps(game_dir)
    entry = catalog().get(f'{tid:016X}')
    if not entry:
        raise ValueError('No shipped game profile for this title. See --list-games; the official CLI can survey unknown games.')
    builds = {key: {'display': value} for key, value in entry['builds'].items()}
    have = official.nsp_versions(family, builds)
    chosen = package or max(have, key=official.vnum)
    if chosen not in have:
        raise ValueError('The selected update is absent from the input folder: ' + chosen)
    print('Detected package: ' + chosen + '; registered builds: ' +
          ', '.join(k + ' (' + v + ')' for k, v in entry['builds'].items()), flush=True)
    if chosen not in entry['builds']:
        print('Note: this package is not registered. The official pipeline will derive a profile from its own files; registered-version fixes may not apply and gameplay is untested.', flush=True)
    missing = [v for v in entry['shader_versions'] if v not in have]
    # Like the official CLI, absent shader source versions can use a derived profile.
    if missing:
        print('Note: shader-source versions absent: ' + ', '.join(missing) +
              '. The official pipeline will derive tables from the selected version.', flush=True)
    return entry, chosen, family


def pick(kind):
    response = subprocess.run(['osascript', str(ROOT / 'dm/local_one_click/choose_inputs.applescript'), kind],
                              text=True, capture_output=True)
    if response.returncode:
        detail = response.stderr.strip()
        if '(-128)' in detail:
            raise ValueError('Selection cancelled. No build started.')
        raise ValueError('Cannot open the selection window: ' + (detail or str(response.returncode)))
    return Path(response.stdout.strip()).expanduser().resolve()


def clean_env():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for key in ('DM_GAMES_DIR', 'DM_GAMES_FIRST', 'DM_ENV_FILE', 'DM_ROOT', 'WORK',
                'PATCHED', 'ROMFS', 'MSL_IOS', 'DM_PATCH_FRONT', 'XLATE'):
        env.pop(key, None)
    return env


def command(game_dir, keys, output, package, language):
    return [sys.executable, str(ROOT / 'scripts/build_ipa_from_nsp.py'), str(game_dir),
            '-k', str(keys), '-p', package, '-l', language, '--platform', 'ios',
            '--progress', 'lines', '-o', str(output)]


def verify_ipa(path, entry, expected_display=None):
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('IPA CRC failed: ' + bad)
        names = set(archive.namelist())
        infos = [n for n in names if re.fullmatch(r'Payload/[^/]+\.app/Info.plist', n)]
        if len(infos) != 1:
            raise ValueError('IPA must contain exactly one application.')
        info = plistlib.loads(archive.read(infos[0]))
        prefix = infos[0][:-len('Info.plist')]
        if info.get('CFBundleIdentifier') != 'org.nxnative.' + entry['id'].lower():
            raise ValueError('Unexpected application identifier.')
        executable = info.get('CFBundleExecutable', '')
        if not executable or '/' in executable or prefix + executable not in names:
            raise ValueError('Missing application executable.')
        if entry['marker'] and prefix + 'romfs/' + entry['marker'] not in names:
            raise ValueError('IPA lacks the profile RomFS marker.')
        if not any(n.startswith(prefix + 'msl/') and n.endswith('.metallib') for n in names):
            raise ValueError('IPA lacks embedded iOS shader libraries.')
        if not any(n.startswith(prefix + 'romfs/') for n in names):
            raise ValueError('IPA lacks embedded RomFS.')
        if any(n.startswith(prefix) and (n.endswith('/embedded.mobileprovision') or '/_CodeSignature/' in n) for n in names):
            raise ValueError('Expected an unsigned IPA.')
        # Registered versions describe known builds; NACP is the actual app version.
        return dict(bundle_id=info['CFBundleIdentifier'], version=info.get('CFBundleShortVersionString'),
                    registered_version=expected_display)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--select', action='store_true')
    ap.add_argument('--list-games', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--plan', action='store_true', help='inspect inputs without installing or building')
    ap.add_argument('--game-dir', type=Path)
    ap.add_argument('--keys', type=Path)
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--package', help='package present in the folder, e.g. v2228224 or v0')
    ap.add_argument('--language', default='en-US', help='same language codes as the official CLI')
    a = ap.parse_args(argv)
    if a.list_games:
        entries = list(catalog().values())
        if a.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False))
        else:
            for e in entries:
                print(e['id'] + '  ' + e['name'] + '  ' + ', '.join(k + '=' + v for k, v in e['builds'].items()))
            print(str(len(entries)) + ' shipped profiles; registration is not a promise of complete iOS gameplay.')
        return
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Building requires an Apple Silicon Mac with full Xcode.')
    if not a.select and not all((a.game_dir, a.keys, a.output_dir)):
        ap.error('provide --game-dir, --keys and --output-dir, or use --select')
    game_dir = (a.game_dir or pick('game')).expanduser().resolve()
    keys = (a.keys or pick('keys')).expanduser().resolve()
    output = (a.output_dir or pick('output')).expanduser().resolve()
    if not game_dir.is_dir() or not keys.is_file() or keys.name != 'prod.keys':
        raise ValueError('Select a game folder and your prod.keys file.')
    if game_dir == ROOT or ROOT in game_dir.parents or keys == ROOT or ROOT in keys.parents:
        raise ValueError('Keep game files and keys outside the source repository.')
    if not a.plan:
        # Re-exec with explicit choices: dependency setup never repeats the panels.
        import dependencies
        args = ['--game-dir', str(game_dir), '--keys', str(keys), '--output-dir', str(output),
                '--language', a.language] + (['--package', a.package] if a.package else [])
        dependencies.ensure(game_dir, Path(__file__).resolve(), args)
    entry, chosen, family = select_inputs(game_dir, a.package)
    if a.plan:
        print(json.dumps(dict(game=entry, package=chosen, game_dir=str(game_dir), output=str(output),
                              language=a.language, dlc_packages=len(family['dlc'])), indent=2, ensure_ascii=False))
        return
    output.mkdir(parents=True, exist_ok=True)
    work = game_dir / '.nxnative-one-click'
    work.mkdir(exist_ok=True)
    with (work / 'build.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another one-click build is using this game folder.')
        stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
        job = work / stamp
        job.mkdir()
        # Build into the destination volume; publish only after validation. No overwrite.
        name = Path(entry['ipa']).stem
        target = output / (name + '-' + chosen + '-' + stamp + '-unsigned.ipa')
        partial = output / ('.' + target.name + '.partial.ipa')
        cmd = command(game_dir, keys, partial, chosen, a.language)
        env = clean_env()
        print('Game: ' + entry['name'] + ' / ' + entry['builds'].get(chosen, chosen + ' (unregistered)'), flush=True)
        print('Log: ' + str(job / 'build.log'), flush=True)
        with (job / 'build.log').open('w') as log:
            with subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
                for line in proc.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
                    log.flush()
                if proc.wait():
                    raise ValueError('Official build failed. Log and caches retained: ' + str(job))
        info = verify_ipa(partial, entry, entry['builds'].get(chosen))
        checksum = digest(partial)
        partial.rename(target)
        target.with_suffix('.ipa.sha256').write_text(checksum + '  ' + target.name + '\n')
        try:
            source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            source = 'source archive (no Git metadata)'
        manifest = dict(info, game=entry['id'], package=chosen, language=a.language,
                        source_commit=source, sha256=checksum, embedded_resources=True,
                        dlc_packages=len(family['dlc']), official_script='scripts/build_ipa_from_nsp.py')
        target.with_suffix('.ipa.json').write_text(json.dumps(manifest, indent=2))
        print('\nDone: ' + str(target))
        print('Unsigned all-in-one IPA: no external .data pack. Sign the complete IPA yourself.')
        print('Inputs, outputs, logs and official caches are retained. No game files were uploaded.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelled; inputs and previous outputs retained.', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print('\nError: ' + str(error), file=sys.stderr)
        sys.exit(1)
