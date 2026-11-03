"""Regressions for source material semantics and URP's different AO channel."""
import base64,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Tools/MapBuild'))
from ground_review import documents
from native_assets import export_model

class MaterialImportTests(unittest.TestCase):
    def test_source_properties_and_orm_ao_repack_survive_cached_export(self):
        image=Image.fromarray(np.array([[[10,200,230,255],[250,20,40,255]]],dtype='u1'))
        material={'doubleSided':False,'normalTexture':{'index':0,'scale':.4},'occlusionTexture':{'index':0,'strength':.25}}
        stub=SimpleNamespace(g={'materials':[material],'textures':[{'source':0}]},removed_nodes=[],image=lambda _:image.copy(),
            geometry=lambda:(np.array([[0,0,0],[0,0,1],[1,0,0]],float),np.array([[0,1,0]]*3,float),np.array([[0,0],[0,1],[1,0]],float),np.array([0,1,2]),[(0,3)],[0],np.zeros(3)))
        template=base64.b64decode((ROOT/'Tools/MapBuild/mesh_template.b64').read_text()).decode()
        with tempfile.TemporaryDirectory(prefix='aaris-material-test-') as directory:
            source=Path(directory)/'source.glb';source.write_bytes(b'synthetic pinned material fixture')
            folder=Path(directory)/'Assets/Fixture'
            with patch('native_assets.Glb',return_value=stub):
                export_model(source,folder,template)
                m=documents(folder/'Material_00.mat')[0][3];f={k:v for e in m['m_SavedProperties']['m_Floats'] for k,v in e.items()}
                self.assertEqual((f['_Cull'],f['_BumpScale'],f['_OcclusionStrength'],m['m_DoubleSidedGI']),(2,.4,.25,0))
                ao=folder/'Image_00_occlusion.png';normal=folder/'Image_00_normal.png'
                np.testing.assert_array_equal(np.asarray(Image.open(ao))[:,:,1],np.asarray(image)[:,:,0])
                np.testing.assert_array_equal(np.asarray(Image.open(normal)),np.asarray(image))
                # Reproduce a cached legacy export with roughness in green, then repair it.
                image.save(ao)
                export_model(source,folder,template,reuse_images=True)
                np.testing.assert_array_equal(np.asarray(Image.open(ao))[:,:,1],np.asarray(image)[:,:,0])
                material['doubleSided']=True
                export_model(source,folder,template,reuse_images=True)
                m=documents(folder/'Material_00.mat')[0][3];f={k:v for e in m['m_SavedProperties']['m_Floats'] for k,v in e.items()}
                self.assertEqual((f['_Cull'],m['m_DoubleSidedGI']),(0,1))

if __name__=='__main__':unittest.main()
