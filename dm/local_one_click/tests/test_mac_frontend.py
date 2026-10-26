import importlib.util
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('frontend',ROOT/'scripts/nx_one_click.py')
frontend=importlib.util.module_from_spec(spec);spec.loader.exec_module(frontend)
ENTRY={'id':'0100000000000000','marker':'marker.bin'}


class MacFrontendTests(unittest.TestCase):
    def app(self,root):
        app=root/'Game.app';contents=app/'Contents';res=contents/'Resources'
        for folder in ['MacOS','Resources/romfs','Resources/msl/b-chain','Resources/dm/font']:
            (contents/folder).mkdir(parents=True,exist_ok=True)
        (contents/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.nxnative.0100000000000000','CFBundleExecutable':'nxnative'}))
        for name in ['nxnative','dmhost']:
            p=contents/'MacOS'/name;p.write_bytes(b'fixture');p.chmod(0o755)
        for name in ['romfs/marker.bin','msl/b-chain/library.metallib','dm/main.patched.bin','dm/font/font.ttf']:
            (res/name).write_bytes(b'fixture')
        return app
    def test_mac_delegates_to_official_standalone_app_mode(self):
        cmd=frontend.command(Path('/game folder'),Path('/prod.keys'),Path('/Game.app'),'v0','en-US','mac-app')
        self.assertEqual(cmd[cmd.index('--platform')+1],'mac-app')
        self.assertEqual(cmd[cmd.index('--mac-sign')+1],'-')
        self.assertNotIn('--prepare-xcode',cmd)


    def test_publish_official_app_without_secondary_signature_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial, target = root / 'partial.app', root / 'finished.app'
            partial.mkdir()
            (partial / 'official-resource').write_bytes(b'fixture')
            with patch.object(frontend.subprocess, 'run') as run:
                frontend.publish_output(partial, target, mac=True)
                run.assert_not_called()
            self.assertTrue((target / 'official-resource').is_file())
            with self.assertRaisesRegex(ValueError, 'no output'):
                frontend.publish_output(root / 'missing.app', root / 'other.app', mac=True)

    def test_cleanup_retains_finished_app(self):
        import cleanup
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app=self.app(root);game=root/'inputs';game.mkdir();keys=game/'prod.keys';keys.touch()
            (game/'base.nsp').touch();cache=game/'.nxnative-one-click';cache.mkdir();(cache/'build.log').touch()
            removed,retained=cleanup.cleanup_success(game,game,ENTRY['id'],app,keys)
            self.assertFalse(retained);self.assertFalse(cache.exists());self.assertTrue(app.is_dir())
            self.assertTrue((app/'Contents/Resources/romfs/marker.bin').is_file())
    def test_mac_launcher_protected_from_upstream(self):
        spec=importlib.util.spec_from_file_location('sync',ROOT/'dm/local_one_click/sync_upstream.py')
        sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
        self.assertTrue(sync.protected('一键生成Mac应用.command'))


if __name__=='__main__':unittest.main()
