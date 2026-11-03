"""Assertions on saved map structure and measured ground geometry.

These checks do not substitute for a Unity import, render, navigation or playtest.
They fail the assembly before generated assets can reach the repository branch.
"""
import hashlib,json,math,re
from pathlib import Path
import numpy as np
import yaml
from sculpt import SEA,STEP,sample

def validate(t,sites,roads,buildings,spawns,models):
    checks={};h=t.h
    def check(name,condition,detail):
        checks[name]={'passed':bool(condition),'detail':detail}
        assert condition,(name,detail)
    check('exactly_four_1000m_tiles',len(t.sources)==4 and h.shape==(4097,4097),list(t.sources))
    seams=[]
    for a,b,axis in [('1_1','2_1','X'),('1_2','2_2','X'),('1_1','1_2','Z'),('2_1','2_2','Z')]:
        def tile(tag):
            i,j=map(int,tag.split('_'));return np.asarray(t.data[tag]['m_Heightmap']['m_Heights']).reshape(2049,2049)
        aa,bb=tile(a),tile(b);diff=aa[:,-1]-bb[:,0] if axis=='X' else aa[-1,:]-bb[0,:]
        seams.append({'tiles':[a,b],'axis':axis,'maximum_difference_m':float(np.max(np.abs(diff))*800/32766)})
    check('all_terrain_edges_match',all(s['maximum_difference_m']==0 for s in seams),seams)
    boundary=np.r_[h[0],h[-1],h[:,0],h[:,-1]]
    check('outer_edges_below_ocean',float(boundary.max())<SEA-20,{'highest_boundary_m':float(boundary.max()),'sea_level_m':SEA})
    check('at_least_ten_districts',len(sites)>=10,len(sites))
    placed={b['model'] for b in buildings}
    check('all_17_unique_models_used',len(models)==17 and placed==set(models),sorted(placed))
    foundations=[]
    for b in buildings:
        if b['model']=='CanalTown':continue
        q=b['aabb_xz_m'];xx,zz=np.meshgrid(np.linspace(q[0],q[2],7),np.linspace(q[1],q[3],7));yy=sample(h,xx,zz)
        foundations.append(float(np.max(np.abs(yy-b['ground_y_m']))))
    check('building_foundations_flat',max(foundations)<.03,{'max_deviation_m':max(foundations),'instances':len(buildings)})
    occupied=[]
    for i,a in enumerate(buildings):
        for b in buildings[i+1:]:
            q=a['aabb_xz_m'];r=b['aabb_xz_m']
            if q[0]<r[2] and q[2]>r[0] and q[1]<r[3] and q[3]>r[1]:occupied.append([a['name'],b['name']])
    check('no_building_aabb_overlap',not occupied,occupied)
    spawn_stats=[]
    for sp in spawns:
        x,y,z=sp['position_m'];ex,ez=sp['exit_world_xz_m'];xx,zz=np.meshgrid(np.linspace(x-3,x+3,7),np.linspace(min(z-6,ez),max(z+6,ez),13));yy=sample(h,xx,zz)
        distance=float(np.max(np.abs(yy-y)));grounderr=abs(float(sample(h,x,z))-y)
        yaw=math.degrees(math.atan2(ex-x,ez-z));yawerr=abs(((yaw-sp['yaw_degrees']+180)%360)-180)
        spawn_stats.append({'name':sp['name'],'ground_error_m':grounderr,'pad_max_deviation_m':distance,'exit_yaw_error_degrees':yawerr,'position_m':sp['position_m']})
    check('empty_vehicle_bays_flat_and_grounded',len(spawns)>=26 and max(s['pad_max_deviation_m'] for s in spawn_stats)<.03 and max(s['ground_error_m'] for s in spawn_stats)<.001,spawn_stats)
    check('vehicle_yaw_faces_exit',all(s['exit_yaw_error_degrees']<.001 for s in spawn_stats),'Unity +Z points towards the connecting street')
    categories={s['name'] for s in sites if any(v['district']==s['name'] for v in spawns)}
    check('every_district_has_vehicle_bays',len(categories)==len(sites),sorted(categories))
    # Inspect retained native instances, including terrain rocks/shrubs, in each full bay/corridor.
    blocked=[]
    for tag,data in t.data.items():
        i,j=map(int,tag.split('_'))
        for inst in data['m_DetailDatabase']['m_TreeInstances']:
            p=inst['position'];x=(i-2)*1000+p['x']*1000;z=(j-2)*1000+p['z']*1000
            for sp in spawns:
                sx,sy,sz=sp['position_m'];ez=sp['exit_world_xz_m'][1]
                if abs(x-sx)<8 and min(sz-9,ez-3)<z<max(sz+9,ez+3):blocked.append(sp['name'])
    check('no_terrain_instances_in_vehicle_bays',not blocked,blocked)
    external=[r for r in roads if 'sites' in r];connected={0}
    for _ in sites:
        for r in external:
            a,b=r['sites']
            if a in connected or b in connected:connected.update([a,b])
    check('connected_district_road_graph',len(connected)==len(sites),{'connected_districts':len(connected),'road_links':len(external)})
    grades=[]
    for r in external:
        p=np.array(r['points']);dist=np.linalg.norm(np.diff(p[:,[0,2]],axis=0),axis=1);grade=np.abs(np.diff(p[:,1]))/np.maximum(dist,.01)
        grades.append({'road':r['name'],'max_grade_percent':float(grade.max()*100),'length_m':float(dist.sum())})
    check('roads_have_bounded_grades',max(v['max_grade_percent'] for v in grades)<12,grades)
    road_obstacles=[]
    for r in roads:
        p=np.asarray(r['points'])
        # Densify long straight internal streets before measuring building clearance.
        coords=[]
        for a,b in zip(p[:-1],p[1:]):
            n=max(2,int(np.linalg.norm(b[[0,2]]-a[[0,2]])))
            coords.extend(np.linspace(a,b,n))
        a=np.asarray(coords);margin=r['width']/2+.25
        for b in buildings:
            q=b['aabb_xz_m'];dx=np.maximum(np.maximum(q[0]-a[:,0],a[:,0]-q[2]),0);dz=np.maximum(np.maximum(q[1]-a[:,2],a[:,2]-q[3]),0)
            if np.min(np.hypot(dx,dz))<margin:road_obstacles.append([r['name'],b['name']])
    check('no_roads_through_buildings',not road_obstacles,road_obstacles)
    canals=[]
    for b in buildings:
        if 'canal_basin' not in b:continue
        x,z=b['canal_basin']['center_xz_m'];bed=float(sample(h,x,z));ground=b['ground_y_m']
        canals.append({'district':b['district'],'ground_m':ground,'bed_m':bed,'model_root_y_m':b['position_m'][1]})
    check('canal_bed_excavated_under_authored_water',all(abs(c['ground_m']-c['bed_m']-1.25)<.03 for c in canals),canals)
    # Actual data-file hashes are supplied for rechecking a checkout independently.
    files={str(p.relative_to(Path.cwd())):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in t.sources.values()}
    return {'schema_version':1,'status':'offline_checks_passed','unity_editor_import_tested':False,'unity_render_tested':False,'unity_build_tested':False,
        'scene':'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity','map_size_m':[2000,2000],'area_m2':4000000,
        'district_count':len(sites),'building_instance_count':len(buildings),'unique_model_count':len(models),'vehicle_spawn_count':len(spawns),
        'checks':checks,'terrain_files':files,'limitations':['A Unity 6000.3.26f1 import, shader compilation, visual inspection and target-device playtest remain required.',
            'Some source packs contain exterior shells or authored closed doors. No promise that every building is enterable.',
            'The ocean is visual only; swim, damage, map boundary and vehicle gameplay systems are not included.',
            'Roads are graded using an 8% planning target; final measured slopes and maximum appear above after intersections and flat district transitions.',
            'Ground-review LOD meshes and target-device performance require verification after native authoring.']}

def structural():
    """Check generated Mesh buffers, local scene references and native asset GUIDs."""
    root=Path.cwd();assets=root/'Assets/AarisWorld';count=0;triangles=0
    for p in assets.rglob('*.asset'):
        text=p.read_text();assert 'Mesh:' in text,p
        # Only one object per authored mesh. Parse without Unity tag directives.
        body=text.split('\n',3)[3]
        body=re.sub(r'(?m)^(\s*(?:_typelessdata|m_IndexBuffer):) ([0-9a-f]+)$',r'\1 "\2"',body)
        d=yaml.load(body,Loader=yaml.CSafeLoader)['Mesh']
        vd=d['m_VertexData'];raw=bytes.fromhex(str(vd['_typelessdata']));assert len(raw)==vd['m_DataSize']==vd['m_VertexCount']*48,p
        v=np.frombuffer(raw,'<f4').reshape(-1,12);assert np.isfinite(v).all(),p
        ind=np.frombuffer(bytes.fromhex(str(d['m_IndexBuffer'])),'<u4');assert len(ind)%3==0 and int(ind.max())<len(v),p
        assert sum(s['indexCount'] for s in d['m_SubMeshes'])==len(ind),p
        count+=1;triangles+=len(ind)//3
    scene=(root/'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity').read_text()
    ids=re.findall(r'(?m)^--- !u!\d+ &(-?\d+)',scene);assert len(ids)==len(set(ids))
    roots=set(map(int,ids))|{0};localrefs=[int(m) for m in re.findall(r'\{fileID: (-?\d+)\}',scene)];assert set(localrefs)<=roots,set(localrefs)-roots
    assert len(re.findall(r'(?m)^  m_Name: Terrain_[12]_[12]$',scene))==4
    spawn_names=re.findall(r'm_Name: (VehicleSpawnPoint_\d+)\n',scene);layout=json.loads((root/'Docs/MAP_LAYOUT.json').read_text());assert len(spawn_names)==len(layout['vehicle_spawns'])
    guids={}
    for p in (root/'Assets').rglob('*.meta'):
        m=re.search(r'(?m)^guid: (\w+)',p.read_text());
        if m:guids[m[1]]=p
    package_guids={'933532a4fcc9baf4fa0491de14d08ed7'}
    missing=[]
    for p in [*(assets.rglob('*.mat')),*(assets.rglob('*.prefab')),root/'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity']:
        for g in re.findall(r'guid: ([0-9a-f]{32})',p.read_text()):
            if g not in guids and g not in package_guids and not re.fullmatch('0{16}[ef]0{15}',g):missing.append((str(p),g))
    # Full source checkout should resolve original skybox/Terrain material refs.
    if (root/'TRANSFER-MANIFEST.json').exists():assert not missing,missing
    report={'mesh_assets_checked':count,'unique_mesh_triangles':triangles,'scene_objects_and_components_checked':len(ids),'unresolved_asset_guids':missing}
    (root/'Docs/MAP_STRUCTURE_REPORT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':structural()
