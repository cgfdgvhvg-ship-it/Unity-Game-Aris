"""Scratch-only Unity SceneView framing tests; no native assets changed."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ai_codespace_executor as ex


class ScratchSceneViewGalleryTests(unittest.TestCase):
    def sample(self):
        return ('class AarisLiveEditorBridge {\n'
                '                    case "inspect": Inspect(request, result); break;\n'
                '        private static void Capture(Request request, Response result) {}\n}\n')

    def test_camera_patch_only_adds_sceneview_operation(self):
        before=self.sample()
        after=ex._sceneview_bridge_source(before)
        self.assertEqual(before.count('case "inspect"'), 1)
        self.assertEqual(after.count('case "view": FrameForScreenshot(request, result); break;'),1)
        self.assertIn('SceneView.lastActiveSceneView',after)
        self.assertIn('view.LookAtDirect(request.cameraTarget',after)
        self.assertIn('view.orthographic = false;',after)
        self.assertNotIn('SubmitRenderRequest',after)
        self.assertNotIn('EditorSceneManager.Save',after)
        self.assertEqual(before,self.sample())

    def test_missing_or_duplicate_anchors_are_refused(self):
        for bad in ('bogus source',
                    self.sample()+'                    case "inspect": Inspect(request, result); break;',
                    self.sample().replace('private static void Capture','private static void Missing')):
            with self.assertRaises(ValueError):
                ex._sceneview_bridge_source(bad)
        with self.assertRaises(ValueError):
            ex._sceneview_bridge_source(ex._sceneview_bridge_source(self.sample()))

    def test_bounded_read_only_view_request(self):
        good={'action':'view',
              'cameraPosition':{'x':350,'y':-10.1,'z':265},
              'cameraTarget':{'x':350,'y':-7.1,'z':245}}
        self.assertEqual(ex.validate_live_payload(good),good)
        with self.assertRaises(ValueError):
            ex.validate_live_payload({'action':'view','cameraTarget':good['cameraTarget']})
        with self.assertRaises(ValueError):
            ex.validate_live_payload(dict(good,delta={'x':1,'y':0,'z':0}))
        with self.assertRaises(ValueError):
            ex.validate_live_payload(dict(good,cameraPosition={'x':float('nan'),'y':0,'z':0}))

    def test_staging_has_original_and_scratch_guards(self):
        source=Path(ex.__file__).read_text(encoding='utf-8')
        block=source.split('def unity_sceneview_prepare():',1)[1].split('\ndef unity_virtual_frame(',1)[0]
        for guard in ('_scratch_unity_pids()', 'bridge.resolve().is_relative_to(scratch.resolve())',
                      'scratch.is_symlink()', 'bridge.is_symlink()',
                      'scene-readback.json', 'original_worktree_untouched',
                      'backup.exists()', 'os.replace(new,bridge)'):
            self.assertIn(guard,block)
        self.assertNotIn('shutil.rmtree(',block)
        self.assertNotIn('RenderPipeline.SubmitRenderRequest',block)


if __name__ == '__main__':
    unittest.main()
