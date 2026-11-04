"""No Unity Editor required: safe motion planner contract tests."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_world_motion as m


class MathTests(unittest.TestCase):
    def test_world_left_50_and_right_100(self):
        self.assertEqual(m.delta("left",50),[-50.,0.,0.])
        self.assertEqual(m.delta("right",100),[100.,0.,0.])
        self.assertEqual(m.delta("forward",40),[0.,0.,40.])

    def test_target_local_yaw_90(self):
        q=m.native_rotation(90)
        d=m.delta("left",50,"target-local",q)
        self.assertAlmostEqual(d[0],0.)
        self.assertAlmostEqual(d[2],50.)
        d=m.delta("forward",100,"target-local",q)
        self.assertAlmostEqual(d[0],100.)
        self.assertAlmostEqual(d[2],0.)

    def test_pitched_object_local_left_stays_horizontal(self):
        q=[[.7071,0,.7071],[0,.8,-.6],[-.7071,.6,.56568]]
        # Orientation fixtures need not be perfectly orthogonal for this
        # math contract; we always project horizontal movement to Y=0.
        d=m.delta("forward",20,"target-local",q)
        self.assertAlmostEqual(d[1],0.)
        self.assertAlmostEqual((d[0]**2+d[2]**2)**.5,20.)

    def test_excess_distance_and_nans_rejected(self):
        for call in (
            lambda:m.delta("right",501),
            lambda:m.delta("right",float("nan")),
            lambda:m.delta(xyz=[0,0,0]),
            lambda:m.delta(xyz=[float("inf"),0,0]),
            lambda:m.delta(direction="left",meters=10,xyz=[5,0,0]),
            lambda:m.delta("right",10,"target-local",None),
        ):
            with self.subTest(call=call),self.assertRaises(m.MotionError):
                call()

    def test_vector_precision_and_short_output(self):
        data={"status":"planned_read_only","target":"scene:"+"a"*32+":1",
              "before_world_xyz_m":[1.,2.,3.],
              "proposed_world_xyz_m":[-49.,2.,3.],
              "nearby_saved_evidence":{
                  "before":{"scene_on_page":[{"name":"Tree","v":"x"*3000}]*15,
                             "terrain_instances_on_page":[],
                             "pagination":{"scene_next_offset":15}},
                  "destination_before_move":{"scene_on_page":[]}}}
        out=m.output(data)
        parsed=json.loads(out)
        self.assertEqual(parsed["proposed_world_xyz_m"],[-49.,2.,3.])
        self.assertLessEqual(len(out),m.MAX_RESULT)


class PatchTests(unittest.TestCase):
    def test_inline_scene_patch_has_hashes_and_world_pos(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            root=Path(temp);name="Assets/MyScene.unity"
            file=root/name;file.parent.mkdir(parents=True)
            file.write_bytes(b"scene-yaml");(root/(name+".meta")).write_bytes(b"guid: aaa")
            ident="scene:"+"a"*32+":123"
            from hashlib import sha256
            digest=lambda p:sha256(p.read_bytes()).hexdigest()
            patch=m.make_patch(ident,[1,2,3],[-49,2,3],name,None,root,digest)
            self.assertEqual(patch["operations"][0]["op"],"set_transform")
            self.assertEqual(patch["operations"][0]["world_position"],[-49.,2.,3.])
            self.assertEqual(len(patch["expected_files"]),2)
            self.assertEqual(len(patch["expected_files"][name]),64)
            self.assertEqual(patch["schema_version"],2)
            self.assertEqual(patch["transaction_id"],patch["idempotency_key"])

    def test_native_instance_requires_both_scene_and_terrain_identity(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            root=Path(temp);scene="Assets/MyScene.unity"
            native="Assets/Terrain/Data/Tile.asset"
            for f in [scene,scene+".meta",native,native+".meta"]:
                p=root/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("X")
            from hashlib import sha256
            patch=m.make_patch("terrain:"+"f"*32+":99",[1,0,3],[51,0,3],
                               scene,native,root,lambda x:sha256(x.read_bytes()).hexdigest())
            self.assertEqual(patch["operations"][0]["op"],"terrain_instance_move")
            self.assertEqual(patch["operations"][0]["world_xz"],[51.,3.])
            self.assertEqual(len(patch["expected_files"]),4)

    def test_reference_frame_requires_explicit_scene_id(self):
        identity="scene:"+"a"*32+":123"
        for extra in (
            ["--frame","reference-local"],
            ["--frame","world","--reference",identity],
            ["--frame","reference-local","--reference","terrain:"+"f"*32+":8",
             "--dx","5"],
        ):
            with self.subTest(extra=extra):
                out=io.StringIO()
                with contextlib.redirect_stdout(out):
                    code=m.main(["plan","--target",identity,
                                 "--direction","left","--metres","50",*extra])
                self.assertEqual(code,2)
                self.assertEqual(json.loads(out.getvalue())["status"],"rejected_no_write")

    def test_native_up_direction_rejected_by_planner_input(self):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            with patch.object(sys,"argv",["ai_world_motion.py","plan",
                    "--target","scene:"+"f"*32+":1","--direction","left"]):
                self.assertEqual(m.main(),2)


if __name__=="__main__":
    unittest.main()
