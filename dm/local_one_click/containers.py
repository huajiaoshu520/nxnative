"""Read XCI CNMT and supply separate, unchanged-content NSPs to the official CLI."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'dm/local_one_click/xci_catalog'


def tool_digest():
    h = hashlib.sha256()
    for path in sorted(SOURCE.glob('*')):
        if path.suffix in ('.cs', '.csproj'):
            h.update(path.name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def build_tool(work, plan=False):
    target = work / 'container-tool'
    marker = target / 'source.sha256'
    binary = target / 'xci_catalog'
    key = tool_digest()
    if binary.is_file() and marker.is_file() and marker.read_text().strip() == key:
        return binary
    if plan:
        raise ValueError('XCI inspection tool has not been prepared. Run normally once to build the metadata tool, then --plan is available.')
    print('Preparing XCI metadata reader...', flush=True)
    # MSBuild output paths must not contain apostrophes. Publish in a temporary
    # directory then copy to the game drive, as the official nx_extract does.
    with tempfile.TemporaryDirectory(prefix='nx_xci_') as tmp:
        out = Path(tmp) / 'out'
        result = subprocess.run(['dotnet', 'build', str(SOURCE), '-c', 'Release', '-o', str(out),
                                 '--nologo', '-v', 'quiet'], capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Cannot build XCI metadata reader: ' + result.stdout + result.stderr)
        stage = work / ('container-tool-' + uuid.uuid4().hex)
        shutil.copytree(out, stage)
        (stage / 'source.sha256').write_text(key)
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    return binary


def run_tool(tool, keys, source, output=None):
    # Invoke the DLL through the selected SDK so read-only --plan also works
    # with a Homebrew SDK that has no system-wide apphost registration.
    args = [shutil.which('dotnet') or 'dotnet', str(tool.with_suffix('.dll')), str(keys), str(source)] + ([str(output)] if output else [])
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'XCI metadata reader failed.')
    try:
        titles = json.loads(result.stdout)
    except ValueError:
        raise ValueError('XCI metadata reader returned invalid JSON.') from None
    if not isinstance(titles, list) or not titles:
        raise ValueError('XCI has no supported application metadata.')
    return titles


def normalize(game_dir, keys, plan=False):
    sources = sorted(p for p in game_dir.iterdir() if p.is_file() and p.suffix.lower() == '.xci')
    if not sources:
        return game_dir
    if len(sources) != 1:
        raise ValueError('Keep one integrated XCI per game folder; external NSP updates and DLC may accompany it.')
    work = game_dir / '.nxnative-one-click'
    if plan and not work.is_dir():
        raise ValueError('XCI metadata inspection needs a prepared tool; run normally first.')
    if not plan:
        work.mkdir(exist_ok=True)
    if plan:
        tool = build_tool(work, plan=True)
        titles = run_tool(tool, keys, sources[0])
        print('XCI contents: ' + ', '.join(t['Type'] + ' ' + t['TitleId'] + ' v' + str(t['Version']) for t in titles), flush=True)
        # A read-only plan describes the container instead of guessing a base-only package.
        return dict(container=str(sources[0]), titles=titles)
    with (work / 'container.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another process is preparing this XCI.')
        tool = build_tool(work)
        source = sources[0]
        titles = run_tool(tool, keys, source)
        print('XCI contents: ' + ', '.join(t['Type'] + ' ' + t['TitleId'] + ' v' + str(t['Version']) for t in titles), flush=True)
        extras = sorted(p for p in game_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.nsp', '.nsz', '.xcz'))
        paths = [source, *extras]
        fingerprint = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
        key = hashlib.sha256(json.dumps([tool_digest(), fingerprint]).encode()).hexdigest()[:24]
        target = work / 'container-inputs' / key
        marker = target / 'container.json'
        if marker.is_file():
            manifest = json.loads(marker.read_text())
            if all((target / name).is_file() and (target / name).stat().st_size == size
                   for name, size in manifest['outputs'].items()):
                return target
            raise ValueError('Prepared XCI inputs are incomplete; keep them for diagnosis and use another output cache.')
        target.parent.mkdir(exist_ok=True)
        stage = target.with_name('.' + key + '-' + uuid.uuid4().hex)
        stage.mkdir()
        print('Splitting integrated XCI into base/update/DLC NSP inputs (original NCAs unchanged)...', flush=True)
        try:
            exported = run_tool(tool, keys, source, stage)
            if exported != titles:
                raise ValueError('XCI metadata changed during export.')
            for p in extras:
                if (stage / p.name).exists():
                    raise ValueError('Duplicate input file name: ' + p.name)
                (stage / p.name).symlink_to(p.resolve())
            if fingerprint != [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]:
                raise ValueError('Game inputs changed during XCI preparation.')
            outputs = {p.name: p.stat().st_size for p in stage.iterdir() if p.is_file()}
            (stage / 'container.json').write_text(json.dumps(dict(source=str(source), titles=titles, outputs=outputs), indent=2))
            stage.rename(target)
        except BaseException:
            # These are only this attempt's generated copies; original XCI/NSPs are untouched.
            shutil.rmtree(stage)
            raise
        return target
