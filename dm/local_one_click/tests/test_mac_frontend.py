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
    def test_self_contained_app_and_signature_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=self.app(Path(tmp))
            with patch.object(frontend.subprocess,'run') as run:
                frontend.verify_mac_app(app,ENTRY)
                self.assertIn('--verify',run.call_args.args[0])
                self.assertIn('--strict',run.call_args.args[0])
    def test_external_shader_reference_rejected_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app=self.app(root);external=root/'cache.metallib';external.touch()
            (app/'Contents/Resources/msl/external.metallib').symlink_to(external)
            with self.assertRaisesRegex(ValueError,'external'):
                frontend.verify_mac_app(app,ENTRY)
    def test_missing_resources_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=self.app(Path(tmp));(app/'Contents/Resources/dm/font/font.ttf').unlink()
            with self.assertRaisesRegex(ValueError,'font'):
                frontend.verify_mac_app(app,ENTRY)
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
