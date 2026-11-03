import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch as mock_patch
import numpy as np

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'MapBuild'))
from test_world import fixture
from native_assets import mesh_asset
from unity_data import documents, digest, WorldError
from mesh_faces import arrays, remove_triangles
from patching import preview_yaml, apply_yaml


class MeshFaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);fixture(self.root)
        self.path='Assets/Panel.asset'
        template=base64.b64decode((pathlib.Path(__file__).resolve().parents[2]/'MapBuild/mesh_template.b64').read_text()).decode()
        mesh_asset(self.root/self.path,np.array([[0,0,0],[1,0,0],[0,2,0],[1,2,0]],dtype='f4'),
                   np.tile([0,0,1],(4,1)),np.array([[0,0],[1,0],[0,1],[1,1]]),
                   np.array([0,1,2,1,3,2]),template,groups=[(0,3),(3,3)])
    def tearDown(self):self.temp.cleanup()
    def mesh(self):return documents(self.root/self.path)[1][0]['data']
    def patch(self):
        return {'schema_version':2,'transaction_id':'remove-panel-0001','idempotency_key':'remove-panel-0001',
                'reason':'Remove one inspected door panel while retaining its material slot and adjacent wall',
                'expected_files':{p:digest(self.root/p)for p in (self.path,self.path+'.meta')},
                'operations':[{'id':'panel','op':'remove_mesh_triangles','path':self.path,'file_id':4300000,
                               'selections':[{'submesh':0,'triangles':[0]}]}]}
    def test_preview_and_apply_remove_faces_keep_slots_vertex_attributes_and_meta(self):
        before=(self.root/self.path).read_bytes();meta=(self.root/(self.path+'.meta')).read_bytes();old=self.mesh()
        preview=preview_yaml(self.root,self.patch());self.assertTrue(preview['preview'])
        self.assertEqual((self.root/self.path).read_bytes(),before)
        result=apply_yaml(self.root,self.patch(),True);new=self.mesh()
        self.assertEqual(new['m_VertexData'],old['m_VertexData'])
        self.assertEqual(new['m_SubMeshes'][0]['indexCount'],0)
        np.testing.assert_array_equal(arrays(new)[1][1],arrays(old)[1][1])
        self.assertEqual((self.root/(self.path+'.meta')).read_bytes(),meta)
        self.assertEqual(result['operation_after'][0]['state']['triangles_by_submesh'],[0,1])
    def test_invalid_and_total_removal_never_changes_source(self):
        before=(self.root/self.path).read_bytes()
        for selection in ([{'submesh':0,'triangles':[1]}],[{'submesh':2,'triangles':[0]}],
                          [{'submesh':0,'triangles':[0,0]}],
                          [{'submesh':0,'triangles':[0]},{'submesh':1,'triangles':[0]}]):
            with self.subTest(selection=selection),self.assertRaises(WorldError):remove_triangles(self.mesh(),selection)
        self.assertEqual((self.root/self.path).read_bytes(),before)
    def test_stale_metadata_blocks_geometry_write(self):
        patch=self.patch();(self.root/(self.path+'.meta')).write_text('changed')
        with self.assertRaises(WorldError):apply_yaml(self.root,patch,True)
    def test_unity_preview_receives_the_already_edited_mesh_in_its_private_project(self):
        import engine
        (self.root/'Packages').mkdir();(self.root/'ProjectSettings').mkdir()
        before=(self.root/self.path).read_bytes()
        def launch(arguments,**kwargs):
            project=pathlib.Path(arguments[arguments.index('-projectPath')+1])
            mesh=documents(project/self.path)[1][0]['data']
            self.assertEqual([s['indexCount']for s in mesh['m_SubMeshes']],[0,3])
            pathlib.Path(kwargs['env']['AARIS_WORLD_RESPONSE']).write_text(json.dumps({'status':'ok'}))
            return SimpleNamespace(wait=lambda timeout:0,poll=lambda:0,pid=1)
        with mock_patch('engine.capabilities',return_value={'ready':True}),mock_patch.dict(os.environ,{'UNITY_EDITOR_PATH':'/simulated-editor'}),mock_patch('engine.subprocess.Popen',side_effect=launch):
            result=engine.run(self.root,{'command':'preview'},self.patch())
        self.assertTrue(result['preview'])
        self.assertEqual((self.root/self.path).read_bytes(),before)


if __name__=='__main__':unittest.main()
