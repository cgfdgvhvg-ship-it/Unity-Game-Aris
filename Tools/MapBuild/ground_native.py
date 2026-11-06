"""Materialize core TerrainData and real building LOD meshes in a LFS checkout."""
from __future__ import annotations
import copy, hashlib, json, math, re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import yaml
from native_assets import mesh_asset
from lod_winding import candidate_winding

def simplify(raw,level):
    """Material/normal/UV aware clustering for distant LODs; LOD0 is untouched."""
    d=yaml.load(raw,Loader=yaml.CSafeLoader)['Mesh'] if not raw.startswith('%YAML') else yaml.load(re.split(r'(?m)^--- .*\n',raw,maxsplit=1)[1],Loader=yaml.CSafeLoader)['Mesh']
    vd=d['m_VertexData'];buf=bytes.fromhex(str(vd['_typelessdata']))
    assert len(buf)==vd['m_VertexCount']*48,'Unexpected generated vertex stride'
    v=np.frombuffer(buf,dtype='<f4').reshape(-1,12)
    inds=np.frombuffer(bytes.fromhex(str(d['m_IndexBuffer'])),dtype='<u4')
    span=float(np.ptp(v[:,:3],axis=0).max())
    voxel=max(.15,span/110) if level==1 else max(.40,span/40)
    positions=[];normals=[];tangents=[];uvs=[];indices=[];groups=[];offset=0;first=0
    for sub in d['m_SubMeshes']:
        old=inds[sub['firstByte']//4:sub['firstByte']//4+sub['indexCount']].reshape(-1,3)
        if not len(old):raise ValueError('Empty source material submesh')
        used,inv=np.unique(old,return_inverse=True);local=v[used]
        key=np.column_stack((np.floor(local[:,:3]/voxel),np.round(local[:,3:6]*(2 if level==1 else 1)),np.floor(local[:,10:12]*(2 if level==1 else .5)))).astype('i4')
        _,representative,mapped=np.unique(key,axis=0,return_index=True,return_inverse=True)
        chosen=local[representative];tri=mapped[inv].reshape(-1,3)
        keep=(tri[:,0]!=tri[:,1])&(tri[:,0]!=tri[:,2])&(tri[:,1]!=tri[:,2]);tri=tri[keep]
        if len(tri):
            q=chosen[tri,:3];tri=tri[np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)>1e-7]
        if not len(tri):chosen=v[old[0]];tri=np.array([[0,1,2]])
        # Keep the original material slots and a valid triangle for tiny authored details.
        active,remap=np.unique(tri,return_inverse=True);chosen=chosen[active];tri=remap.reshape(-1,3)
        # Keep the saved LOD front faces consistent with the source vertex normals.
        # Repairs only proposed index ordering at authoring time; does not touch UV,
        # tangents, original LOD0, materials or any existing native LFS core files.
        tri,_quality=candidate_winding(chosen,tri)
        tri=tri.reshape(-1)
        positions.extend(chosen[:,:3]);normals.extend(chosen[:,3:6]);tangents.extend(chosen[:,6:10]);uvs.extend(chosen[:,10:12])
        indices.extend(tri+offset);groups.append((first,len(tri)));first+=len(tri);offset+=len(chosen)
    return positions,normals,uvs,indices,tangents,groups

def materialize(root):
    import UnityPy
    from export_index import export
    root=Path(root);report_path=root/'Docs/GROUND_REVIEW_REPORT.json'
    report=json.loads(report_path.read_text());layout_path=root/'Docs/MAP_LAYOUT.json';layout=json.loads(layout_path.read_text())
    terrain_index=json.loads((root/'Docs/TERRAIN_INDEX.json').read_text())
    plan=json.loads((root/'Docs/FOREST_PLANTING_PLAN.json').read_text())['placements']
    source_report=json.loads((root/'Docs/MAP_BUILD_REPORT.json').read_text());tree_seed=None
    terrain=SimpleNamespace(data={},env={});accepted=[];rejected=[];hashes={};new_by_tile=Counter()
    for path,old_info in source_report['terrain_files'].items():
        f=root/path;raw=f.read_bytes();assert not raw.startswith(b'version https://git-lfs'),f'Fetch native LFS bytes first: {path}'
        env=UnityPy.load(raw);obj=next(o for o in env.objects if o.type.name=='TerrainData');d=obj.read_typetree()
        tag=re.search(r'Terrain_(\d_\d)_',f.name).group(1);i,j=map(int,tag.split('_'));ox=(i-2)*1000;oz=(j-2)*1000
        db=d['m_DetailDatabase'];h=np.asarray(d['m_Heightmap']['m_Heights']).reshape(2049,2049).astype(float)/32766*800-120
        index=next(t for t in terrain_index['tiles'] if t['tile']==tag)
        proto={p['path']:n for n,p in enumerate(index['tree_and_rock_prototypes'])}
        before_heights=copy.deepcopy(d['m_Heightmap']['m_Heights'])
        preserved_details=copy.deepcopy(db);preserved_details.pop('m_TreeInstances')
        alpha_bytes={o.path_id:hashlib.sha256(o.get_raw_data()).hexdigest() for o in env.objects if o.type.name=='Texture2D'}
        existing=np.array([(t['position']['x']*1000+ox,t['position']['z']*1000+oz,t['index']) for t in db['m_TreeInstances']],dtype=float)
        tree_indices={n for n,p in enumerate(index['tree_and_rock_prototypes']) if p['category']=='tree'}
        seed=next((copy.deepcopy(t) for t in db['m_TreeInstances'] if t['index'] in tree_indices),tree_seed)
        assert seed is not None,'A source tree instance is required for foliage color/lighting defaults'
        tree_seed=copy.deepcopy(seed)
        for p in [p for p in plan if p['tile']==tag]:
            x,z=p['position_xz_m'];fx=(x-ox)*2048/1000;fz=(z-oz)*2048/1000
            ix=int(np.clip(math.floor(fx),1,2046));iz=int(np.clip(math.floor(fz),1,2046));dx=fx-ix;dz=fz-iz
            y=float((h[iz,ix]*(1-dx)+h[iz,ix+1]*dx)*(1-dz)+(h[iz+1,ix]*(1-dx)+h[iz+1,ix+1]*dx)*dz)
            slope=math.hypot(h[iz,ix+1]-h[iz,ix-1],h[iz+1,ix]-h[iz-1,ix])/(2*1000/2048)
            if y < -38.07552+2.0 or slope>math.tan(math.radians(30)):
                rejected.append({'id':p['id'],'reason':'native shoreline/slope'});continue
            prototype=proto[p['path']]
            # Serialized float32 coordinates drift slightly; centimetre rounding can duplicate ties.
            same=(existing[:,2]==prototype)&((existing[:,0]-x)**2+(existing[:,1]-z)**2 < .05**2)
            if not np.any(same):
                tree=copy.deepcopy(seed);tree.update(position={'x':(x-ox)/1000,'y':(y+120)/800,'z':(z-oz)/1000},
                    widthScale=p['width_scale'],heightScale=p['height_scale'],rotation=math.radians(p['yaw_degrees']),index=proto[p['path']])
                db['m_TreeInstances'].append(tree);existing=np.vstack((existing,[x,z,prototype]))
            accepted.append(p);new_by_tile[tag]+=1
        assert before_heights==d['m_Heightmap']['m_Heights'],'Forest patch changed terrain heights'
        obj.save_typetree(d);f.write_bytes(env.file.save())
        # Reopen the actual saved binary; indexes must reflect the serialized result.
        check=UnityPy.load(f.read_bytes());saved=next(o for o in check.objects if o.type.name=='TerrainData');native=saved.read_typetree()
        assert native['m_Heightmap']['m_Heights']==before_heights
        assert len(native['m_DetailDatabase']['m_TreeInstances'])==len(db['m_TreeInstances'])
        remaining_details=copy.deepcopy(native['m_DetailDatabase']);remaining_details.pop('m_TreeInstances')
        assert remaining_details==preserved_details,'Forest patch changed detail maps or prototype settings'
        assert alpha_bytes=={o.path_id:hashlib.sha256(o.get_raw_data()).hexdigest() for o in check.objects if o.type.name=='Texture2D'},'Embedded terrain alpha textures changed'
        terrain.data[tag]=native;terrain.env[tag]=(check,saved)
        hashes[path]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'size':f.stat().st_size}
        next(t for t in layout['tile_reports'] if t['tile']==tag)['remaining_terrain_instances']=len(db['m_TreeInstances'])
    export(terrain,root/'Docs',root/'Tools/MapBuild')
    for path in [root/'Docs/MAP_BUILD_REPORT.json',root/'Docs/NATIVE_TERRAIN_VERIFICATION.json']:
        data=json.loads(path.read_text());data['terrain_files']=hashes
        if 'tiles' in data:
            for t in data['tiles']:t['indexed_instance_count']=len(terrain.data[t['tile']]['m_DetailDatabase']['m_TreeInstances'])
        path.write_text(json.dumps(data,indent=2)+'\n')
    lods={};cpu_meshes=0;checked_meshes=0
    for name in layout['models']:
        path=root/f'Assets/AarisWorld/Models/{name}/Geometry.asset';raw=path.read_text()
        assert raw.startswith('%YAML'),f'Expected materialized native Mesh: {path}'
        levels=[]
        for level in [1,2]:
            pos,norm,uv,ind,tangent,groups=simplify(raw,level)
            out=path.with_name(f'Geometry_LOD{level}.asset')
            record=mesh_asset(out,pos,norm,uv,ind,raw,name=name+f'_LOD{level}',tangent=tangent,groups=groups)
            levels.append(record['triangles'])
            assert record['triangles']<=layout['models'][name]['triangles']
        lods[name]={'lod0_triangles':layout['models'][name]['triangles'],'lod1_triangles':levels[0],'lod2_triangles':levels[1]}
    for path in (root/'Assets/AarisWorld').rglob('*.asset'):
        raw=path.read_bytes()
        if raw.startswith(b'version https://git-lfs'):raise ValueError('Unmaterialized mesh '+str(path))
        if raw.startswith(b'%YAML') and re.search(rb'(?m)^Mesh:\r?$',raw):
            cpu_meshes+=int(bool(re.search(rb'(?m)^  m_IsReadable: 1\r?$',raw)))
            patched=re.sub(rb'(?m)^  m_IsReadable:[^\r\n]*',b'  m_IsReadable: 0',raw)
            path.write_bytes(patched);checked_meshes+=1
    layout['ground_review']={'new_native_tree_count':len(accepted),'saved_forest_plan':'Docs/FOREST_PLANTING_PLAN.json','building_lod_levels':3}
    layout_path.write_text(json.dumps(layout,indent=2)+'\n')
    current_index=json.loads((root/'Docs/TERRAIN_INDEX.json').read_text())
    trees=sum(t['terrain_instances'].get('tree',0) for t in current_index['tiles'])
    report.update(native_assets_materialized=True,accepted_new_trees=len(accepted),rejected_new_trees=rejected,
        new_trees_by_tile=dict(new_by_tile),total_tree_count=trees,
        total_trees_by_tile={t['tile']:t['terrain_instances'].get('tree',0) for t in current_index['tiles']},
        cpu_readable_mesh_copies_removed=cpu_meshes,non_readable_generated_mesh_count=checked_meshes,
        terrain_detail_maps_prototypes_and_alpha_textures_preserved=True,building_lod_triangles=lods)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return report

if __name__=='__main__':materialize(Path.cwd())
