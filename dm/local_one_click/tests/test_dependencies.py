import importlib.util
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('dependencies', ROOT / 'dm/local_one_click/dependencies.py')
dependencies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependencies)


class DependencyTests(unittest.TestCase):
    def test_brew_install_does_not_wait_for_yes_no(self):
        with patch.object(dependencies, 'call') as call:
            dependencies.install_brew('/opt/homebrew/bin/brew', ['glslang'])
        args, kwargs = call.call_args
        self.assertEqual(args[0], ['/opt/homebrew/bin/brew', 'install', '--no-ask', 'glslang'])
        self.assertEqual(kwargs['env']['HOMEBREW_NO_ASK'], '1')
        self.assertEqual(kwargs['env']['NONINTERACTIVE'], '1')

    def translator(self, root):
        tool = root / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
        tool.parent.mkdir(parents=True)
        tool.touch()
        return tool

    def test_translator_probe_uses_read_only_source_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); tool = self.translator(root)
            with patch.object(dependencies.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='0123456789abcdef\n', stderr='')) as run:
                dependencies.check_shader_translator(root)
            self.assertEqual(run.call_args.args[0], [str(tool), '--source-sha'])

    def test_blocked_translator_retries_only_after_user_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.translator(root)
            outcomes = [SimpleNamespace(returncode=-9, stdout='', stderr=''), SimpleNamespace(returncode=0, stdout='0123456789abcdef', stderr='')]
            with patch.object(dependencies.subprocess, 'run', side_effect=outcomes) as run, patch.object(dependencies.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='') as prompt:
                dependencies.check_shader_translator(root)
            self.assertEqual(run.call_count, 2)
            prompt.assert_called_once()

    def test_noninteractive_failure_stops_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.translator(root)
            with patch.object(dependencies.subprocess, 'run', side_effect=PermissionError('blocked')), patch.object(dependencies.sys.stdin, 'isatty', return_value=False), self.assertRaisesRegex(ValueError, 'No game build'):
                dependencies.check_shader_translator(root)

    def test_quit_preserves_blocked_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.translator(root)
            with patch.object(dependencies.subprocess, 'run', return_value=SimpleNamespace(returncode=-9, stdout='', stderr='')), patch.object(dependencies.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='q'), self.assertRaisesRegex(ValueError, 'cancelled'):
                dependencies.check_shader_translator(root)


if __name__ == '__main__':
    unittest.main()
