import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('sync',ROOT/'dm/local_one_click/sync_upstream.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def git(self,*args):
        return subprocess.check_output(['git',*args],stderr=subprocess.DEVNULL,text=True).strip()
    def write(self,path,text):
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def commit(self):
        self.git('add','-A');self.git('commit','-qm','fixture')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.cwd=Path.cwd();os.chdir(self.temp.name)
        self.git('init','-q');self.git('config','user.name','Test');self.git('config','user.email','test@example.invalid')
        self.write('scripts/nx_one_click.py','base\n');self.write('official.txt','base\n');self.commit()
        self.git('branch','upstream');self.git('checkout','-qb','fork')
        self.write('scripts/nx_one_click.py','fork\n');self.write('dm/local_one_click/helper','keep\n');self.commit()
    def tearDown(self):
        os.chdir(self.cwd);self.temp.cleanup()
    def upstream(self): self.git('checkout','-q','upstream')
    def fork(self): self.git('checkout','-q','fork')
    def test_conflict_on_launcher_keeps_fork_and_updates_official(self):
        self.upstream();self.write('scripts/nx_one_click.py','upstream\n');self.write('official.txt','updated\n');self.commit();self.fork()
        self.assertTrue(sync.merge('upstream'))
        self.assertEqual(Path('scripts/nx_one_click.py').read_text(),'fork\n')
        self.assertEqual(Path('official.txt').read_text(),'updated\n')
        self.assertEqual(len(self.git('show','-s','--format=%P').split()),2)
    def test_upstream_deletion_and_addition_in_protected_prefix(self):
        self.upstream();self.git('rm','scripts/nx_one_click.py');self.write('dm/local_one_click/foreign','upstream\n');self.commit();self.fork()
        sync.merge('upstream')
        self.assertTrue(Path('scripts/nx_one_click.py').exists())
        self.assertFalse(Path('dm/local_one_click/foreign').exists())
        self.assertEqual(Path('dm/local_one_click/helper').read_text(),'keep\n')
    def test_conflict_outside_protection_aborts(self):
        self.write('official.txt','fork\n');self.commit();before=self.git('rev-parse','HEAD')
        self.upstream();self.write('official.txt','other\n');self.commit();self.fork()
        with self.assertRaises(RuntimeError): sync.merge('upstream')
        self.assertEqual(self.git('rev-parse','HEAD'),before)
        self.assertEqual(self.git('status','--porcelain'),'')
    def test_runner_without_git_identity(self):
        self.upstream();self.write('official.txt','updated\n');self.commit();self.fork()
        self.git('config','--unset','user.name');self.git('config','--unset','user.email')
        self.assertTrue(sync.merge('upstream'))
        self.assertEqual(Path('official.txt').read_text(),'updated\n')
    def test_no_updates(self): self.assertFalse(sync.merge('upstream'))
    def test_dirty_checkout_rejected(self):
        self.write('untracked','data')
        with self.assertRaises(RuntimeError): sync.merge('upstream')


if __name__=='__main__': unittest.main()
