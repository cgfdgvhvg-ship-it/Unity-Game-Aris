"""Build saved native Unity assets. Run from repository root; no Unity Editor required.

The source GLBs and original TerrainData are hash-pinned. This script is a
build-time tool only; the scene opens directly without executing generation code.
"""
import base64,copy,hashlib,json,math,re,sys,time,urllib.request
from pathlib import Path
import numpy as np
import yaml
from native_assets import Glb,guid,meta,mesh_asset,material_asset,ref,vec
from native_scene import Scene
from sculpt import Terrain,SEA,BASE,STEP,sample
from layout import create_sites,road_network
import surfaces
ROOT=Path.cwd();TOOLS=ROOT/'Tools/MapBuild';OUT=ROOT/'Assets/AarisWorld';DOCS=ROOT/'Docs'
DATA=ROOT/'Assets/TerrainDemoScene_URP/Terrain/Data'
SCENE=ROOT/'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity'

def log(*args):print(*args,flush=True)
def jsonsave(path,data):Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(json.dumps(data,indent=2)+'\n')
def unity_docs(text):
    for chunk in re.split(r'(?m)^--- !u!',text)[1:]:
        header,body=chunk.split('\n',1);cls=int(header.split()[0]);ident=int(header.split('&')[1].split()[0]);d=yaml.safe_load(body);name=next(iter(d));yield cls,ident,name,d[name]

def source_cache():
    source=json.loads((TOOLS/'model_sources.json').read_text());cache=TOOLS/'.source-cache';cache.mkdir(exist_ok=True)
    for entry in source:
        p=cache/(entry['id']+'.glb')
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
            log('Downloading',entry['id']);err=None
            for attempt in range(3):
                try:
                    request=urllib.request.Request(entry['url'],headers={'User-Agent':'AarisMapBuild/1.0'})
                    with urllib.request.urlopen(request,timeout=180) as response:p.write_bytes(response.read())
                    err=None;break
                except Exception as ex:err=ex;time.sleep(attempt+1)
            if err:raise err
        assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'],entry['id']+' source checksum mismatch'
    return source,cache

def model_export(template):
    from native_assets import export_model
    sources,cache=source_cache();models={};shared={}
    order=sorted(sources,key=lambda e:e['id']!='TownHall')
    for entry in order:
        mid=entry['id'];log('Author native mesh/materials',mid)
        p=OUT/'Models'/mid
        cache_dir=TOOLS/'.model-cache';cache_dir.mkdir(exist_ok=True)
        record=cache_dir/(mid+'.json')
        key=hashlib.sha256((entry['sha256']+(TOOLS/'native_assets.py').read_text()+(TOOLS/'native_scene.py').read_text()+template+json.dumps(shared,sort_keys=True)).encode()).hexdigest()
        prior=json.loads(record.read_text()) if record.exists() else {}
        if prior.get('key')==key and (p/'Geometry.asset').exists():report=prior['report']
        else:
            report=export_model(cache/(mid+'.glb'),p,template,shared=shared,reuse_images=prior.get('report',{}).get('source_sha256')==entry['sha256'])
            jsonsave(record,{'key':key,'report':report})
        models[mid]=report
        if mid=='TownHall':
            for key,index in [('wood',6),('stone',0)]:
                mat=yaml.safe_load(re.split(r'(?m)^--- .*\n',(p/f'Material_{index:02d}.mat').read_text())[1])['Material']
                ts={k:v['m_Texture']['guid'] for e in mat['m_SavedProperties']['m_TexEnvs'] for k,v in e.items()}
                shared[key]={'color':ts['_BaseMap'],'normal':ts.get('_BumpMap')}
    return sources,models

def place_buildings(t,sites,models):
    buildings=[];spawns=[];internals=[]
    small=['a_frame_cabin','bungalow_house','pitched_roof_cottage','detached_two_storey_house','garage_apartment','two_bedroom_garage_house','row_three_townhouses']
    def place(site,model,dx,dz,yaw=0):
        dims=models[model]['dimensions_m'];angle=math.radians(yaw);c=abs(math.cos(angle));s=abs(math.sin(angle))
        hx=(dims[0]*c+dims[2]*s)/2;hz=(dims[0]*s+dims[2]*c)/2;x=site['x']+dx;z=site['z']+dz
        assert abs(dx)+hx+1<site['width']/2 and abs(dz)+hz+1<site['depth']/2,(site['name'],model,dims,dx,dz)
        box=[x-hx,z-hz,x+hx,z+hz]
        for b in buildings:
            q=b['aabb_xz_m'];assert not(box[0]<q[2]+3 and box[2]>q[0]-3 and box[1]<q[3]+3 and box[3]>q[1]-3),(site['name'],model,'overlap',b['name'])
        name=f'{site["name"]}_{model}_{sum(b["district"]==site["name"] for b in buildings)+1:02d}'
        rec={'name':name,'district':site['name'],'model':model,'position_m':[x,site['height'],z],'ground_y_m':site['height'],'yaw_degrees':yaw,'aabb_xz_m':box}
        buildings.append(rec);return rec
    for si,s in enumerate(sites):
        w,d=s['width'],s['depth'];short=w<100
        focal=s['focal_model']
        if s['name']=='SouthernAirfield':
            # Buildings on north side; full 220m runway is left unobstructed in the south.
            place(s,focal,0,35,yaw=90)
            place(s,'warehouse_loading_dock',-105,42)
            place(s,'garage_apartment',104,42)
            s['runway']=[s['x'],s['z']-35,240,24]
        elif short:
            place(s,focal,0,8)
        else:
            place(s,focal,0,25)
            if s['name']=='FreightDistrict':
                place(s,'warehouse_loading_dock',-53,25)
                place(s,'warehouse_loading_dock',53,25)
                place(s,'garage_apartment',-55,-48)
                place(s,'two_bedroom_garage_house',52,-48)
            else:
                for k,(dx,dz) in enumerate([(-w*.32,25),(w*.32,25),(-w*.32,-d*.31),(w*.32,-d*.31)]):
                    mid=small[(si*2+k)%len(small)]
                    place(s,mid,dx,dz,0 if dz>0 else 180)
                if w>=165:
                    place(s,'garage_apartment',0,-d*.31,180)
        # Internal distributor at z=-20. Gate leads to this street, away from buildings.
        streetz=s['z']-20
        internals.append({'name':s['name']+'_Entry','points':[list(s['gate']),[s['gate'][0] if s['gate_side']=='south' else s['x'],s['height'],streetz]],'width':8})
        internals.append({'name':s['name']+'_Street','points':[[s['x']-w/2+8,s['height'],streetz],[s['x']+w/2-8,s['height'],streetz]],'width':7})
        # At least two empty bays per district, fully outside all model bounds.
        candidates=[]
        if short:candidates=[(s['x']-w/2+9,streetz+8,streetz),(s['x']+w/2-9,streetz+8,streetz)]
        elif s['name']=='SouthernAirfield':candidates=[(s['x']-108,s['z']+17,streetz),(s['x']+105,s['z']+17,streetz)]
        else:candidates=[(s['x']-w*.32,streetz+9,streetz),(s['x']+w*.32,streetz+9,streetz)]
        for x,z,exit_z in candidates:
            spawns.append({'district':s['name'],'position_m':[x,s['height'],z],'exit_world_xz_m':[x,exit_z],'reserved_size_m':[6,12]})
        # Specific garage apron bays: find a free lane on the street-facing side.
        for b in [b for b in buildings if b['district']==s['name'] and b['model'] in ('garage_apartment','two_bedroom_garage_house','warehouse_loading_dock')]:
            q=b['aabb_xz_m'];north=b['position_m'][2]>streetz
            z=q[1]-8 if north else q[3]+8;x=(q[0]+q[2])/2
            if abs(z-streetz)<5:continue
            if any(abs(x-v['position_m'][0])<7 and abs(z-v['position_m'][2])<13 for v in spawns if v['district']==s['name']):continue
            spawns.append({'district':s['name'],'position_m':[x,s['height'],z],'exit_world_xz_m':[x,streetz],'reserved_size_m':[6,12],'serves':b['name']})
    # Candidate bays must remain clear of all complete source-kit geometry bounds.
    good=[]
    for sp in spawns:
        x,y,z=sp['position_m'];ex,ez=sp['exit_world_xz_m'];lo=[x-3,min(z-6,ez)-1];hi=[x+3,max(z+6,ez)+1]
        if any(lo[0]<b['aabb_xz_m'][2]+.5 and hi[0]>b['aabb_xz_m'][0]-.5 and lo[1]<b['aabb_xz_m'][3]+.5 and hi[1]>b['aabb_xz_m'][1]-.5 for b in buildings):continue
        if any(abs(x-v['position_m'][0])<7 and abs(z-v['position_m'][2])<13 for v in good):continue
        sp['yaw_degrees']=math.degrees(math.atan2(ex-x,ez-z));sp['name']=f'VehicleSpawnPoint_{len(good)+1:02d}';good.append(sp)
    assert len(good)>=26,('Too few unobstructed vehicle bays',len(good))
    return buildings,good,internals

def sculpt_layout(t,sites,roads,buildings,spawns,models):
    # Reassert flat foundations after external road grading. Roads use the service strip.
    for s in sites:t.pad(s['x'],s['z'],s['width']/2,s['depth']/2,s['height'],70)
    for road in roads:
        if 'sites' not in road:t.road(road['points'],road['width'],5)
    for sp in spawns:
        x,y,z=sp['position_m'];ez=sp['exit_world_xz_m'][1]
        t.pad(x,(z+ez)/2,5,abs(z-ez)/2+7,y,8)
    # Resolve crossing-road elevation conflicts on the final, fixed district layout.
    for iteration in range(8):
        for road in roads:
            if 'sites' not in road:continue
            p=np.asarray(road['points']);length=np.linalg.norm(np.diff(p[:,[0,2]],axis=0),axis=1)
            yy=sample(t.h,p[:,0],p[:,2]);a,b=road['sites'];yy[0]=sites[a]['height'];yy[-1]=sites[b]['height']
            for _ in range(12):
                for k in range(1,len(yy)-1):yy[k]=min(max(yy[k],yy[k-1]-.10*length[k-1]),yy[k-1]+.10*length[k-1])
                for k in range(len(yy)-2,0,-1):yy[k]=min(max(yy[k],yy[k+1]-.10*length[k]),yy[k+1]+.10*length[k])
            p[:,1]=yy;t.road(p,road['width'],5)
        for road in roads:
            if 'sites' not in road:t.road(road['points'],road['width'],5)
    for b in buildings:
        if b['model']=='CanalTown':
            pivot=models['CanalTown']['source_pivot'];x=b['position_m'][0]-pivot[0];z=b['position_m'][2]-pivot[2]
            b['canal_basin']={'center_xz_m':[x,z],'size_xz_m':[28,8],'depth_m':1.25}
            t.pad(x,z,14,4,b['ground_y_m']-1.25,.15)
    t.quantize()
    for s in sites:s['height']=float(sample(t.h,s['x'],s['z']));s['gate'][1]=s['height']
    for b in buildings:
        b['ground_y_m']=next(s['height'] for s in sites if s['name']==b['district'])
        # Starter kits have a deliberately buried slab/canal bed below their authored y=0 street.
        offset=models[b['model']]['source_pivot'][1]+.03 if b['model'] in ('Airfield','HanokVillage','CanalTown','ParcelDepot') else 0
        b['position_m'][1]=b['ground_y_m']+offset
    for sp in spawns:sp['position_m'][1]=float(sample(t.h,sp['position_m'][0],sp['position_m'][2]))
    for road in roads:
        p=np.array(road['points']);p[:,1]=sample(t.h,p[:,0],p[:,2]);road['points']=p.tolist()

def scene_build(t,sites,roads,buildings,spawns,models,template,terrain_template,render_settings):
    world=Scene();world.environment(render_settings)
    _,root,_=world.object('Aaris_Island_2km');_,districtroot,_=world.object('Districts',parent=root)
    parents={}
    for s in sites:_,parents[s['name']],_=world.object(s['name'],parent=districtroot)
    for b in buildings:
        m=models[b['model']];world.model(b['name'],m['guid'],m['materials'],position=b['position_m'],yaw=b['yaw_degrees'],parent=parents[b['district']],bounds=m['bounds'])
    _,terrainroot,_=world.object('Terrain_2x2',parent=root)
    prefab=Scene();_,pr,_=prefab.object('TerrainHigh')
    for tag,path in t.sources.items():
        i,j=map(int,tag.split('_'));g=yaml.safe_load(Path(str(path)+'.meta').read_text())['guid'];pos=((i-2)*1000,BASE,(j-2)*1000)
        world.terrain('Terrain_'+tag,g,pos,terrain_template,parent=terrainroot)
        # Same prefab retains original absolute 1000m grid, with root accounting for scene origin.
        prefab.terrain('Terrain_'+tag,g,(i*1000,0,j*1000),terrain_template,parent=pr)
    prefab.transforms[pr]['m_LocalPosition']=vec(-2000,BASE,-2000)
    prefab_path=next((p for p in (ROOT/'Assets').rglob('TerrainHigh.prefab') if 'AarisWorld' not in str(p)),None)
    assert prefab_path is not None
    original_meta=Path(str(prefab_path)+'.meta');prior=original_meta.read_text() if original_meta.exists() else None
    prefab.save(prefab_path,prefab=True)
    if prior:original_meta.write_text(prior)
    geom=OUT/'Surfaces';geom.mkdir(parents=True,exist_ok=True);mats=surfaces.materials(geom)
    _,roadsroot,_=world.object('RoadNetwork',parent=root)
    for k,road in enumerate(roads):
        p=geom/f'Road_{k:02d}.asset';m=surfaces.ribbon(p,road['points'],road['width'],t.h,template)
        world.model(road['name'],m['guid'],[mats['Asphalt']],parent=roadsroot,lod=False,collider=False)
        # Split paint at actual paved triangles; terrain heights alone cause buried paint.
        from road_markings import read_mesh,project_markings,paint_quads
        if list(paint_quads(road['points'])):
            paved,paved_tri,_=read_mesh(p)
            paint,paint_tri,_=project_markings(paved,paved_tri,road['points'])
            m=surfaces.surface(geom/f'RoadMark_{k:02d}.asset',paint[:,[0,2]],paint_tri,paint[:,1],template)
            world.model(road['name']+'_Markings',m['guid'],[mats['RoadMark']],parent=roadsroot,lod=False,collider=False)
    _,groundroot,_=world.object('FoundationsAndAprons',parent=root)
    for k,b in enumerate(buildings):
        if b['model']=='CanalTown':continue
        q=b['aabb_xz_m'];m=surfaces.rect(geom/f'Foundation_{k:03d}.asset',(q[0]+q[2])/2,(q[1]+q[3])/2,q[2]-q[0]+2,q[3]-q[1]+2,b['ground_y_m']+.014,template)
        world.model(b['name']+'_Foundation',m['guid'],[mats['Concrete']],parent=groundroot,collider=False,lod=False)
    for k,sp in enumerate(spawns):
        x,y,z=sp['position_m'];ez=sp['exit_world_xz_m'][1];m=surfaces.rect(geom/f'Apron_{k:03d}.asset',x,(z+ez)/2,7,abs(z-ez)+13,y+.012,template)
        world.model(sp['name']+'_Apron',m['guid'],[mats['Concrete']],parent=groundroot,collider=False,lod=False)
    for s in sites:
        if 'runway' in s:
            x,z,w,d=s['runway'];m=surfaces.rect(geom/'Runway.asset',x,z,w,d,s['height']+.028,template)
            world.model('Airfield_240m_Runway',m['guid'],[mats['Asphalt']],parent=parents[s['name']],collider=False,lod=False)
            for k in range(-5,6):
                m=surfaces.rect(geom/f'RunwayDash_{k+5:02d}.asset',x+k*18,z,8,.5,s['height']+.032,template)
                world.model('RunwayCentre_'+str(k+5),m['guid'],[mats['RoadMark']],parent=parents[s['name']],collider=False,lod=False)
    m=surfaces.beach(geom/'CoastalSand.asset',t,template)
    if m:world.model('CoastalSand',m['guid'],[mats['Sand']],parent=root,collider=False,lod=False)
    m,mat=surfaces.ocean(geom,template);world.model('Ocean_VisualOnly',m['guid'],[mat],parent=root,collider=False,lod=False)
    for b in buildings:
        if 'canal_basin' in b:
            x,z=b['canal_basin']['center_xz_m'];m=surfaces.rect(geom/'CanalWater.asset',x,z,27.8,7.8,b['ground_y_m']-.25,template)
            world.model('CanalWater_VisualOnly',m['guid'],[mat],parent=parents[b['district']],collider=False,lod=False)
    port=next(s for s in sites if s['name']=='EasternPort');y=port['height'];z=port['z']+25
    # Dock meets the source quay's 1.2m deck via a shallow native ramp, then reaches the sea.
    dock=surfaces.port_dock(geom/'PortDock.asset',port['x']+models['Harbour']['dimensions_m'][0]/2+10,966,z,y,template)
    world.model('Port_Sea_Pier',dock['guid'],[mats['Concrete']],parent=parents['EasternPort'],collider=True,lod=False)
    _,spawnroot,_=world.object('VehicleSpawns',parent=root,static=False)
    for sp in spawns:world.object(sp['name'],position=sp['position_m'],yaw=sp['yaw_degrees'],parent=spawnroot,static=False)
    oldmeta=Path(str(SCENE)+'.meta');prior=oldmeta.read_text() if oldmeta.exists() else None
    world.save(SCENE)
    if prior:oldmeta.write_text(prior)
    # All surface overlays are visual; Terrain provides ground collision exactly at marker y.
    return world

def remove_extra_tiles(t):
    keep=set(t.sources.values());removed=[]
    for p in DATA.glob('*.asset'):
        if p not in keep:removed.append(str(p.relative_to(ROOT)));p.unlink();Path(str(p)+'.meta').unlink(missing_ok=True)
    for p in (ROOT/'Assets').rglob('TerrainProxy.prefab'):
        removed.append(str(p.relative_to(ROOT)));p.unlink();Path(str(p)+'.meta').unlink(missing_ok=True)
    return removed

def project_settings():
    packages={'com.unity.render-pipelines.universal':'17.3.0','com.unity.visualeffectgraph':'17.3.0',
              'com.unity.modules.imgui':'1.0.0','com.unity.modules.audio':'1.0.0','com.unity.modules.physics':'1.0.0','com.unity.modules.terrain':'1.0.0',
              'com.unity.modules.terrainphysics':'1.0.0','com.unity.modules.particlesystem':'1.0.0','com.unity.modules.ui':'1.0.0','com.unity.modules.jsonserialize':'1.0.0'}
    jsonsave(ROOT/'Packages/manifest.json',{'dependencies':packages})
    folder=ROOT/'ProjectSettings';folder.mkdir(exist_ok=True);(folder/'ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.26f1\n')
    from native_assets import write_yaml
    write_yaml(folder/'ProjectSettings.asset',[(129,1,'PlayerSettings',{'m_ObjectHideFlags':0,'serializedVersion':27,'companyName':'Aaris','productName':'Aaris Map Explorer','m_ActiveColorSpace':1,'activeInputHandler':0,
        'scriptingDefineSymbols':{'Android':'URP_COMPATIBILITY_MODE','Standalone':'URP_COMPATIBILITY_MODE','WebGL':'URP_COMPATIBILITY_MODE'},'bundleVersion':'0.1.0',
        'defaultInterfaceOrientation':4,'allowedAutorotateToPortrait':0,'allowedAutorotateToPortraitUpsideDown':0,
        'allowedAutorotateToLandscapeLeft':1,'allowedAutorotateToLandscapeRight':1,
        'applicationIdentifier':{'Android':'com.aaris.mapexplorer'},'AndroidTargetArchitectures':2,
        'AndroidMinSdkVersion':26,'AndroidTargetSdkVersion':0,'AndroidUseCustomKeystore':0,'scriptingBackend':{'Android':1}})])
    write_yaml(folder/'GraphicsSettings.asset',[(30,1,'GraphicsSettings',{'m_ObjectHideFlags':0,'serializedVersion':16,
        'm_CustomRenderPipeline':ref(11400000,'4f455263fdaa19b4894b6dbdb822f8d6'),'m_SRPDefaultSettings':{},
        'm_LightsUseLinearIntensity':1,'m_LightsUseColorTemperature':1,'m_DefaultRenderingLayerMask':1,
        'm_LogWhenShaderIsCompiled':0,'m_SpritesDefaultMaterial':ref(),'m_AlwaysIncludedShaders':[],
        'm_PreloadedShaders':[],'m_LightmapStripping':0,'m_FogStripping':0,'m_InstancingStripping':0})])
    scene_guid=yaml.safe_load(Path(str(SCENE)+'.meta').read_text())['guid']
    write_yaml(folder/'EditorBuildSettings.asset',[(1045,1,'EditorBuildSettings',{'m_ObjectHideFlags':0,'serializedVersion':2,
        'm_Scenes':[{'enabled':1,'path':str(SCENE.relative_to(ROOT)),'guid':scene_guid}],'m_configObjects':{},'m_UseUCBPForAssetBundles':0})])
    # Keep original names/layers for terrain detail prefabs; provision missing slots.
    write_yaml(folder/'TagManager.asset',[(78,1,'TagManager',{'serializedVersion':2,'tags':[],'layers':['Default','TransparentFX','Ignore Raycast','','Water','UI','Terrain']+['']*25,
        'm_SortingLayers':[{'name':'Default','uniqueID':0,'locked':0}],'m_RenderingLayers':['Default']})])

def folder_metas():
    for p in (ROOT/'Assets').rglob('*'):
        if p.is_dir() and not Path(str(p)+'.meta').exists():meta(p,kind='folder')

def run():
    DOCS.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    template=(TOOLS/'mesh_template.asset').read_text() if (TOOLS/'mesh_template.asset').exists() else base64.b64decode((TOOLS/'mesh_template.b64').read_text()).decode()
    original_scene=(TOOLS/'original_scene.yaml').read_text() if (TOOLS/'original_scene.yaml').exists() else SCENE.read_text()
    original_terrain=(TOOLS/'original_terrain.yaml').read_text() if (TOOLS/'original_terrain.yaml').exists() else next((ROOT/'Assets').rglob('TerrainHigh.prefab')).read_text()
    terrain_template=next(d for c,i,n,d in unity_docs(original_terrain) if c==218)
    terrain_template.update(m_HeightmapPixelError=5,m_RenderingLayerMask=1,m_LightmapParameters=ref())
    render_settings=next(d for c,i,n,d in unity_docs(original_scene) if c==104)
    log('Load four original TerrainData assets');t=Terrain(DATA)
    sources,models=model_export(template)
    t.coast_sculpt();sites=create_sites(t);log('Route district roads');roads=road_network(t,sites)
    buildings,spawns,internals=place_buildings(t,sites,models);roads+=internals
    sculpt_layout(t,sites,roads,buildings,spawns,models)
    log('Save edited native TerrainData');tile_reports=t.save()
    from export_index import export
    export(t,DOCS,TOOLS)
    log('Save native scene, static colliders, roads and empty vehicle markers')
    scene_build(t,sites,roads,buildings,spawns,models,template,terrain_template,render_settings)
    removed=remove_extra_tiles(t);project_settings();folder_metas()
    model_report={k:{kk:vv for kk,vv in m.items() if kk not in ['materials','prefab']} for k,m in models.items()}
    jsonsave(DOCS/'MAP_LAYOUT.json',{'world_units':'metres','size_m':[2000,2000],'area_m2':4000000,'terrain_bounds_xz_m':[-1000,-1000,1000,1000],
        'sea_level_m':SEA,'terrain_base_y_m':BASE,'districts':sites,'buildings':buildings,'roads':roads,'vehicle_spawns':spawns,'models':model_report,
        'provenance':sources,'removed_assets':removed,'tile_reports':tile_reports,
        'vehicle_phase':'Empty markers only. Vehicle prefabs/physics intentionally deferred.'})
    np.savez_compressed(TOOLS/'.build_geometry.npz',height=t.h,cleared=t.cleared,original=t.original)
    from validate_map import validate
    report=validate(t,sites,roads,buildings,spawns,models)
    jsonsave(DOCS/'MAP_BUILD_REPORT.json',report)
    attributes=ROOT/'.gitattributes';text=attributes.read_text() if attributes.exists() else ''
    # Remove stale LFS paths for the deleted tiles/proxy prefab, preserve all other source rules.
    text='\n'.join(line for line in text.splitlines() if not any(p.replace(' ','[[:space:]]') in line or p in line for p in removed))+'\n'
    text+='\n# Generated native map meshes and extracted textures\nAssets/AarisWorld/**/*.asset filter=lfs diff=lfs merge=lfs -text\nAssets/AarisWorld/**/*.png filter=lfs diff=lfs merge=lfs -text\n'
    attributes.write_text(text)
    # Author saved native assets only; no runtime map/lighting bootstrapper is added.
    from ground_review import upgrade
    from ground_native import materialize
    upgrade(ROOT)
    materialize(ROOT)
    log('ASSEMBLY COMPLETE',len(sites),'districts',len(buildings),'model instances',len(spawns),'empty vehicle markers')
if __name__=='__main__':run()
