import copy
import json
import math
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch as mock_patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unity_data import SCENE, World, WorldError, digest, pointer, safe_path
from terrain import NativeTerrain, interpolate
from patching import apply_yaml, plan, preview_yaml, atomic_write
from retention import expired
from world import dispatch, performance
from fetch_assets import required
from capabilities import schema as automation_schema
from observations import inspect, runtime, usages

GUID = "1"*32
MAT = "Assets/Test.mat"


def fixture(root):
    scene = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
    for go, tr, name, parent, pos, rot, scale, children in [
        (100,101,"Root",0,[0,0,30],[0,math.sqrt(.5),0,math.sqrt(.5)],[2,1,3],[201]),
        (200,201,"House",101,[1,2,3],[0,0,0,1],[1,1,1],[]),
        (300,301,"House",0,[0,0,0],[0,0,0,1],[1,1,1],[])]:
        scene += f"--- !u!1 &{go}\nGameObject:\n  m_Name: {name}\n  m_IsActive: 1\n  m_Component:\n  - component: {{fileID: {tr}}}\n"
        scene += f"--- !u!4 &{tr}\nTransform:\n  m_GameObject: {{fileID: {go}}}\n  m_Father: {{fileID: {parent}}}\n"
        for key, axes, values in [("m_LocalPosition","xyz",pos),("m_LocalRotation","xyzw",rot),("m_LocalScale","xyz",scale)]:
            scene += "  "+key+": {"+", ".join(f"{a}: {v}" for a,v in zip(axes,values))+"}\n"
        scene += "  m_Children: "+("[]\n" if not children else "\n"+"".join(f"  - {{fileID: {c}}}\n" for c in children))
    p = root/SCENE; p.parent.mkdir(parents=True); p.write_text(scene)
    Path(str(p)+".meta").write_text("fileFormatVersion: 2\nguid: "+GUID+"\n")
    (root/MAT).write_text("%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!21 &2100000\nMaterial:\n  m_Name: Wall\n  m_SavedProperties:\n    m_Colors:\n    - _BaseColor: {r: 0.2, g: 0.3, b: 0.4, a: 1}\n")
    (root/(MAT+".meta")).write_text("fileFormatVersion: 2\nguid: "+"2"*32+"\n")


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); fixture(self.root)
    def tearDown(self): self.tmp.cleanup()
    def transform_patch(self):
        return {"schema_version":1,"reason":"Move the test house along its parent-local X axis",
                "expected_files":{p:digest(self.root/p) for p in (SCENE,SCENE+".meta")},
                "operations":[{"op":"set_transform","target":f"scene:{GUID}:200","local_position":[2,2,3]}]}
    def transform_patch_v2(self):
        return {"schema_version":2,"transaction_id":"tx:test:0001","idempotency_key":"idem:test:0001",
                "reason":"Move the selected object in world space and return its neighbourhood",
                "expected_files":{p:digest(self.root/p) for p in (SCENE,SCENE+".meta")},
                "operations":[{"id":"move-house","op":"set_transform","target":f"scene:{GUID}:200",
                               "world_position":[11,2,26]}]}
    def test_hierarchy_world_coordinates_and_unit_forward(self):
        w = World(self.root); r = w.object(200)
        np.testing.assert_allclose(r["world_position_m"],[9,2,28],atol=1e-10)
        np.testing.assert_allclose(r["world_forward"],[1,0,0],atol=1e-10)
    def test_ambiguous_name_is_rejected(self):
        with self.assertRaises(WorldError): World(self.root).resolve("House")
        with self.assertRaises(WorldError): World(self.root).resolve("scene:"+"3"*32+":200")
    def test_scan_and_plan_are_read_only(self):
        before = digest(self.root/SCENE); dispatch(self.root,{"command":"scan","limit":2})
        report,_ = plan(self.root,self.transform_patch())
        self.assertEqual(digest(self.root/SCENE),before); self.assertTrue(report["dry_run"])
        self.assertIn(SCENE,report["diffs"])
    def test_apply_updates_core_and_preserves_ids_meta_and_unrelated_document(self):
        p = self.transform_patch(); old = World(self.root); oldtext = old.text
        marker = old.docs[301]; untouched = oldtext[marker["start"]:marker["end"]]
        meta = (self.root/(SCENE+".meta")).read_bytes()
        result = apply_yaml(self.root,p,True); new = World(self.root)
        np.testing.assert_allclose(new.object(200)["world_position_m"],[9,2,26],atol=1e-10)
        self.assertEqual(set(new.docs),set(old.docs)); self.assertIn(untouched,new.text)
        self.assertEqual((self.root/(SCENE+".meta")).read_bytes(),meta)
        self.assertFalse(result["dry_run"])
    def test_stale_source_or_meta_is_rejected(self):
        p = self.transform_patch(); (self.root/(SCENE+".meta")).write_text("changed")
        with self.assertRaises(WorldError): apply_yaml(self.root,p,True)
    def test_material_write_is_actual_saved_property(self):
        p = {"schema_version":1,"reason":"Adjust shared wall tint","expected_files":{f:digest(self.root/f) for f in (MAT,MAT+".meta")},
             "operations":[{"op":"set_material_color","path":MAT,"file_id":2100000,"property":"_BaseColor","rgba":[.4,.5,.6,1]}]}
        apply_yaml(self.root,p,True)
        self.assertEqual(World(self.root).asset_docs(MAT)["docs"][0]["data"]["m_SavedProperties"]["m_Colors"][0]["_BaseColor"]["g"],.5)
    def test_v2_world_position_is_resolved_through_parent_and_state_is_typed(self):
        patch=self.transform_patch_v2();apply_yaml(self.root,patch,True)
        np.testing.assert_allclose(World(self.root).object(200)["world_position_m"],[11,2,26],atol=1e-10)
        state={"schema_version":2,"transaction_id":"tx:test:0002","idempotency_key":"idem:test:0002",
               "reason":"Rename only the selected saved object","expected_files":{p:digest(self.root/p) for p in (SCENE,SCENE+".meta")},
               "operations":[{"id":"rename-house","op":"set_object_state","target":f"scene:{GUID}:200","name":"RoofCover"}]}
        apply_yaml(self.root,state,True);self.assertEqual(World(self.root).object(200)["name"],"RoofCover")
    def test_preview_is_isolated_and_returns_post_edit_context(self):
        before=digest(self.root/SCENE);result=preview_yaml(self.root,self.transform_patch_v2())
        self.assertEqual(digest(self.root/SCENE),before);self.assertTrue(result["preview"]);self.assertTrue(result["dry_run"])
        self.assertTrue(result["post_edit_observations"])
        np.testing.assert_allclose(result["post_edit_observations"][0]["result"]["target"]["world_position_m"],[11,2,26])
    def test_parent_and_child_world_edits_use_final_hierarchy_in_both_orders(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); fixture(root)
                patch = self.transform_patch_v2()
                patch["expected_files"] = {p:digest(root/p) for p in (SCENE,SCENE+".meta")}
                parent = {"id":"parent", "op":"set_transform", "target":f"scene:{GUID}:100",
                          "world_position":[10,0,30], "local_scale":[3,2,4],
                          "local_rotation_xyzw":[0,0,0,1]}
                patch["operations"].append(parent)
                if reverse: patch["operations"].reverse()
                result = apply_yaml(root, patch, True)
                np.testing.assert_allclose(World(root).object(200)["world_position_m"],[11,2,26],atol=1e-8)
                self.assertFalse(result["dry_run"])
    def test_conflicting_world_and_local_writes_in_separate_operations_are_rejected(self):
        patch = self.transform_patch_v2()
        patch["operations"].append({"id":"conflict", "op":"set_transform",
                                    "target":f"scene:{GUID}:200", "local_position":[0,0,0]})
        original = (self.root/SCENE).read_bytes()
        with self.assertRaisesRegex(WorldError,"Conflicting transform"):
            apply_yaml(self.root,patch,True)
        self.assertEqual((self.root/SCENE).read_bytes(),original)
    def test_finite_but_wrong_written_position_is_rolled_back(self):
        patch = self.transform_patch_v2(); original = (self.root/SCENE).read_bytes()
        def wrong_write(path, data):
            if Path(path) == self.root/SCENE and data != original:
                data = re.sub(rb"(?s)(--- !u!4 &201\n.*?m_LocalPosition: \{x: )([^,]+)",
                              lambda m:m[1]+str(float(m[2])+1).encode(),data,count=1)
            atomic_write(path,data)
        with mock_patch('patching.atomic_write',side_effect=wrong_write):
            with self.assertRaisesRegex(WorldError,"Postcondition failed"):
                apply_yaml(self.root,patch,True)
        self.assertEqual((self.root/SCENE).read_bytes(),original)
    def test_context_capsule_reports_neighbours_without_making_a_design_decision(self):
        w=World(self.root);result=inspect(w,{"target":f"scene:{GUID}:200","radius":50,"limit":20,"native":False,"geometry":False})
        self.assertEqual(result["target"]["name"],"House")
        self.assertGreaterEqual(len(result["nearby_scene_objects"]),1)
        self.assertNotIn("placement_valid",result)
        self.assertFalse(result["coverage"]["physics_tested"])
    def test_schema_v2_requires_ids_and_exposes_native_and_prefab_operations(self):
        contract=automation_schema();self.assertEqual(contract["protocol_version"],2)
        self.assertIn("terrain_instance_move",contract["write_operations"]);self.assertIn("instantiate_prefab",contract["write_operations"])
        patch=self.transform_patch_v2();patch["operations"][0].pop("id")
        with self.assertRaises(WorldError):plan(self.root,patch)
    def test_schema_bootstraps_before_scene_or_lfs_assets_are_fetched(self):
        empty=self.root/"sparse";empty.mkdir()
        result=dispatch(empty,{"command":"schema"})
        self.assertEqual(result["result"]["protocol_version"],2)
        self.assertEqual(result["source_fingerprint"]["files"][0][1],"missing")
    def test_reverse_usage_and_runtime_evidence_are_explicitly_limited(self):
        use=self.root/"Assets/Use.prefab";use.write_text("%YAML 1.1\nmaterial: {fileID: 2100000, guid: "+"2"*32+", type: 2}\n")
        script=self.root/"Assets/Load.cs";script.write_text("class Load { void Update() { UnityEngine.SceneManagement.SceneManager.LoadScene(\"Map\"); } }\n")
        result=usages(World(self.root),{"path":MAT});self.assertEqual(result["text_serialized_usages"][0]["path"],"Assets/Use.prefab")
        evidence=runtime(self.root,{"search":"LoadScene","offset":0,"limit":10});self.assertEqual(evidence["total"],1)
    def test_rollback_when_post_write_validation_fails(self):
        p = self.transform_patch(); original = (self.root/SCENE).read_bytes()
        real = World.world_matrix
        def fail_after_write(w,*args,**kwargs):
            if (w.root/SCENE).read_bytes()!=original: raise WorldError("Injected validation failure")
            return real(w,*args,**kwargs)
        with mock_patch.object(World,"world_matrix",fail_after_write):
            with self.assertRaises(WorldError): apply_yaml(self.root,p,True)
        self.assertEqual((self.root/SCENE).read_bytes(),original)
    def test_path_escape_and_remote_mutations_rejected(self):
        for p in ("../secret","/tmp/secret","Tools/World/world.py","."):
            with self.assertRaises(WorldError): safe_path(self.root,p)
        with self.assertRaises(WorldError): dispatch(self.root,{"command":"apply"},True)
        with self.assertRaises(WorldError): dispatch(self.root,{"command":"height","x":float("nan"),"z":0},True)
    def test_invalid_scale_is_not_written(self):
        p = self.transform_patch();p["operations"][0]["local_scale"]=[0,1,1]
        with self.assertRaises(WorldError): apply_yaml(self.root,p,True)
    def test_invalid_patch_operations_and_hashes_are_rejected(self):
        for value in ([], ["set_transform"]):
            p=self.transform_patch();p["operations"]=value
            with self.assertRaises(WorldError): plan(self.root,p)
        p=self.transform_patch();p["expected_files"][SCENE]="not a hash"
        with self.assertRaises(WorldError): plan(self.root,p)
    def test_fetcher_selects_only_requested_asset_and_rejects_writes(self):
        self.assertEqual(required(World(self.root),{"command":"asset","path":MAT}),[MAT])
        self.assertEqual(required(World(self.root),{"command":"object","target":f"scene:{GUID}:200"}),[])
        with self.assertRaises(WorldError): required(World(self.root),{"command":"apply"})
    def test_native_pointer_is_never_interpreted_as_empty_tile(self):
        p = self.root/"Assets/Data.asset"; p.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:"+"a"*64+"\nsize 53\n")
        self.assertTrue(pointer(p))
        native=NativeTerrain(World(self.root))
        with self.assertRaisesRegex(WorldError,"LFS pointer"):
            native.load({"asset":{"path":"Assets/Data.asset","file_id":15600000},"origin_m":[0,0,0]})
    def test_neighbour_inspection_fetches_shapes_even_without_a_nearby_pivot(self):
        mesh = "Assets/LargeBuilding.asset"
        (self.root / mesh).write_text("version https://git-lfs.github.com/spec/v1\n")
        (self.root / (mesh+".meta")).write_text("fileFormatVersion: 2\nguid: "+"4"*32+"\n")
        scene = self.root / SCENE
        text = scene.read_text().replace("  - component: {fileID: 301}\n", "  - component: {fileID: 301}\n  - component: {fileID: 302}\n")
        text += "--- !u!33 &302\nMeshFilter:\n  m_GameObject: {fileID: 300}\n  m_Mesh: {fileID: 4300000, guid: "+"4"*32+", type: 2}\n"
        scene.write_text(text)
        w = World(self.root)
        for request in ({"x":1000,"y":0,"z":0}, {"target":f"scene:{GUID}:200"}):
            self.assertEqual(required(w,{"command":"inspect","native":False,**request}),[mesh])
            self.assertEqual(required(w,{"command":"inspect","native":False,"geometry":False,**request}),[])
    def test_performance_uses_device_samples_and_build_identity(self):
        p=self.root/"phone.jsonl";p.write_text(json.dumps({"reason":"sample","averageFps":52,"p95FrameMs":25,"buildGuid":"b1","androidPssKB":1234})+"\n")
        r=performance(p);self.assertEqual(r["average_sample_fps"],52);self.assertEqual(r["build_guids"],["b1"])


class HeightTests(unittest.TestCase):
    def test_plane_height_gradient_slope_and_edges(self):
        x,z=np.meshgrid(np.arange(5)*.5,np.arange(5)*.25);h=5+2*x+3*z
        r=interpolate(h,[0,0,0],[.5,.25],.4,.3)
        self.assertAlmostEqual(r["height_m"],6.7);self.assertEqual(r["gradient_dy_dx_dz"],[2.,3.])
        self.assertAlmostEqual(r["slope_degrees"],math.degrees(math.atan(math.sqrt(13))))
        self.assertAlmostEqual(interpolate(h,[0,0,0],[.5,.25],2,1)["height_m"],12)
        with self.assertRaises(WorldError): interpolate(h,[0,0,0],[.5,.25],2.1,1)


class RetentionTests(unittest.TestCase):
    def test_cleanup_scope_event_completion_and_ttl(self):
        now=datetime(2026,11,3,tzinfo=timezone.utc)
        r={"path":".github/workflows/world-query.yml","status":"completed","event":"workflow_dispatch",
           "display_title":"World query TTL=2h","updated_at":(now-timedelta(hours=3)).isoformat()}
        self.assertTrue(expired(r,"world-query.yml",now))
        for key,value in (("path",".github/workflows/explorer-checks.yml"),("status","in_progress"),
                          ("event","pull_request"),("display_title","World query TTL=0h"),("updated_at",now.isoformat())):
            changed={**r,key:value};self.assertFalse(expired(changed,"world-query.yml",now))


if __name__=="__main__": unittest.main()

