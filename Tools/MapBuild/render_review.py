"""Audit actual URP settings and pinned source material semantics offline."""
from __future__ import annotations
import json,re
from pathlib import Path
from ground_review import documents
from native_assets import Glb

PIPELINE='Assets/TerrainDemoScene_URP/Settings/URP/URP-HighQuality Pipeline Asset.asset'
RENDERER='Assets/TerrainDemoScene_URP/Settings/URP/Universal Render Pipeline Asset_Renderer.asset'

def floats(material):return {k:v for item in material['m_SavedProperties']['m_Floats'] for k,v in item.items()}

def audit(root):
    from build_map import source_cache
    root=Path(root);sources,cache=source_cache();entries=[]
    for source in sources:
        glb=Glb(cache/(source['id']+'.glb'));folder=root/'Assets/AarisWorld/Models'/source['id']
        for path in sorted(folder.glob('Material_*.mat')):
            index=int(path.stem.split('_')[-1]);source_material=glb.g.get('materials',[])[index] if index>=0 else {}
            material=documents(path)[0][3];settings=floats(material)
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

if __name__=='__main__':audit(Path.cwd())
