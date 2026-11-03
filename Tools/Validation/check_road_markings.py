"""Geometry regressions: dash crossings must follow both planes of a bent road."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'MapBuild'))
from road_markings import project_markings,heights_on_mesh,PAINT_OFFSET_M

class RoadPaintTests(unittest.TestCase):
    def test_dash_split_across_twisted_paved_triangles(self):
        # Ground underneath cannot supply this elevated, non-planar paved surface.
        road=np.array([[-4,2,0],[4,2,0],[-4,3,30],[4,5,30]],float)
        tri=np.array([[0,2,1],[1,2,3]])
        points=np.array([[0,0,0],[0,0,30]])
        pos,ind,area=project_markings(road,tri,points)
        self.assertAlmostEqual(area['covered_area_m2'],area['paint_area_m2'],places=7)
        for weights in ((1,0,0),(0,1,0),(0,0,1),(.2,.3,.5),(1/3,1/3,1/3)):
            samples=(pos[ind]*np.array(weights)[None,:,None]).sum(axis=1)
            gaps=samples[:,1]-heights_on_mesh(road,tri,samples)
            np.testing.assert_allclose(gaps,PAINT_OFFSET_M,atol=1e-8)
        normals=np.cross(pos[ind[:,1]]-pos[ind[:,0]],pos[ind[:,2]]-pos[ind[:,0]])
        self.assertTrue((normals[:,1]>0).all())

    def test_either_road_winding_and_repeat_are_deterministic(self):
        road=np.array([[-4,2,0],[4,2,0],[-4,3,30],[4,5,30]],float)
        tri=np.array([[0,1,2],[1,3,2]])
        points=np.array([[0,0,0],[0,0,30]])
        a,b,_=project_markings(road,tri,points);c,d,_=project_markings(road,tri,points)
        np.testing.assert_array_equal(a,c);np.testing.assert_array_equal(b,d)

    def test_reject_paint_outside_pavement(self):
        road=np.array([[-4,0,0],[4,0,0],[-4,0,30],[4,0,30]],float)
        with self.assertRaises(AssertionError):
            project_markings(road,np.array([[0,2,1],[1,2,3]]),[[12,0,0],[12,0,30]])

if __name__=='__main__':unittest.main()
