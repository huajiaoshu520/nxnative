import importlib.util
import json
from pathlib import Path
import plistlib
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('frontend', ROOT / 'scripts/nx_one_click.py')
frontend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend)


class FrontendTests(unittest.TestCase):
    def test_live_catalog_and_multiple_versions(self):
        entries = frontend.catalog()
        self.assertGreater(len(entries), 60)
        self.assertEqual(entries['01006F8002326000']['builds']['v2228224'], '3.0.3')
        self.assertTrue(any(len(e['builds']) > 1 for e in entries.values()))

    def test_profiles_added_without_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / 'dm/games/0100000000000000/game.tsv'
            profile.parent.mkdir(parents=True)
            profile.write_text('title_id\t0100000000000000\nname\tFixture\nipa\tFixture.ipa\nbuild\tv0\t1.0\nbuild\tv65536\t1.1\n')
            self.assertEqual(frontend.catalog(root)['0100000000000000']['builds'], {'v0':'1.0','v65536':'1.1'})

    def family(self, update):
        return {'base':Path('base.nsp'), 'updates':[(update,Path('update.nsp'))], 'dlc':[]}

    def test_select_registered_and_other_version(self):
        official = frontend.pipeline()
        with patch.object(official, 'scan_nsps', return_value=(int('01006F8002326000',16),self.family(2228224))), patch.object(frontend,'pipeline',return_value=official):
            entry, version, _ = frontend.select_inputs(Path('/tmp'))
            self.assertEqual(version,'v2228224')
        with patch.object(official,'scan_nsps',return_value=(int('01006F8002326000',16),self.family(9999999))), patch.object(frontend,'pipeline',return_value=official):
            _, version, _ = frontend.select_inputs(Path('/tmp'))
            self.assertEqual(version, 'v9999999')

    def test_base_only_paper_mario_and_absent_explicit_package(self):
        official = frontend.pipeline()
        family = {'base': Path('base.nsp'), 'updates': [], 'dlc': []}
        tid = next(int(k,16) for k,v in frontend.catalog().items() if v['name'] == 'Paper Mario: The Thousand-Year Door')
        with patch.object(official, 'scan_nsps', return_value=(tid, family)), patch.object(frontend, 'pipeline', return_value=official):
            _, version, _ = frontend.select_inputs(Path('/tmp'))
            self.assertEqual(version, 'v0')
            with self.assertRaisesRegex(ValueError, 'absent'):
                frontend.select_inputs(Path('/tmp'), 'v65536')

    def test_upstream_command_keeps_spaces_and_embedding(self):
        cmd = frontend.command(Path('/my games/a'),Path('/my keys/prod.keys'),Path('/out/full.ipa'),'v0','zh-Hans')
        self.assertIn('/my games/a',cmd)
        self.assertEqual(cmd[1],str(ROOT/'scripts/build_ipa_from_nsp.py'))
        self.assertEqual(cmd[cmd.index('--platform')+1],'ios')
        self.assertNotIn('--prepare-xcode',cmd)
        self.assertNotIn('pack_data.py',' '.join(cmd))

    def test_ipa_all_in_one_checks(self):
        entry = {'id':'0100000000000000','marker':'marker.bin'}
        with tempfile.TemporaryDirectory() as tmp:
            for embedded in (True,False):
                out=Path(tmp)/'test.ipa'
                with zipfile.ZipFile(out,'w') as z:
                    z.writestr('Payload/Test.app/Info.plist',plistlib.dumps({'CFBundleIdentifier':'org.nxnative.0100000000000000','CFBundleExecutable':'Test'}))
                    z.writestr('Payload/Test.app/Test',b'fixture')
                    z.writestr('Payload/Test.app/msl/b-test/shader.metallib',b'fixture')
                    if embedded: z.writestr('Payload/Test.app/romfs/marker.bin',b'fixture')
                if embedded: frontend.verify_ipa(out,entry)
                else:
                    with self.assertRaises(ValueError): frontend.verify_ipa(out,entry)

    @unittest.skipUnless(platform.system() == 'Darwin', 'AppleScript requires macOS')
    def test_picker_initializes_without_readonly_property_error(self):
        result = subprocess.run(['osascript', str(ROOT / 'dm/local_one_click/choose_inputs.applescript'), '--self-test'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_picker_preserves_actual_error(self):
        response = subprocess.CompletedProcess([], 1, '', 'execution error: fixture (-10006)')
        with patch.object(frontend.subprocess, 'run', return_value=response):
            with self.assertRaisesRegex(ValueError, '-10006'):
                frontend.pick('game')

    def test_plan_never_installs_or_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); keys=root/'prod.keys'; keys.touch()
            out=root/'output'
            with patch.object(frontend.platform,'system',return_value='Darwin'), patch.object(frontend.platform,'machine',return_value='arm64'), patch.object(frontend,'select_inputs',return_value=({'id':'fixture'},'v0',{'dlc':[]})), patch.object(frontend.subprocess,'Popen') as popen:
                frontend.main(['--plan','--game-dir',str(root),'--keys',str(keys),'--output-dir',str(out)])
                popen.assert_not_called()
                self.assertFalse(out.exists())
                self.assertFalse((root/'.nxnative-one-click').exists())


if __name__=='__main__': unittest.main()
