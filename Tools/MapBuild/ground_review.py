"""Author permanent ground-review scene assets. Nothing here runs in the APK."""
from __future__ import annotations
import copy, hashlib, json, math, re
from collections import Counter
from pathlib import Path
import numpy as np
import yaml
from native_assets import Flow, color, guid, material_asset, meta, ref, vec, write_yaml
from native_scene import Scene

SCENE = 'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity'
PLAYER = 'Assets/AarisWorld/Player'
SCRIPT = 'Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs'
SEA = -38.07552
SPAWN_XZ = (-650.0, -190.0)

def documents(path):
    def flow(value):
        if isinstance(value,list):return [flow(v) for v in value]
        if not isinstance(value,dict):return value
        value={k:flow(v) for k,v in value.items()};keys=set(value)
        if ('fileID'in keys and keys<={'fileID','guid','type'}) or keys in ({'x','y'},{'x','y','z'},{'x','y','z','w'},{'r','g','b','a'}):return Flow(value)
        return value
    result=[]
    for chunk in re.split(r'(?m)^--- !u!',Path(path).read_text())[1:]:
        header,body=chunk.split('\n',1);obj=yaml.safe_load(body);name=next(iter(obj))
        result.append((int(header.split()[0]),int(header.split('&')[1].split()[0]),name,flow(obj[name])))
    return result

def heights(root):
    h=np.zeros((257,257),dtype=float)
    for p in (root/'Docs/TerrainHeightSamples').glob('*.csv'):
        i,j=map(int,p.stem.removeprefix('Terrain_').split('_'))
        h[(j-1)*128:(j-1)*128+129,(i-1)*128:(i-1)*128+129]=np.loadtxt(p,delimiter=',',skiprows=1)[:,1:]
    return h

def sample(h,x,z):
    x=np.clip((np.asarray(x)+1000)*128/1000,0,256)
    z=np.clip((np.asarray(z)+1000)*128/1000,0,256)
    ix=np.minimum(x.astype(int),255);iz=np.minimum(z.astype(int),255)
    fx=x-ix;fz=z-iz
    return (h[iz,ix]*(1-fx)+h[iz,ix+1]*fx)*(1-fz)+(h[iz+1,ix]*(1-fx)+h[iz+1,ix+1]*fx)*fz

def segment_distance(points,segments):
    a,b=segments[:,0],segments[:,1];v=b-a
    t=np.clip(np.sum((points[:,None,:]-a)*v,axis=2)/np.maximum(np.sum(v*v,axis=1),1e-8),0,1)
    return np.linalg.norm(points[:,None,:]-(a+t[:,:,None]*v),axis=2).min(axis=1)

def forest_plan(root,layout,h):
    """Fill sparse quadrants with shared source trees, reserving all authored pads."""
    rng=np.random.default_rng(20261103)
    ix=json.loads((root/'Docs/TERRAIN_INDEX.json').read_text())
    prototype_paths=list(dict.fromkeys(p['path'] for t in ix['tiles'] for p in t['tree_and_rock_prototypes'] if p['category']=='tree'))
    weights={'Cypress_Forest_Desktop':.35,'Pine_B':.38,'Conifer':.17,'Pine_D':.05,'Pine_A':.03,'Pine_C':.02}
    probabilities=np.array([weights[Path(p).stem] for p in prototype_paths]);probabilities/=probabilities.sum()
    existing=[]
    for f in (root/'Docs/TerrainInstances').glob('*.jsonl'):
        existing.extend(json.loads(s) for s in f.read_text().splitlines() if s)
    old_tree=np.array([r['position_m'][::2] for r in existing if r['category']=='tree'])
    rocks=np.array([r['position_m'][::2] for r in existing if r['category']=='rock'])
    segments=np.array([[p[::2],q[::2]] for r in layout['roads'] for p,q in zip(r['points'],r['points'][1:])])
    gz,gx=np.gradient(h,1000/128)
    goals={'1_1':80,'1_2':80,'2_1':520,'2_2':420};out=[]
    for tag,goal in goals.items():
        i,j=map(int,tag.split('_'));ox=(i-2)*1000;oz=(j-2)*1000
        axis=np.arange(25,985,18.0)
        xx,zz=np.meshgrid(axis+ox,axis+oz)
        points=np.column_stack((xx.ravel(),zz.ravel()))+rng.uniform(-5.5,5.5,(xx.size,2))
        y=sample(h,points[:,0],points[:,1])
        slope=np.hypot(sample(gx,points[:,0],points[:,1]),sample(gz,points[:,0],points[:,1]))
        ok=(y>SEA+2.5)&(slope<math.tan(math.radians(24)))&(np.abs(points).max(axis=1)<930)
        for s in layout['districts']:
            ok &= ~((np.abs(points[:,0]-s['x'])<s['width']/2+18)&(np.abs(points[:,1]-s['z'])<s['depth']/2+18))
        ok &= np.linalg.norm(points-np.array(SPAWN_XZ),axis=1)>12
        candidates=points[ok]
        road_clear=[]
        for chunk in np.array_split(candidates,max(1,len(candidates)//100)):
            if len(chunk):road_clear.extend(chunk[segment_distance(chunk,segments)>17])
        candidates=np.array(road_clear)
        rng.shuffle(candidates)
        # Coherent glades and denser groves, rather than identical rows over the whole tile.
        selected=[]
        for x,z in candidates:
            wave=math.sin(x*.010)*math.cos(z*.013)+.35*math.sin((x+z)*.025)
            if wave < -.55 and rng.random()<.82:continue
            p=np.array([x,z])
            if len(old_tree) and np.linalg.norm(old_tree-p,axis=1).min()<10:continue
            if len(rocks) and np.linalg.norm(rocks-p,axis=1).min()<4:continue
            if selected and np.linalg.norm(np.array(selected)-p,axis=1).min()<13:continue
            selected.append(p)
            path=prototype_paths[int(rng.choice(len(prototype_paths),p=probabilities))]
            scale=float(rng.uniform(1.5,1.98) if 'Cypress' in path else rng.uniform(.80,1.25))
            out.append({'id':f'ground_{tag}_{len(selected):04d}','tile':tag,'path':path,
                        'position_xz_m':[round(float(x),3),round(float(z),3)],
                        'height_scale':round(scale,4),'width_scale':round(scale*float(rng.uniform(.94,1.06)),4),
                        'yaw_degrees':round(float(rng.uniform(0,360)),3)})
            if len(selected)==goal:break
        assert len(selected)==goal,(tag,'Insufficient safe forest candidates',len(selected),goal)
    return out

def player(scene,root,camera_id,spawn):
    folder=root/PLAYER;folder.mkdir(parents=True,exist_ok=True)
    mats={}
    for name,rgb in [('Jacket',(.12,.23,.25)),('Trousers',(.15,.17,.18)),('Skin',(.47,.29,.18)),('Boots',(.035,.042,.047)),('Hair',(.055,.035,.022)),('Vest',(.25,.28,.19))]:
        p=folder/(name+'.mat');mats[name]=material_asset(p,'Aaris '+name,base=(*rgb,1),smoothness=.25,extra={'_Cull':2})
    go,tr,gd=scene.object('AarisPlayer',position=spawn,static=False)
    gd['m_TagString']='Player'
    scene.component(go,gd,143,'CharacterController',{'m_Material':ref(),'m_IncludeLayers':{'serializedVersion':2,'m_Bits':0},
        'm_ExcludeLayers':{'serializedVersion':2,'m_Bits':0},'m_LayerOverridePriority':0,'m_IsTrigger':0,'m_ProvidesContacts':0,
        'm_Enabled':1,'serializedVersion':3,'m_Height':1.78,'m_Radius':.28,'m_SlopeLimit':46,'m_StepOffset':.30,
        'm_SkinWidth':.035,'m_MinMoveDistance':0,'m_Center':vec(0,.89,0)})
    def shape(name,parent,position,scale,material,mesh=10208):
        # Unity built-in primitive meshes: capsule=10208, sphere=10207, cube=10202.
        _,joint=scene.model('AarisPlayer_'+name,'0000000000000000e000000000000000',[mats[material]],
                            position=position,parent=parent,collider=False,lod=False)
        scene.transforms[joint]['m_LocalScale']=vec(*scale)
        # Scene.model normally addresses native Mesh assets. These parts share built-in meshes.
        part_go=scene.transforms[joint]['m_GameObject']['fileID']
        next(d for c,i,n,d in scene.objects if n=='MeshFilter' and d['m_GameObject']['fileID']==part_go)['m_Mesh']=ref(mesh,'0000000000000000e000000000000000',0)
        return joint
    shape('Torso',tr,(0,1.17,0),(.46,.31,.29),'Jacket')
    shape('Vest',tr,(0,1.22,.10),(.37,.41,.13),'Vest',10202)
    shape('Hips',tr,(0,.88,0),(.37,.24,.26),'Trousers',10202)
    shape('Neck',tr,(0,1.48,0),(.12,.09,.12),'Skin',10207)
    shape('Head',tr,(0,1.62,0),(.24,.28,.23),'Skin',10207)
    shape('Hair',tr,(0,1.71,-.01),(.25,.12,.24),'Hair',10207)
    shape('Nose',tr,(0,1.61,.12),(.055,.065,.06),'Skin',10202)
    limbs={}
    for side,sign in [('Left',-1),('Right',1)]:
        _,arm,_=scene.object('AarisPlayer_'+side+'Arm',position=(sign*.29,1.42,0),parent=tr,static=False)
        shape(side+'Sleeve',arm,(0,-.15,0),(.15,.16,.15),'Jacket')
        shape(side+'Forearm',arm,(0,-.43,0),(.12,.14,.12),'Skin')
        shape(side+'Hand',arm,(0,-.61,0),(.13,.15,.11),'Skin',10207)
        _,leg,_=scene.object('AarisPlayer_'+side+'Leg',position=(sign*.12,.88,0),parent=tr,static=False)
        shape(side+'Thigh',leg,(0,-.19,0),(.16,.21,.16),'Trousers')
        shape(side+'Shin',leg,(0,-.57,0),(.13,.19,.13),'Trousers')
        shape(side+'Boot',leg,(0,-.79,.045),(.17,.16,.28),'Boots',10202)
        limbs[side+'Arm']=arm;limbs[side+'Leg']=leg
    scene.component(go,gd,114,'MonoBehaviour',{'m_Enabled':1,'m_EditorHideFlags':0,'m_Script':ref(11500000,guid(SCRIPT),3),
        'm_Name':'','m_EditorClassIdentifier':'Assembly-CSharp::Aaris.MapReview.AarisThirdPersonPlayer','followCamera':ref(camera_id),
        'leftArm':ref(limbs['LeftArm']),'rightArm':ref(limbs['RightArm']),'leftLeg':ref(limbs['LeftLeg']),'rightLeg':ref(limbs['RightLeg']),
        'walkSpeed':4.2,'runSpeed':6.2,'jumpHeight':1,'gravity':24,'followDistance':4.2,'pivotHeight':1.45,'lookSensitivity':.12,'seaLevel':SEA})
    for c,i,n,d in scene.objects:
        if n=='GameObject' and (d['m_Name']=='AarisPlayer' or d['m_Name'].startswith('AarisPlayer_')):
            d['m_Layer']=8
    tags_path=root/'ProjectSettings/TagManager.asset';tags=documents(tags_path)[0][3]
    assert tags['layers'][8] in ('',None,'Player'),'Layer 8 is already in use'
    tags['layers'][8]='Player';write_yaml(tags_path,[(78,1,'TagManager',tags)])
    return tr

def upgrade(root):
    root=Path(root);layout=json.loads((root/'Docs/MAP_LAYOUT.json').read_text());h=heights(root)
    original=documents(root/SCENE)
    scene_meta=Path(str(root/SCENE)+'.meta').read_text()
    # Ground authoring reserves IDs >= 200000. Re-running it replaces its own additions.
    objects=[o for o in original if o[1]<200000 or o[2]=='SceneRoots']
    for c,i,n,d in objects:
        if n=='Transform':d['m_Children']=[r for r in d.get('m_Children',[]) if r['fileID']<200000]
    cameras=[o for o in objects if o[2]=='Camera'];assert len(cameras)==1
    camera_id=cameras[0][1];camera_go=cameras[0][3]['m_GameObject']['fileID']
    remove={i for c,i,n,d in objects if n=='MonoBehaviour' and d.get('m_GameObject',{}).get('fileID')==camera_go}
    objects=[o for o in objects if o[1] not in remove and o[2]!='SceneRoots']
    for c,i,n,d in objects:
        if n=='GameObject':d['m_Component']=[r for r in d['m_Component'] if r['component']['fileID'] not in remove]
        if n=='RenderSettings':
            d.update(m_AmbientMode=1,m_AmbientIntensity=1,m_AmbientSkyColor=color(.45,.58,.72),
                     m_AmbientEquatorColor=color(.42,.46,.43),m_AmbientGroundColor=color(.22,.24,.20),m_ReflectionIntensity=.65)
        if n=='Light':d['m_Intensity']=1.2;d['m_Shadows']['m_Strength']=.65
        if n=='Camera':d['far clip plane']=3500;d['near clip plane']=.15;d['field of view']=60
        if n=='Terrain':d['m_SplatMapDistance']=400
    scene=Scene();scene.objects=objects;scene.next_id=200000
    scene.transforms={i:d for c,i,n,d in objects if n=='Transform'}
    # Keep detailed close meshes and add real, saved reduced meshes for middle/far views.
    id_to_go={i:d for c,i,n,d in objects if n=='GameObject'}
    root_lods=[o for o in list(objects) if o[2]=='LODGroup']
    for c,i,n,lod in root_lods:
        go=lod['m_GameObject']['fileID'];name=id_to_go[go]['m_Name']
        building=next((b for b in layout['buildings'] if b['name']==name),None)
        if building is None:continue
        root_tr=next(k for k,d in scene.transforms.items() if d['m_GameObject']['fileID']==go)
        renderer=next((k,d) for cc,k,nn,d in objects if nn=='MeshRenderer' and d['m_GameObject']['fileID']==go)
        levels=[{'screenRelativeHeight':.22,'fadeTransitionWidth':.12,'renderers':[{'renderer':ref(renderer[0])}]}]
        for level,threshold in [(1,.07),(2,.0025)]:
            mesh_path=f"Assets/AarisWorld/Models/{building['model']}/Geometry_LOD{level}.asset"
            mats=[m['guid'] for m in renderer[1]['m_Materials']]
            child_go,child_tr=scene.model('ReviewLOD_'+name+'_'+str(level),guid(mesh_path),mats,parent=root_tr,collider=False,lod=False)
            child_renderer=next(k for cc,k,nn,d in scene.objects if nn=='MeshRenderer' and d['m_GameObject']['fileID']==child_go)
            levels.append({'screenRelativeHeight':threshold,'fadeTransitionWidth':.12,'renderers':[{'renderer':ref(child_renderer)}]})
        lod['m_LODs']=levels
    start=len(scene.objects)
    spawn=(SPAWN_XZ[0],float(sample(h,*SPAWN_XZ))+.1,SPAWN_XZ[1])
    player_tr=player(scene,root,camera_id,spawn)
    player_objects=copy.deepcopy(scene.objects[start:])
    for c,i,n,d in scene.objects[start:]:
        if n=='GameObject':d['m_StaticEditorFlags']=0
    # Reusable saved player asset has no illegal reference to an object outside its prefab.
    for c,i,n,d in player_objects:
        if n=='GameObject':d['m_StaticEditorFlags']=0
        if n=='MonoBehaviour':d['followCamera']=ref()
        if n=='Transform' and i==player_tr:d['m_LocalPosition']=vec()
    write_yaml(root/PLAYER/'AarisPlayer.prefab',player_objects);meta(root/PLAYER/'AarisPlayer.prefab',kind='PrefabImporter')
    go,tr,gd=scene.object('DaylightWind',position=(0,10,0),static=False)
    scene.component(go,gd,182,'WindZone',{'m_Enabled':1,'m_Mode':0,'m_Radius':0,'m_WindMain':.22,'m_WindTurbulence':.12,'m_WindPulseMagnitude':.08,'m_WindPulseFrequency':.15})
    for i,d in scene.transforms.items():
        if d['m_GameObject']['fileID']==camera_go:
            d['m_LocalPosition']=vec(spawn[0]+.3,spawn[1]+2.32,spawn[2]-4.11)
            a=math.radians(12)/2;d['m_LocalRotation']=Flow(x=math.sin(a),y=0,z=0,w=math.cos(a))
    scene.save(root/SCENE)
    # Preserve the original scene GUID: saved editor build settings already reference it.
    Path(str(root/SCENE)+'.meta').write_text(scene_meta)
    script_meta={'fileFormatVersion':2,'guid':guid(SCRIPT),'MonoImporter':{'externalObjects':{},'serializedVersion':2,'defaultReferences':[],
        'executionOrder':0,'icon':{'fileID':0},'userData':'','assetBundleName':'','assetBundleVariant':''}}
    Path(str(root/SCRIPT)+'.meta').write_text(yaml.safe_dump(script_meta,sort_keys=False))
    meta(root/PLAYER,kind='folder')
    sky=root/'Assets/TerrainDemoScene_URP/Prefabs/Skybox/Materials/Sky.mat'
    old=next(d for c,i,n,d in documents(sky) if n=='Material')
    old.update(m_Shader=ref(106,'0000000000000000f000000000000000',0),m_ShaderKeywords='_SUNDISK_HIGH_QUALITY')
    old['m_SavedProperties']={'serializedVersion':3,'m_TexEnvs':[],'m_Floats':[
        {'_SunDisk':2},{'_SunSize':.035},{'_SunSizeConvergence':5},{'_AtmosphereThickness':1},{'_Exposure':1.05}],
        'm_Colors':[{'_SkyTint':color(.50,.55,.60)},{'_GroundColor':color(.35,.36,.32)}]}
    write_yaml(sky,[(21,2100000,'Material',old)])
    for name in ['Asphalt','Concrete','Sand','RoadMark']:
        path=root/'Assets/AarisWorld/Surfaces'/(name+'.png')
        old_guid=yaml.safe_load(Path(str(path)+'.meta').read_text())['guid']
        meta(path,texture={});data=yaml.safe_load(Path(str(path)+'.meta').read_text());data['guid']=old_guid
        Path(str(path)+'.meta').write_text(yaml.safe_dump(data,sort_keys=False))
    graphics=root/'ProjectSettings/GraphicsSettings.asset';gs=documents(graphics)[0][3]
    gs['m_AlwaysIncludedShaders']=[ref(106,'0000000000000000f000000000000000',0)]
    write_yaml(graphics,[(30,1,'GraphicsSettings',gs)])
    settings_path=root/'ProjectSettings/ProjectSettings.asset';settings=documents(settings_path)[0][3]
    settings['productName']='Aaris Ground Review';settings['bundleVersion']='0.2.1';settings['AndroidBundleVersionCode']=3
    write_yaml(settings_path,[(129,1,'PlayerSettings',settings)])
    quality={'serializedVersion':3,'name':'Aaris Ground','pixelLightCount':1,'shadows':2,'shadowResolution':2,'shadowProjection':1,
        'shadowCascades':2,'shadowDistance':100,'shadowNearPlaneOffset':3,'shadowCascade2Split':.25,'shadowCascade4Split':vec(.067,.2,.467),
        'shadowmaskMode':0,'skinWeights':4,'globalTextureMipmapLimit':0,'textureMipmapLimitSettings':[],
        'anisotropicTextures':2,'antiAliasing':0,'softParticles':0,'softVegetation':1,'realtimeReflectionProbes':0,
        'billboardsFaceCameraPosition':1,'vSyncCount':0,'lodBias':1,'maximumLODLevel':0,
        'streamingMipmapsActive':1,'streamingMipmapsAddAllCameras':1,'streamingMipmapsMemoryBudget':384,
        'streamingMipmapsRenderersPerFrame':128,'streamingMipmapsMaxLevelReduction':2,'streamingMipmapsMaxFileIORequests':64,
        'particleRaycastBudget':256,'asyncUploadTimeSlice':2,'asyncUploadBufferSize':16,'asyncUploadPersistentBuffer':1,
        'resolutionScalingFixedDPIFactor':1,'customRenderPipeline':ref(11400000,'4f455263fdaa19b4894b6dbdb822f8d6'),
        'excludedTargetPlatforms':[]}
    write_yaml(root/'ProjectSettings/QualitySettings.asset',[(47,1,'QualitySettings',{'m_ObjectHideFlags':0,'serializedVersion':5,
        'm_CurrentQuality':0,'m_QualitySettings':[quality],'m_TextureMipmapLimitGroupNames':[],'m_PerPlatformDefaultQuality':{'Android':0,'Standalone':0}})])
    signature=hashlib.sha256(json.dumps({k:layout[k] for k in ['districts','roads','vehicle_spawns']},sort_keys=True).encode()+h.tobytes()).hexdigest()
    plan_path=root/'Docs/FOREST_PLANTING_PLAN.json'
    prior=json.loads(plan_path.read_text()) if plan_path.exists() else {}
    plan=prior['placements'] if prior.get('layout_fingerprint')==signature else forest_plan(root,layout,h)
    plan_path.write_text(json.dumps({'schema_version':1,'seed':20261103,'layout_fingerprint':signature,'placements':plan},indent=2)+'\n')
    report={'schema_version':1,'native_assets_materialized':False,'unity_editor_import_tested':False,'android_playtest_passed':False,
        'player_height_m':1.78,'spawn_m':list(spawn),'follow_distance_m':4.2,'free_flight_camera_removed':True,
        'planned_new_trees':len(plan),'new_trees_by_tile':dict(Counter(p['tile'] for p in plan)),
        'native_terrain_heights_unchanged':True,'source_tree_models_reused':True,'tree_clearance_road_m':17,
        'tree_clearance_district_m':18,'target_frame_rate':30,'render_scale_or_texture_resolution_reduced':False}
    (root/'Docs/GROUND_REVIEW_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return report

if __name__=='__main__':upgrade(Path.cwd())
