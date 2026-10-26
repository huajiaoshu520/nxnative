"""Dependency setup for the frontend; upstream build tools stay unmodified."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def call(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def ensure(game_dir, launcher, args):
    if subprocess.run(['xcodebuild', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError('Install full Xcode, open it and accept its license before building.')
    missing = [t for t in ('xcodegen', 'zstd', 'spirv-cross', 'glslang') if not shutil.which(t)]
    if sys.version_info < (3, 12):
        missing.append('python@3.14')
    if missing:
        brew = shutil.which('brew')
        if not brew:
            print('Installing Homebrew from its official installer.', flush=True)
            with tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / 'install.sh'
                with urllib.request.urlopen('https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh', timeout=60) as r:
                    script.write_bytes(r.read())
                call(['bash', script], env=dict(os.environ, NONINTERACTIVE='1'))
            brew = '/opt/homebrew/bin/brew'
        call([brew, 'install', *missing])
    if sys.version_info < (3, 12):
        py = '/opt/homebrew/opt/python@3.14/bin/python3.14'
        os.execv(py, [py, str(launcher), *args])
    os.environ['PATH'] = str(Path.home() / '.dotnet') + os.pathsep + os.environ['PATH']
    dotnet = shutil.which('dotnet')
    if not dotnet or not any(s.startswith('10.') for s in subprocess.check_output([dotnet, '--list-sdks'], text=True).splitlines()):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'dotnet-install.sh'
            with urllib.request.urlopen('https://dot.net/v1/dotnet-install.sh', timeout=60) as r:
                script.write_bytes(r.read())
            call(['bash', script, '--channel', '10.0', '--install-dir', Path.home() / '.dotnet'])
        dotnet = str(Path.home() / '.dotnet/dotnet')
    runtimes = subprocess.check_output([dotnet, '--list-runtimes'], text=True).splitlines()
    runtime = next((s for s in runtimes if s.startswith('Microsoft.NETCore.App 10.')), None)
    if not runtime:
        raise ValueError('.NET 10 runtime is missing after SDK setup.')
    root = str(Path(runtime.split('[', 1)[1].rstrip(']')).parents[1])
    os.environ['DOTNET_ROOT'] = root
    os.environ['DOTNET_ROOT_ARM64'] = root
    packages = [p for mod, p in [('lz4.block', 'lz4'), ('capstone', 'capstone'), ('fontTools', 'fonttools')]
                if not available(mod)]
    if sys.version_info < (3, 14) and not available('backports.zstd'):
        packages.append('backports.zstd')
    if any(game_dir.glob('*.nsz')) or any(game_dir.glob('*.xcz')):
        if not available('nsz'):
            packages.append('nsz')
    if packages:
        venv = game_dir / '.nxnative-one-click/venv'
        py = venv / 'bin/python'
        if Path(sys.executable).parent.parent.resolve() == venv.resolve():
            call([sys.executable, '-m', 'pip', 'install', *packages])
        else:
            if not py.is_file():
                call([sys.executable, '-m', 'venv', venv])
            elif subprocess.check_output([py, '-c', 'import sys; print(sys.version_info >= (3,12))'], text=True).strip() != 'True':
                call([sys.executable, '-m', 'venv', '--upgrade', venv])
            call([py, '-m', 'pip', 'install', *packages])
            os.execv(str(py), [str(py), str(launcher), *args])
    for sdk in ('macosx', 'iphoneos'):
        if subprocess.run(['xcrun', '-sdk', sdk, 'metal', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            call(['xcodebuild', '-downloadComponent', 'MetalToolchain'])
            break
