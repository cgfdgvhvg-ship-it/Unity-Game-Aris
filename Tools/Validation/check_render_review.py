"""Fail on invisible player layers, stale shader checks or material import drift."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Tools/MapBuild'))
from ground_review import documents
from render_review import floats,PIPELINE,RENDERER

def check():
    report=json.loads((ROOT/'Docs/RENDER_REVIEW_REPORT.json').read_text());audit=json.loads((ROOT/'Docs/RENDER_SOURCE_AUDIT.json').read_text())
    assert report['native_assets_materialized'] and report['materials_checked']==182
    assert audit['cull_mismatches']==audit['normal_scale_mismatches']==audit['occlusion_strength_mismatches']==0
    for row in audit['materials']:
        d=documents(ROOT/row['path'])[0][3];f=floats(d)
        assert f['_Cull']==row['expected_cull'] and f['_BumpScale']==row['source_normal_scale']
        assert f['_OcclusionStrength']==row['source_occlusion_strength'] and d['m_DoubleSidedGI']==int(row['source_double_sided'])
    for relative,expected in report['native_pipeline_files'].items():
        raw=(ROOT/relative).read_bytes()
        if raw.startswith(b'version https://git-lfs'):assert ('oid sha256:'+expected['sha256']).encode()in raw
        else:
            assert hashlib.sha256(raw).hexdigest()==expected['sha256']
            if relative==RENDERER:
                d=documents(ROOT/relative)[0][3]
                assert all(d[k]['m_Bits']==mask for k,mask in report['saved_renderer_masks'].items())
    objects=documents(ROOT/'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity');layers={i:d['m_Layer'] for c,i,n,d in objects if n=='GameObject'}
    used={layers[d['m_GameObject']['fileID']] for c,i,n,d in objects if n in ('MeshRenderer','Terrain')}
    for mask in report['saved_renderer_masks'].values():
        assert all(mask&(1<<layer) for layer in used),(used,mask,'Renderer hides a saved scene layer')
        assert mask&(1<<8),'Player layer is invisible'
    assert report['render_scale']==report['hdr']==report['srp_batcher']==1
    water=documents(ROOT/'Assets/AarisWorld/Surfaces/CoastalWater.mat')[0][3];assert floats(water)['_Smoothness']==.82
    shader=ROOT/'Assets/AarisWorld/Surfaces/CoastalWater.shader';source=shader.read_text()
    assert '"LightMode"="DepthOnly"'in source and 'UniversalFragmentPBR(lighting, water)'in source
    hlsl=json.loads((ROOT/'Docs/WATER_HLSL_CHECKS.json').read_text())
    assert hlsl['status']=='dxc_hlsl_checks_passed' and hlsl['compilations_passed']==52
    assert hlsl['shader_sha256']==hashlib.sha256(shader.read_bytes()).hexdigest(),'Shader changed since compilation checks'
    result={'status':'core_render_checks_passed','materials_checked':182,'visible_scene_layers':sorted(used),'player_layer_visible':True,
        'water_hlsl_compilations':52,'render_scale':1,'unity_shaderlab_import_tested':False,'unity_android_build_tested':False,'android_device_tested':False}
    (ROOT/'Docs/RENDER_CORE_CHECKS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return result

if __name__=='__main__':check()
