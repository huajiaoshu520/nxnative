"""Dependency setup for the frontend; upstream build tools stay unmodified."""
import importlib.util
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def call(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def install_brew(brew, missing):
    # Homebrew ask mode is now the default; this frontend already installs
    # its declared build dependencies without an extra terminal prompt.
    call([brew, 'install', '--no-ask', *missing],
         env=dict(os.environ, HOMEBREW_NO_ASK='1', NONINTERACTIVE='1'))


def available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def check_shader_translator(root):
    """Trigger first-launch approval before extraction or shader compilation."""
    tool = Path(root) / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
    if not tool.is_file():
        raise ValueError('Missing official shader translator: ' + str(tool))
    print('Checking dmsh_xlate before building. If macOS blocks it, approve it in System Settings > Privacy & Security > Open Anyway.', flush=True)
    while True:
        try:
            result = subprocess.run([str(tool), '--source-sha'], capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and re.fullmatch(r'[0-9a-fA-F]{16}', result.stdout.strip()):
                print('dmsh_xlate is ready.', flush=True)
                return
            detail = (result.stderr or result.stdout or ('exit ' + str(result.returncode))).strip()
        except (OSError, subprocess.TimeoutExpired) as error:
            detail = str(error)
        message = ('dmsh_xlate could not run: ' + detail[:1000] + '\n'
                   '若 macOS 提示无法验证 dmsh_xlate：点“完成”，在“系统设置 → 隐私与安全性”中找到它，选择“仍要打开”并完成确认。\n'
                   'If blocked by macOS, approve this tool in System Settings > Privacy & Security > Open Anyway. No system security settings are changed by this script.')
        print(message, flush=True)
        if not sys.stdin.isatty():
            raise ValueError('Authorize dmsh_xlate if blocked, resolve any error above, then rerun the launcher. No game build has started.')
        try:
            answer = input('处理完成后按回车重试；输入 q 退出 / Press Return to retry, or q to quit: ')
        except EOFError:
            raise ValueError('Tool preflight cancelled; no game build has started.') from None
        if answer.strip().lower() == 'q':
            raise ValueError('Tool preflight cancelled; no game build has started.')


def ensure(game_dir, launcher, args, mac=False):
    if subprocess.run(['xcodebuild', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError('Install full Xcode, open it and accept its license before building.')
    missing = [t for t in (('zstd', 'spirv-cross', 'glslang') if mac else ('xcodegen', 'zstd', 'spirv-cross', 'glslang')) if not shutil.which(t)]
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
        install_brew(brew, missing)
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
    check_shader_translator(Path(launcher).resolve().parents[1])
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
    for sdk in (('macosx',) if mac else ('macosx', 'iphoneos')):
        if subprocess.run(['xcrun', '-sdk', sdk, 'metal', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            call(['xcodebuild', '-downloadComponent', 'MetalToolchain'])
            break
