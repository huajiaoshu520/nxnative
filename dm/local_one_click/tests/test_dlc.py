"""Synthetic package fixtures: no game files, keys, shaders or Xcode required."""
import contextlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('dlc_frontend', ROOT / 'scripts/nx_one_click.py')
frontend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend)
import containers

APP = 0x01006F8002326000


def package(path, title=None):
    names = [] if title is None else [f'{title:016x}0000000000000001.tik']
    strings = b''.join(n.encode() + b'\0' for n in names)
    entries = b''.join(struct.pack('<QQII', 0, 0, 0, 0) for n in names)
    path.write_bytes(b'PFS0' + struct.pack('<III', len(names), len(strings), 0) + entries + strings)


class DlcTests(unittest.TestCase):
    def test_ticketless_untagged_dlc_uses_official_metadata_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root / f'base [{APP:016X}][v0].nsp', APP)
            dlc = root / 'Happy Home Paradise.nsp'
            package(dlc)
            official = frontend.pipeline()
            with patch.object(frontend, 'pipeline', return_value=official), patch.object(official, 'package_title_reader', return_value=contextlib.nullcontext(lambda p: APP + 0x1001)) as reader:
                _, _, family = frontend.select_inputs(root, keys=root / 'prod.keys')
            self.assertEqual(family['dlc'], [(APP + 0x1001, None, dlc)])
            self.assertEqual(reader.call_args.args[1], root / 'prod.keys')

    def test_unreadable_dlc_stops_instead_of_disappearing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root / f'base [{APP:016X}][v0].nsp', APP)
            package(root / 'unreadable-dlc.nsp')
            official = frontend.pipeline()
            with patch.object(frontend, 'pipeline', return_value=official), patch.object(official, 'package_title_reader', return_value=contextlib.nullcontext(lambda p: None)), self.assertRaisesRegex(ValueError, 'Cannot identify'):
                frontend.select_inputs(root, keys=root / 'prod.keys')

    def test_recursive_dlc_preserves_duplicate_names_and_ignores_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package(root / f'Base [{APP:016X}][v0].nsp', APP)
            for directory, title in [('DLC/one', APP + 0x1001), ('DLC/two', APP + 0x1002)]:
                folder = root / directory
                folder.mkdir(parents=True)
                package(folder / 'Content.NSP', title)
            cache = root / f'{APP:016X}_build/nsp'
            cache.mkdir(parents=True)
            package(cache / 'duplicate.nsp', APP)
            (root / 'linked-dlc').symlink_to(root / 'DLC', target_is_directory=True)
            prepared = containers.normalize(root, root / 'prod.keys')
            _, _, family = frontend.select_inputs(prepared)
            self.assertEqual(len(family['dlc']), 2)
            self.assertEqual(len(list(prepared.glob('*.nsp'))), 3)
            self.assertTrue((root / 'DLC/one/Content.NSP').exists())
            self.assertEqual(containers.normalize(root, root / 'prod.keys'), prepared)
            package(root / 'DLC' / f'New [{APP + 0x1003:016X}].nsp', APP + 0x1003)
            self.assertNotEqual(containers.normalize(root, root / 'prod.keys'), prepared)

    def test_integrated_xci_and_external_dlc_reach_official_scanner(self):
        titles = [{'TitleId': f'{APP:016X}', 'Version': 0, 'Type': 'application'},
                  {'TitleId': f'{APP | 0x800:016X}', 'Version': 2228224, 'Type': 'patch'},
                  {'TitleId': f'{APP + 0x1001:016X}', 'Version': 0, 'Type': 'dlc'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'game.xci').write_bytes(b'original')
            (root / '._game.xci').write_bytes(b'AppleDouble')
            (root / 'DLC/subfolder').mkdir(parents=True)
            extra = root / 'DLC/subfolder' / f'Bonus [{APP + 0x1002:016X}][v0].NSP'
            package(extra, APP + 0x1002)
            (root / ('._' + extra.name)).write_bytes(b'AppleDouble')
            def export(tool, keys, source, output=None):
                if output:
                    for title in titles:
                        package(output / f"[{title['TitleId']}][v{title['Version']}].nsp", int(title['TitleId'], 16))
                return titles
            with patch.object(containers, 'build_tool', return_value=Path('/tool')), patch.object(containers, 'run_tool', side_effect=export):
                prepared = containers.normalize(root, root / 'prod.keys')
                _, version, family = frontend.select_inputs(prepared)
                self.assertEqual(version, 'v2228224')
                self.assertEqual({t for t, _, _ in family['dlc']}, {APP + 0x1001, APP + 0x1002})
                self.assertFalse(any(p.name.startswith('._') for p in prepared.iterdir()))
                # Adding a DLC changes the input cache and cannot reuse an old set.
                package(root / f'Extra [{APP + 0x1003:016X}][v0].nsp', APP + 0x1003)
                newer = containers.normalize(root, root / 'prod.keys')
                self.assertNotEqual(prepared, newer)
                self.assertEqual(len(frontend.select_inputs(newer)[2]['dlc']), 3)
                command = frontend.command(newer, root / 'prod.keys', root / 'out.ipa', version, 'en-US')
                self.assertEqual(command[2], str(newer))
                self.assertEqual((root / 'game.xci').read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
