import importlib.util
from pathlib import Path
import unittest
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


if __name__ == '__main__':
    unittest.main()
