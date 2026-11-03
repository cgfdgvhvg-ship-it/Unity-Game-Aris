"""Source transactions: offline static copy, dependency integrity and AI ownership."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unity_data import SCENE, World, WorldError, digest
from patching import plan, apply_yaml, preview_yaml, Dumper
from model_import import _unpack, import_model
from test_world import fixture, GUID


class StaticPrefabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);fixture(self.root)
        self.prefab="Assets/Prop.prefab"
        text="%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
        objects=[(1,10,"GameObject",{"m_Name":"ImportedProp","m_Component":[{"component":{"fileID":11}},{"component":{"fileID":12}}],"m_IsActive":1}),
                 (4,11,"Transform",{"m_GameObject":{"fileID":10},"m_LocalPosition":{"x":0,"y":0,"z":0},"m_LocalRotation":{"x":0,"y":0,"z":0,"w":1},"m_LocalScale":{"x":1,"y":1,"z":1},"m_Father":{"fileID":0},"m_Children":[]}),
                 (65,12,"BoxCollider",{"m_GameObject":{"fileID":10},"m_Size":{"x":2,"y":4,"z":3},"m_Center":{"x":0,"y":2,"z":0},"m_Enabled":1})]
        for cls,ident,kind,data in objects:
            text+=f"--- !u!{cls} &{ident}\n"+yaml.dump({kind:data},Dumper=Dumper,sort_keys=False)
        (self.root/self.prefab).write_text(text);(self.root/(self.prefab+".meta")).write_text("fileFormatVersion: 2\nguid: "+"8"*32+"\n")
    def tearDown(self):self.tmp.cleanup()
    def transaction(self):
        files=[SCENE,SCENE+".meta",self.prefab,self.prefab+".meta"]
        return {"schema_version":2,"transaction_id":"static-prop-test-0001","idempotency_key":"static-prop-test-0001",
                "reason":"AI explicitly chose this location and orientation", "expected_files":{p:digest(self.root/p) for p in files},
                "operations":[{"id":"place-prop","op":"place_static_prefab","prefab_path":self.prefab,"name":"ChosenProp",
                               "parent":f"scene:{GUID}:100","world_position":[11,2,26],"yaw_degrees":30,"local_scale":[2,2,2]}]}
    def test_preview_then_apply_preserves_old_ids_metadata_and_explicit_world_intent(self):
        tx=self.transaction();before=World(self.root);source=digest(self.root/SCENE);meta=digest(self.root/(SCENE+".meta"))
        report=preview_yaml(self.root,tx)
        self.assertEqual(source,digest(self.root/SCENE));self.assertTrue(report["resolved_objects"])
        result=apply_yaml(self.root,tx,True);after=World(self.root)
        self.assertTrue(set(before.docs)<set(after.docs));self.assertEqual(meta,digest(self.root/(SCENE+".meta")))
        self.assertEqual(result["backend"],"python_yaml");self.assertFalse(result["resolved_objects"][0]["prefab_connection"])
        go=after.resolve(result["resolved_objects"][0]["id"])
        np.testing.assert_allclose(after.object(go)["world_position_m"],[11,2,26],atol=1e-10)
        np.testing.assert_allclose(after.object(go)["world_forward"],[.5,0,np.sqrt(.75)],atol=1e-10)
        self.assertNotIn("placement_valid",result)
        self.assertTrue(any(row.get("result",{}).get("target",{}).get("name")=="ChosenProp" for row in result["post_edit_observations"]))
        # Replaying the same source-hash transaction cannot create another copy.
        with self.assertRaises(WorldError):apply_yaml(self.root,tx,True)
    def test_same_transaction_resolves_the_same_ids_without_writing(self):
        tx=self.transaction();a=plan(self.root,tx)[0];b=plan(self.root,tx)[0]
        self.assertEqual(a["resolved_objects"],b["resolved_objects"])
    def test_stale_prefab_and_unsupported_script_fail_before_source_mutation(self):
        tx=self.transaction();before=digest(self.root/SCENE)
        p=self.root/self.prefab;p.write_text(p.read_text()+"\n")
        with self.assertRaises(WorldError):apply_yaml(self.root,tx,True)
        tx=self.transaction();p.write_text(p.read_text().replace("!u!65 &12","!u!114 &12").replace("BoxCollider:","MonoBehaviour:"))
        tx["expected_files"][self.prefab]=digest(p)
        with self.assertRaises(WorldError):apply_yaml(self.root,tx,True)
        self.assertEqual(before,digest(self.root/SCENE))
    def test_failed_postwrite_validation_rolls_back_added_documents(self):
        tx=self.transaction();before=(self.root/SCENE).read_bytes()
        with patch("observations.inspect",side_effect=RuntimeError("deliberate structural failure")):
            with self.assertRaises(RuntimeError):apply_yaml(self.root,tx,True)
        self.assertEqual(before,(self.root/SCENE).read_bytes())
    def test_name_collision_and_missing_dependency_hash_are_rejected(self):
        tx=self.transaction();tx["operations"][0]["name"]="House"
        with self.assertRaises(WorldError):plan(self.root,tx)
        tx=self.transaction();tx["expected_files"].pop(self.prefab+".meta")
        with self.assertRaises(WorldError):plan(self.root,tx)
    def test_far_pivot_collider_is_reported_and_no_design_verdict_is_invented(self):
        from observations import inspect
        source=self.root/SCENE
        text=source.read_text()
        # One object's pivot is 70m away; its saved box still contains the query.
        text=text.replace('--- !u!4 &301\n', '--- !u!65 &999\nBoxCollider:\n  m_GameObject: {fileID: 300}\n  m_Size: {x: 200, y: 20, z: 200}\n  m_Center: {x: 0, y: 0, z: 0}\n--- !u!4 &301\n')
        marker='  - component: {fileID: 301}\n'
        text=text.replace(marker,marker+'  - component: {fileID: 999}\n');source.write_text(text)
        r=inspect(World(self.root),{'x':70,'y':0,'z':0,'radius':5,'native':False,'geometry':True})
        item=next(row for row in r['nearby_scene_objects'] if row['id'].endswith(':300'))
        self.assertEqual(item['bounds_source'],'saved_collider_envelope')
        self.assertEqual(item['distance_to_bounds_m'],0)
        self.assertNotIn('placement_valid',r)

    def test_import_never_overwrites_existing_assets_or_stale_source(self):
        source=self.root/'model.zip';source.write_bytes(b'not-a-real-zip')
        destination='Assets/WorldImports/Existing';p=self.root/destination;p.mkdir(parents=True)
        with self.assertRaises(WorldError):import_model(self.root,source,destination,digest(source),.01)
        with self.assertRaises(WorldError):import_model(self.root,source,'Assets/WorldImports/New','0'*64,.01)

    def test_native_target_relative_axes_follow_its_authored_yaw(self):
        from observations import inspect
        target={"id":"terrain:test:0","position_m":[0,0,0],"yaw_degrees":90}
        with patch("observations.NativeTerrain.find_instance",return_value=target):
            result=inspect(World(self.root),{"target":target["id"],"native":False,"geometry":False,"radius":50})
        for item in result["nearby_scene_objects"]:
            x,y,z=item["relative_m"]
            np.testing.assert_allclose(item["relative_in_target_axes_m"],[-z,y,x],atol=1e-10)

    def test_bare_fbx_fails_before_unfingerprinted_companions_are_read(self):
        source=self.root/'model.fbx';source.write_bytes(b'FBX')
        out=self.root/'unpacked';out.mkdir()
        with self.assertRaisesRegex(WorldError,"one ZIP"):_unpack(source,out)
        self.assertEqual(list(out.iterdir()),[])

    def test_offline_import_authors_real_mesh_pbr_and_prefab_files(self):
        import zipfile
        import io
        from PIL import Image
        from unity_data import documents
        source=self.root/'static.zip'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('source/model.fbx',b'mocked binary FBX decoder input')
            for role,value,mode in [('BaseColor',(20,40,80),'RGB'),('Normal',(128,128,255),'RGB'),('Metallic',71,'L'),('Roughness',33,'L')]:
                out=io.BytesIO();Image.new(mode,(2,2),value).save(out,format='PNG');archive.writestr('textures/model_'+role+'.png',out.getvalue())
        geometry=(np.array([[0,0,0],[1,0,0],[0,2,1]],dtype='f4'),np.tile([0,0,1],(3,1)).astype('f4'),np.array([[0,0],[1,0],[0,1]],dtype='f4'),np.array([0,1,2],dtype='u4'),np.zeros(3))
        contract={'fbx_version':7700,'global_settings':{'UnitScaleFactor':1},'non_static_records':[]}
        destination='Assets/WorldImports/ImportTest'
        with patch('model_import._fbx_contract',return_value=contract),patch('model_import._geometry',return_value=geometry):
            preview=import_model(self.root,source,destination,digest(source),.01,512)
            self.assertFalse((self.root/destination).exists())
            result=import_model(self.root,source,destination,digest(source),.01,512,True)
        self.assertEqual(preview['mesh']['guid'],result['mesh']['guid'])
        _,docs=documents(self.root/destination/'Geometry.asset');mesh=docs[0]['data']
        self.assertEqual(mesh['m_VertexData']['m_VertexCount'],3)
        self.assertEqual(len(bytes.fromhex(mesh['m_IndexBuffer'])),12)
        packed=Image.open(self.root/destination/'MetallicSmoothness.png')
        self.assertEqual(packed.getpixel((0,0)),(71,0,0,222))
        _,prefab=documents(self.root/result['prefab_path'])
        self.assertEqual({d['kind'] for d in prefab},{'GameObject','Transform','MeshFilter','MeshRenderer','MeshCollider'})

    def test_zip_traversal_cannot_write_outside_import_directory(self):
        import zipfile
        source=self.root/"bad.zip"
        with zipfile.ZipFile(source,"w") as z:z.writestr("../escaped.fbx",b"bad")
        out=self.root/"unpacked";out.mkdir()
        with self.assertRaises(WorldError):_unpack(source,out)
        self.assertFalse((self.root/"escaped.fbx").exists())


if __name__=="__main__":unittest.main()
