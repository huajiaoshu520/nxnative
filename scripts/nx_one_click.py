#!/usr/bin/env python3
"""Double-click frontend for upstream all-in-one IPA and standalone Mac app builds."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dm/local_one_click'))


def catalog(root=ROOT):
    # Read only shipped profiles. External/provisional profiles are not support claims.
    result = {}
    for path in sorted((root / 'dm/games').glob('*/game.tsv')):
        if not re.fullmatch(r'[0-9A-Fa-f]{16}', path.parent.name):
            continue
        rows = [[field.strip() for field in line.split('\t')] for line in path.read_text(encoding='utf-8').splitlines()
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
    if kind == 'keys':
        args = ['xcrun', 'swift', str(ROOT / 'dm/local_one_click/choose_keys.swift')]
    else:
        args = ['osascript', str(ROOT / 'dm/local_one_click/choose_inputs.applescript'), kind]
    response = subprocess.run(args, text=True, capture_output=True)
    if response.returncode:
        detail = response.stderr.strip()
        if response.returncode == 130 or '(-128)' in detail:
            raise ValueError('Selection cancelled. No build started.')
        raise ValueError('Cannot open the selection window: ' + (detail or str(response.returncode)))
    return Path(response.stdout.strip()).expanduser().resolve()


def clean_env():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for key in ('DM_GAMES_DIR', 'DM_GAMES_FIRST', 'DM_ENV_FILE', 'DM_ROOT', 'WORK',
                'PATCHED', 'ROMFS', 'MSL_IOS', 'DM_PATCH_FRONT', 'XLATE'):
        env.pop(key, None)
    return env


def command(game_dir, keys, output, package, language, platform_name="ios"):
    return [sys.executable, str(ROOT / 'scripts/build_ipa_from_nsp.py'), str(game_dir),
            '-k', str(keys), '-p', package, '-l', language, '--platform', platform_name,
            '--progress', 'lines', '-o', str(output)] + (['--mac-sign', '-'] if platform_name == 'mac-app' else [])


def publish_output(partial, target, mac=False):
    # The official process has already succeeded. Only check that its requested
    # output exists; do not impose a second resource/layout/signature policy.
    if not (partial.is_dir() if mac else partial.is_file()):
        raise ValueError('Official build returned success but no output was found: ' + str(partial))
    if target.exists():
        raise ValueError('Output already exists; not overwriting: ' + str(target))
    partial.rename(target)
    if not mac:
        from cleanup import cleanup_output_index
        cleanup_output_index(partial, target)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--select', action='store_true')
    ap.add_argument('--platform', choices=('ios', 'mac-app'), default='ios')
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
    from cleanup import build_lock
    with build_lock(game_dir):
        if not a.plan:
            # Re-exec with explicit choices: dependency setup never repeats the panels.
            import dependencies
            args = ['--game-dir', str(game_dir), '--keys', str(keys), '--output-dir', str(output),
                    '--language', a.language, '--platform', a.platform] + (['--package', a.package] if a.package else [])
            dependencies.ensure(game_dir, Path(__file__).resolve(), args, mac=a.platform == 'mac-app')
        from containers import normalize
        prepared_dir = normalize(game_dir, keys, plan=a.plan)
        if isinstance(prepared_dir, dict):
            print(json.dumps(prepared_dir, indent=2))
            return
        entry, chosen, family = select_inputs(prepared_dir, a.package)
        if a.plan:
            print(json.dumps(dict(game=entry, package=chosen, game_dir=str(game_dir), output=str(output),
                                  language=a.language, platform=a.platform, dlc_packages=len(family['dlc'])), indent=2, ensure_ascii=False))
            return
        output.mkdir(parents=True, exist_ok=True)
        work = game_dir / '.nxnative-one-click'
        work.mkdir(exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
        job = work / stamp
        job.mkdir()
        # Build into the destination volume; publish only after validation. No overwrite.
        name = Path(entry['ipa']).stem
        mac = a.platform == 'mac-app'
        target = output / (name + '-' + chosen + '-' + stamp + ('.app' if mac else '-unsigned.ipa'))
        partial = output / ('.' + target.stem + ('.partial.app' if mac else '.partial.ipa'))
        cmd = command(prepared_dir, keys, partial, chosen, a.language, a.platform)
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
        publish_output(partial, target, mac)
        from cleanup import cleanup_success
        cleanup_success(game_dir, prepared_dir, entry['id'], target, keys)
        print('\nDone: ' + str(target))
        if mac:
            print('Standalone Mac app with embedded game resources. Double-click to run on a supported Apple Silicon Mac.')
        else:
            print('Unsigned all-in-one IPA: no external .data pack. Sign the complete IPA yourself.')
        print('No game files were uploaded. A future build will recreate its dependencies and caches.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelled; inputs and previous outputs retained.', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print('\nError: ' + str(error), file=sys.stderr)
        sys.exit(1)
