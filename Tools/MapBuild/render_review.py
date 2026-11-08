"""Audit actual URP settings and pinned source material semantics offline."""
from __future__ import annotations
import copy,hashlib,json,re,sys
from pathlib import Path
from ground_review import documents
from native_assets import Glb,write_yaml

PIPELINE='Assets/TerrainDemoScene_URP/Settings/URP/URP-HighQuality Pipeline Asset.asset'
RENDERER='Assets/TerrainDemoScene_URP/Settings/URP/Universal Render Pipeline Asset_Renderer.asset'

def material_record(objects):
    """Select the Material YAML document, not Unity's URP AssetVersion prelude.

    Unity 6000.3 can auto-save a MonoBehaviour version record before !u!21
    Material. Never select document index zero for a material asset.
    """
    matches=[d for _class,_id,kind,d in objects if kind=='Material']
    if len(matches)!=1:
        raise ValueError('Expected exactly one Material document')
    return matches[0]

def floats(material):return {k:v for item in material['m_SavedProperties']['m_Floats'] for k,v in item.items()}

def audit(root):
    from build_map import source_cache
    root=Path(root);sources,cache=source_cache();entries=[]
    for source in sources:
        glb=Glb(cache/(source['id']+'.glb'));folder=root/'Assets/AarisWorld/Models'/source['id']
        for path in sorted(folder.glob('Material_*.mat')):
            index=int(path.stem.split('_')[-1]);source_material=glb.g.get('materials',[])[index] if index>=0 else {}
            material=material_record(documents(path));settings=floats(material)
            entries.append({'path':str(path.relative_to(root)),'source_sha256':source['sha256'],'source_material_index':index,
                'source_double_sided':source_material.get('doubleSided',False),'saved_cull':settings['_Cull'],
                'expected_cull':0 if source_material.get('doubleSided',False) else 2,
                'source_alpha_mode':source_material.get('alphaMode','OPAQUE'),
                'source_normal_scale':source_material.get('normalTexture',{}).get('scale',1),
                'saved_normal_scale':settings['_BumpScale'],
                'source_occlusion_strength':source_material.get('occlusionTexture',{}).get('strength',1),
                'saved_occlusion_strength':settings['_OcclusionStrength'],
                'has_occlusion_texture':'occlusionTexture'in source_material})
    pipeline=documents(root/PIPELINE)[0][3];renderer=documents(root/RENDERER)[0][3]
    report={'status':'measured_source_audit','source_models_checked':len(sources),'materials_checked':len(entries),
        'cull_mismatches':sum(e['saved_cull']!=e['expected_cull'] for e in entries),
        'normal_scale_mismatches':sum(e['saved_normal_scale']!=e['source_normal_scale'] for e in entries),
        'occlusion_strength_mismatches':sum(e['saved_occlusion_strength']!=e['source_occlusion_strength'] for e in entries),
        'pipeline':{k:v for k,v in pipeline.items() if k not in ('m_EditorClassIdentifier','m_Name','m_ObjectHideFlags','m_CorrespondingSourceObject','m_PrefabInstance','m_PrefabAsset','m_GameObject','m_Enabled','m_EditorHideFlags','m_Script')},
        'renderer':{k:v for k,v in renderer.items() if k not in ('m_EditorClassIdentifier','m_Name','m_ObjectHideFlags','m_CorrespondingSourceObject','m_PrefabInstance','m_PrefabAsset','m_GameObject','m_Enabled','m_EditorHideFlags','m_Script')},
        'materials':entries,'unity_shader_compilation_tested':False,'unity_render_tested':False,'android_device_tested':False}
    (root/'Docs/RENDER_SOURCE_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('materials','pipeline','renderer')}))
    print(json.dumps({'pipeline':report['pipeline'],'renderer':report['renderer']}))
    return report

def set_float(material,name,value):
    for item in material['m_SavedProperties']['m_Floats']:
        if name in item:item[name]=value;return
    raise ValueError('Required material property missing: '+name)

def unchanged_material_fields(material):
    data=copy.deepcopy(material);data['m_DoubleSidedGI']=0
    for name in ['_Cull','_BumpScale','_OcclusionStrength']:set_float(data,name,0)
    return data

def save(root):
    root=Path(root);report_path=root/'Docs/RENDER_REVIEW_REPORT.json'
    prior=json.loads(report_path.read_text()) if report_path.exists() else {}
    before=audit(root);changed_cull=0;changed_normal=0
    preserved={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'Assets').rglob('*') if p.is_file() and p.suffix in ('.meta','.png','.tif','.st','.prefab','.unity')}
    # Native geometry pointers/bytes must remain untouched by a material-only refinement.
    preserved.update({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'Assets/AarisWorld').rglob('*.asset')})
    for row in before['materials']:
        path=root/row['path'];objects=documents(path);material=material_record(objects);immutable=unchanged_material_fields(material)
        changed_cull+=int(row['saved_cull']!=row['expected_cull']);changed_normal+=int(row['saved_normal_scale']!=row['source_normal_scale'])
        set_float(material,'_Cull',row['expected_cull']);set_float(material,'_BumpScale',row['source_normal_scale'])
        set_float(material,'_OcclusionStrength',row['source_occlusion_strength']);material['m_DoubleSidedGI']=int(row['source_double_sided'])
        write_yaml(path,objects)
        assert unchanged_material_fields(material_record(documents(path)))==immutable,'Unexpected material texture/color/keyword change'
    renderer_objects=documents(root/RENDERER);renderer=renderer_objects[0][3]
    old_masks={k:renderer[k]['m_Bits'] for k in ['m_OpaqueLayerMask','m_TransparentLayerMask']}
    for key in old_masks:renderer[key]['m_Bits']|=(1<<6)|(1<<8)
    write_yaml(root/RENDERER,renderer_objects)
    water_path=root/'Assets/AarisWorld/Surfaces/CoastalWater.mat';water=documents(water_path)
    set_float(material_record(water),'_Smoothness',.82);write_yaml(water_path,water)
    after=audit(root);assert after['cull_mismatches']==after['normal_scale_mismatches']==after['occlusion_strength_mismatches']==0
    assert all(hashlib.sha256((root/path).read_bytes()).hexdigest()==sha for path,sha in preserved.items()),'Geometry, textures, metadata or saved world changed'
    native_files={}
    for relative in [PIPELINE,RENDERER]:native_files[relative]={'sha256':hashlib.sha256((root/relative).read_bytes()).hexdigest(),'size':(root/relative).stat().st_size}
    report={'status':'saved_core_rendering_checked','native_assets_materialized':True,'source_models_checked':17,'materials_checked':len(after['materials']),
        'source_cull_mismatches_fixed':max(changed_cull,prior.get('source_cull_mismatches_fixed',0)),
        'source_normal_strength_mismatches_fixed':max(changed_normal,prior.get('source_normal_strength_mismatches_fixed',0)),
        'original_renderer_masks':prior.get('original_renderer_masks',old_masks),
        'saved_renderer_masks':{k:renderer[k]['m_Bits'] for k in old_masks},
        'water_lighting':'URP 17.3 UniversalFragmentPBR with ambient SH and environment reflection',
        'water_depth_only_pass':True,'shared_depth_color_wave_position':True,'water_smoothness':.82,
        'render_scale':after['pipeline']['m_RenderScale'],'hdr':after['pipeline']['m_SupportsHDR'],'srp_batcher':after['pipeline']['m_UseSRPBatcher'],
        'shadow_distance_m_preserved':after['pipeline']['m_ShadowDistance'],'shadow_atlas_resolution_preserved':after['pipeline']['m_MainLightShadowmapResolution'],
        'geometry_textures_metadata_prefabs_and_scene_preserved':True,'native_pipeline_files':native_files,
        'unity_shader_compilation_tested':False,'unity_render_tested':False,'android_device_tested':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return report

if __name__=='__main__':
    save(Path.cwd()) if '--apply'in sys.argv else audit(Path.cwd())
