"""Verify the authored source migration. Sampled doorway rays are not Unity physics."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from mesh_faces import arrays,summary
from unity_data import World,digest,documents

CONTRACT='Tools/World/tree-house-20261103.postconditions.json'


def mesh_data(path):
    return next(d['data']for d in documents(path)[1]if d['kind']=='Mesh')


def ray_hits(positions,groups,start,end):
    triangles=positions[np.concatenate(groups)].astype(float)
    direction=np.asarray(end)-start;origin=np.asarray(start)
    e1=triangles[:,1]-triangles[:,0];e2=triangles[:,2]-triangles[:,0]
    q=np.cross(direction,e2);det=np.sum(e1*q,axis=1);valid=np.abs(det)>1e-10
    inv=np.divide(1,det,out=np.zeros_like(det),where=valid)
    s=origin-triangles[:,0];u=np.sum(s*q,axis=1)*inv;r=np.cross(s,e1)
    v=np.sum(direction*r,axis=1)*inv;t=np.sum(e2*r,axis=1)*inv
    return int(np.count_nonzero(valid&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>1e-5)&(t<1-1e-5)))


def accepts_historical_transition(root,path,original_sha):
    """Recognize only this explicitly authored hash transition, preserving the old report."""
    root=Path(root);contract=root/CONTRACT
    if not contract.exists():return False
    row=json.loads(contract.read_text())['meshes'].get(str(path))
    if not row or row['before_sha256']!=original_sha or digest(root/path)!=row['after_sha256']:return False
    return summary(mesh_data(root/path))['vertex_buffer_sha256']==row['vertex_buffer_sha256']


# PR #18's historical protection contract records the exact saved house prefab
# bytes before PR #19's two reviewed LOD-threshold-only changes. Preserve that
# stronger byte-for-byte guarantee by reversing exactly these two lines in memory
# and matching the original protected SHA256. Any other change fails closed.
RESIDENTIAL_MOBILE_LOD_PREFABS=frozenset(
    f'Assets/AarisWorld/Models/{name}/{name}.prefab' for name in (
        'a_frame_cabin','bungalow_house','detached_two_storey_house',
        'garage_apartment','pitched_roof_cottage','row_three_townhouses',
        'two_bedroom_garage_house',
    )
)


def preserved_or_reviewed_lod_only(root,path,expected_sha):
    source=(Path(root)/path).read_bytes()
    if hashlib.sha256(source).hexdigest()==expected_sha:return True
    if path not in RESIDENTIAL_MOBILE_LOD_PREFABS:return False
    for new,old in (
        (b'  - screenRelativeHeight: 0.28\n',b'  - screenRelativeHeight: 0.22\n'),
        (b'  - screenRelativeHeight: 0.095\n',b'  - screenRelativeHeight: 0.07\n'),
    ):
        if source.count(new)!=1:return False
        source=source.replace(new,old,1)
    return hashlib.sha256(source).hexdigest()==expected_sha


def verify(root):
    root=Path(root).resolve();contract=json.loads((root/CONTRACT).read_text());rays=0
    for path,row in contract['meshes'].items():
        assert digest(root/path)==row['after_sha256'],path+' differs from inspected migration'
        assert digest(root/(path+'.meta'))==row['meta_sha256'],path+' identity changed'
        facts=summary(mesh_data(root/path))
        assert facts['vertex_buffer_sha256']==row['vertex_buffer_sha256'],path+' vertex attributes changed'
        assert facts['triangles_by_submesh']==row['triangles_by_submesh'],path+' material slots changed'
    for path,sha in contract['tree_source_files'].items():assert digest(root/path)==sha,path+' tree source profile changed'
    for path,sha in contract['preserved_files'].items():
        assert preserved_or_reviewed_lod_only(root,path,sha),path+' protected source changed outside reviewed LOD fields'
    for probe in contract['doorway_samples']:
        folder=root/'Assets/AarisWorld/Models'/probe['model']
        for path in sorted(folder.glob('Geometry*.asset')):
            positions,groups,_=arrays(mesh_data(path))
            center=np.array(probe['center']);normal=probe['normal_axis'];side=2 if normal==0 else 0
            for offset in (-.28,0,.28):
                for dy in (.04,.28,.89,1.5,1.74):
                    start=center.copy();start[side]+=offset;start[1]=probe['foot_y']+dy;end=start.copy()
                    start[normal]-=.55;end[normal]+=.55
                    assert ray_hits(positions,groups,start,end)==0,(probe['model'],path.name,probe['center'],offset,dy,'sampled doorway blocked')
                    rays+=1
    world=World(root);models={Path(p).parent.name for p in contract['meshes']};bindings=0
    for model in sorted(models):
        path='Assets/AarisWorld/Models/'+model+'/Geometry.asset'
        guid=next(g for g,p in world.guid_paths.items()if p==path)
        users=[]
        for go in world.gos:
            components=world.components(go)
            if any(c['kind']=='MeshFilter'and c['data'].get('m_Mesh',{}).get('guid')==guid for c in components):
                users.append(go)
                assert any(c['kind']=='MeshCollider'and c['data'].get('m_Mesh',{}).get('guid')==guid and not c['data'].get('m_Convex')for c in components)
        assert users,model+' has no saved scene users';bindings+=len(users)
    return {'source_meshes_checked':len(contract['meshes']),'residential_instances_using_opened_meshes':bindings,
            'tree_source_files_checked':len(contract['tree_source_files']),'doorway_samples':len(contract['doorway_samples']),
            'clear_sampled_rays_across_all_lods':rays,'vertex_attributes_and_material_slots_preserved':True,
            'unity_import_render_or_physics_tested':False,
            'limits':'Discrete source-triangle rays, not continuous capsule sweeps, complete interior navigation, Unity cooking, rendering or device tests.'}


if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[2])))
