import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('containers',ROOT/'dm/local_one_click/containers.py')
containers=importlib.util.module_from_spec(spec);spec.loader.exec_module(containers)


class ContainerTests(unittest.TestCase):
    def test_integrated_xci_exports_separate_packages_and_reuses(self):
        titles=[{'TitleId':'0100ECD018EBE000','Version':0,'Type':'application'},
                {'TitleId':'0100ECD018EBE800','Version':65536,'Type':'patch'}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'arbitrary-name.xci';source.write_bytes(b'fixture')
            extra=root/'dlc.nsp';extra.write_bytes(b'fixture dlc')
            def tool(binary,keys,source,output=None):
                if output:
                    for title in titles:
                        (output/('['+title['TitleId']+'][v'+str(title['Version'])+'].nsp')).write_bytes(b'fixture NSP')
                return titles
            with patch.object(containers,'build_tool',return_value=Path('/tool')), patch.object(containers,'run_tool',side_effect=tool) as run:
                prepared=containers.normalize(root,root/'prod.keys')
                self.assertTrue((prepared/'[0100ECD018EBE000][v0].nsp').exists())
                self.assertTrue((prepared/'[0100ECD018EBE800][v65536].nsp').exists())
                self.assertEqual((prepared/'dlc.nsp').resolve(),extra.resolve())
                self.assertEqual(containers.normalize(root,root/'prod.keys'),prepared)
                self.assertEqual(sum(1 for c in run.call_args_list if len(c.args)==4),1)
                self.assertEqual(source.read_bytes(),b'fixture')
    def test_export_failure_keeps_original_and_no_ready_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'game.xci').write_bytes(b'original')
            with patch.object(containers,'build_tool',return_value=Path('/tool')), patch.object(containers,'run_tool',side_effect=[[{'TitleId':'A','Type':'application','Version':0}],ValueError('damaged')]):
                with self.assertRaisesRegex(ValueError,'damaged'):
                    containers.normalize(root,root/'prod.keys')
            self.assertEqual((root/'game.xci').read_bytes(),b'original')
            self.assertEqual(list((root/'.nxnative-one-click/container-inputs').iterdir()),[])
    def test_plan_inspects_without_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'game.xci').touch();(root/'.nxnative-one-click').mkdir()
            with patch.object(containers,'build_tool',return_value=Path('/tool')), patch.object(containers,'run_tool',return_value=[{'Type':'patch','TitleId':'B','Version':65536}]) as run:
                plan=containers.normalize(root,root/'prod.keys',plan=True)
                self.assertEqual(plan['titles'][0]['Version'],65536)
                self.assertEqual(len(run.call_args.args),3)
            self.assertFalse((root/'.nxnative-one-click/container.lock').exists())
    def test_plain_nsp_needs_no_container_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'game.nsp').touch()
            with patch.object(containers,'build_tool') as build:
                self.assertEqual(containers.normalize(root,root/'prod.keys'),root)
                build.assert_not_called()


if __name__=='__main__':unittest.main()
