"""Exercise real transaction isolation and saved assets; no Unity/FPS claims."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unity_data import SCENE, WorldError, digest, documents
from patching import apply_yaml, plan, preview_yaml
from lod_profiles import REVIEWED_TREE_LODS, TREE_PREFIX, preserved_tree_lod_only
from test_world import fixture

ROOT = Path(__file__).resolve().parents[3]
PREFAB = 'Assets/TestTree.prefab'


class PrefabLodTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fixture(self.root)
        body = ('%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n'
                '--- !u!205 &42\nLODGroup:\n  m_GameObject: {fileID: 1}\n'
                '  m_FadeMode: 1\n  m_AnimateCrossFading: 1\n  m_LODs:\n')
        for i, height in enumerate((.5, .25, .08, .01)):
            body += f'  - screenRelativeHeight: {height}\n    fadeTransitionWidth: 0\n    renderers:\n    - renderer: {{fileID: {100+i}}}\n'
        body += '--- !u!65 &43\nBoxCollider:\n  m_Size: {x: 1, y: 3, z: 1}\n  m_Enabled: 1\n'
        (self.root/PREFAB).write_text(body)
        (self.root/(PREFAB+'.meta')).write_text('fileFormatVersion: 2\nguid: '+'a'*32+'\n')

    def tearDown(self):
        self.temp.cleanup()

    def patch(self):
        return {'schema_version': 2, 'transaction_id': 'test-prefab-lod-0001',
                'idempotency_key': 'test-prefab-lod-0001', 'reason': 'Move middle transitions while retaining the distant silhouette',
                'expected_files': {p: digest(self.root/p) for p in (PREFAB, PREFAB+'.meta')},
                'operations': [{'id': 'tree-lod', 'op': 'set_prefab_lod_thresholds', 'path': PREFAB,
                                'file_id': 42, 'screen_relative_heights': [.5, .30, .12, .01]}],
                'observe_after': [{'x': 0, 'z': 0, 'radius': 5, 'native': False, 'geometry': False}]}

    def test_plan_preview_apply_change_only_requested_scalars_and_report_exact_state(self):
        original = (self.root/PREFAB).read_bytes()
        scene = (self.root/SCENE).read_bytes()
        metadata = (self.root/(PREFAB+'.meta')).read_bytes()
        patch = self.patch()
        report, _ = plan(self.root, patch)
        self.assertEqual(report['predicted_written_files'], [PREFAB])
        self.assertEqual((self.root/PREFAB).read_bytes(), original)
        preview = preview_yaml(self.root, patch)
        self.assertTrue(preview['preview'])
        self.assertEqual((self.root/PREFAB).read_bytes(), original)
        delta = preview['operation_deltas'][0]
        self.assertEqual(delta['before']['state']['screen_relative_heights'], [.5, .25, .08, .01])
        self.assertEqual(delta['after']['state']['screen_relative_heights'], [.5, .30, .12, .01])
        self.assertEqual(delta['before']['state']['renderer_sets'], delta['after']['state']['renderer_sets'])
        result = apply_yaml(self.root, patch, True)
        expected = original.replace(b'screenRelativeHeight: 0.25\n', b'screenRelativeHeight: 0.3\n').replace(
            b'screenRelativeHeight: 0.08\n', b'screenRelativeHeight: 0.12\n')
        self.assertEqual((self.root/PREFAB).read_bytes(), expected)
        self.assertEqual((self.root/SCENE).read_bytes(), scene)
        self.assertEqual((self.root/(PREFAB+'.meta')).read_bytes(), metadata)
        self.assertEqual(set(result['written_file_changes']), {PREFAB})
        self.assertTrue(result['operation_deltas'][0]['changed'])
        self.assertTrue(result['observation_deltas'])

    def test_culling_count_order_nonfinite_and_boolean_inputs_never_write(self):
        original = (self.root/PREFAB).read_bytes()
        for values in ([.5, .3, .12, .009], [.5, .3, .01], [.5, .6, .12, .01],
                       [.5, .3, float('nan'), .01], [.5, .3, float('inf'), .01],
                       [True, .3, .12, .01], [.5, .3, .3, .01], [.5, .3, .12, 0]):
            patch = self.patch()
            patch['operations'][0]['screen_relative_heights'] = values
            with self.subTest(values=values), self.assertRaises(WorldError):
                apply_yaml(self.root, patch, True)
            self.assertEqual((self.root/PREFAB).read_bytes(), original)

    def test_identity_stale_sources_and_competing_operations_fail_closed(self):
        patch = self.patch()
        patch['expected_files'].pop(PREFAB+'.meta')
        with self.assertRaises(WorldError): plan(self.root, patch)
        patch = self.patch()
        patch['operations'].append({**copy.deepcopy(patch['operations'][0]), 'id': 'duplicate'})
        with self.assertRaises(WorldError): plan(self.root, patch)
        patch = self.patch()
        (self.root/(PREFAB+'.meta')).write_text('changed')
        with self.assertRaises(WorldError): apply_yaml(self.root, patch, True)

    def test_line_endings_and_bom_cannot_normalize_unrelated_saved_bytes(self):
        original = (self.root/PREFAB).read_bytes()
        for source in (original.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf'+original):
            with self.subTest(prefix=source[:8]):
                (self.root/PREFAB).write_bytes(source)
                with self.assertRaisesRegex(WorldError, 'byte normalization'):
                    apply_yaml(self.root, self.patch(), True)
                self.assertEqual((self.root/PREFAB).read_bytes(), source)


class ActualSpeedTreeProfileIntegrity(unittest.TestCase):
    def test_all_six_profiles_retain_close_detail_and_far_cutoff_and_only_change_thresholds(self):
        contract = json.loads((ROOT/'Tools/World/tree-house-20261103.postconditions.json').read_text())
        for name, (old, new) in REVIEWED_TREE_LODS.items():
            path = TREE_PREFIX+name+'.prefab'
            with self.subTest(prefab=path):
                group = next(d for d in documents(ROOT/path)[1] if d['kind'] == 'LODGroup')['data']
                self.assertEqual([lod['screenRelativeHeight'] for lod in group['m_LODs']], new)
                self.assertEqual(old[0], new[0])
                self.assertEqual(old[-1], new[-1])
                self.assertTrue(all(a <= b for a, b in zip(old[1:-1], new[1:-1])))
                self.assertTrue(all(lod['renderers'] for lod in group['m_LODs']))
                self.assertTrue(preserved_tree_lod_only(ROOT, path, contract['tree_source_files'][path]))

    def test_historical_hash_cannot_exempt_modified_colliders_or_renderers(self):
        contract = json.loads((ROOT/'Tools/World/tree-house-20261103.postconditions.json').read_text())
        path = TREE_PREFIX+'Conifer/Conifer.prefab'
        source = (ROOT/path).read_text()
        for old, new in (('  m_Enabled: 1', '  m_Enabled: 0'), ('  m_Size:', '  UnexpectedSize:'),
                         ('  - screenRelativeHeight: 0.01\n', '  - screenRelativeHeight: 0.009\n')):
            with self.subTest(field=old), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)/path
                p.parent.mkdir(parents=True)
                changed = source.replace(old, new, 1)
                self.assertNotEqual(changed, source)
                p.write_text(changed)
                self.assertFalse(preserved_tree_lod_only(tmp, path, contract['tree_source_files'][path]))

    def test_runtime_cannot_reduce_global_lod_culling_horizon(self):
        source = (ROOT/'Assets/AarisWorld/Scripts/AarisMobileRuntime.cs').read_text()
        self.assertIsNone(re.search(r'QualitySettings\.lodBias\s*=(?!=)', source))


if __name__ == '__main__':
    unittest.main()
