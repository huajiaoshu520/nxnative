import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('cleanup',ROOT/'dm/local_one_click/cleanup.py')
cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)
TITLE='0100ECD018EBE000'


class CleanupTests(unittest.TestCase):
    def fixture(self, root):
        game=root/'game';game.mkdir()
        (game/'original.xci').write_bytes(b'original')
        keys=game/'prod.keys';keys.write_bytes(b'fixture')
        ipa=root/'finished.ipa';ipa.write_bytes(b'validated fixture')
        work=game/'.nxnative-one-click';work.mkdir()
        (work/'build.log').write_text('log')
        (work/'venv').mkdir();(work/'venv/python').touch()
        old=game/(TITLE+'_build');old.mkdir();(old/'cache').touch()
        return game,work,ipa,keys
    def test_success_removes_generated_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            game,work,ipa,keys=self.fixture(Path(tmp))
            prepared=work/'container-inputs/hash';prepared.mkdir(parents=True)
            (prepared/'generated.nsp').write_bytes(b'generated')
            (prepared/'external.nsp').symlink_to(game/'original.xci')
            (game/'unrelated.txt').write_text('keep')
            removed,retained=cleanup.cleanup_success(game,prepared,TITLE,ipa,keys)
            self.assertEqual(retained,[])
            self.assertFalse(work.exists())
            self.assertFalse((game/(TITLE+'_build')).exists())
            self.assertEqual((game/'original.xci').read_bytes(),b'original')
            self.assertEqual(keys.read_bytes(),b'fixture')
            self.assertTrue(ipa.exists())
            self.assertEqual((game/'unrelated.txt').read_text(),'keep')
    def test_missing_ipa_never_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            game,work,ipa,keys=self.fixture(Path(tmp));ipa.unlink()
            with self.assertRaises(ValueError):cleanup.cleanup_success(game,game,TITLE,ipa,keys)
            self.assertTrue(work.exists())
    def test_ipa_or_keys_inside_cache_preserved(self):
        for kind in ['ipa','keys']:
            with tempfile.TemporaryDirectory() as tmp:
                game,work,ipa,keys=self.fixture(Path(tmp))
                if kind=='ipa':ipa=work/'finished.ipa';ipa.touch()
                else:keys=work/'prod.keys';keys.touch()
                _,retained=cleanup.cleanup_success(game,game,TITLE,ipa,keys)
                self.assertTrue(retained)
                self.assertTrue(ipa.exists());self.assertTrue(keys.exists())
    def test_saves_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            game,work,ipa,keys=self.fixture(Path(tmp))
            save=game/(TITLE+'_build')/'run/save/slot';save.parent.mkdir(parents=True);save.write_text('save')
            _,retained=cleanup.cleanup_success(game,game,TITLE,ipa,keys)
            self.assertTrue(retained);self.assertEqual(save.read_text(),'save')
    def test_no_directory_symlink_following(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game,work,ipa,keys=self.fixture(root)
            import shutil
            shutil.rmtree(work);outside=root/'outside';outside.mkdir();(outside/'keep').touch();work.symlink_to(outside,target_is_directory=True)
            _,retained=cleanup.cleanup_success(game,game,TITLE,ipa,keys)
            self.assertTrue(retained);self.assertTrue((outside/'keep').exists())
    def test_lock_survives_removal_without_leaving_lockfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            game,work,ipa,keys=self.fixture(Path(tmp))
            with cleanup.build_lock(game):
                with self.assertRaises(ValueError):
                    with cleanup.build_lock(game):pass
                cleanup.cleanup_success(game,game,TITLE,ipa,keys)
            with cleanup.build_lock(game):pass
            self.assertFalse(work.exists())


if __name__=='__main__':unittest.main()
