"""Syntax, saved camera binding and project setup checks. No Unity runtime claim."""
import ast,hashlib,json,re
from pathlib import Path
import yaml
from tree_sitter import Language,Parser
import tree_sitter_c_sharp
ROOT=Path.cwd()
def docs(text):
    for chunk in re.split(r'(?m)^--- !u!',text)[1:]:
        head,body=chunk.split('\n',1);data=yaml.load(body,Loader=yaml.CSafeLoader);name=next(iter(data));yield int(head.split()[0]),int(head.split('&')[1].split()[0]),name,data[name]

def check():
    scene=ROOT/'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity';objects=list(docs(scene.read_text()));byid={i:(c,n,d) for c,i,n,d in objects}
    assert len(byid)==len(objects),'Duplicate Unity scene object IDs'
    go=next(i for c,i,n,d in objects if c==1 and d['m_Name']=='Main Camera');gd=byid[go][2]
    components=[byid[e['component']['fileID']] for e in gd['m_Component']]
    script=ROOT/'Assets/AarisWorld/Scripts/AarisMapExplorer.cs';script_guid=yaml.safe_load(Path(str(script)+'.meta').read_text())['guid']
    explorer=[d for c,n,d in components if c==114 and d['m_Script']['guid']==script_guid]
    assert len(explorer)==1 and explorer[0]['m_Enabled']==1
    assert sum(c==20 for c,n,d in components)==sum(c==81 for c,n,d in components)==1
    assert sum(c==218 for c,i,n,d in objects)==4
    assert sum(c==1 and bool(re.fullmatch('VehicleSpawnPoint_[0-9]+',d['m_Name'])) for c,i,n,d in objects)==45
    assert explorer[0]['terrainClearance']>0 and explorer[0]['maximumAltitude']>=1780
    settings=next(d for c,i,n,d in docs(Path('ProjectSettings/ProjectSettings.asset').read_text()) if n=='PlayerSettings')
    assert settings['activeInputHandler']==0 and settings['AndroidTargetArchitectures']==2 and settings['scriptingBackend']['Android']==1
    # Unity 6.3 rejects the imported vendor renderer's compatibility mode unless
    # its opt-in is present before compiling the selected player target.
    compatibility_targets=('Android','Standalone','WebGL')
    defines=settings.get('scriptingDefineSymbols',{})
    for target in compatibility_targets:
        assert 'URP_COMPATIBILITY_MODE' in defines.get(target,'').split(';'),target+' lost its URP compatibility opt-in'
    generator=ast.parse(Path('Tools/MapBuild/build_map.py').read_text())
    project_settings=next(n for n in generator.body if isinstance(n,ast.FunctionDef) and n.name=='project_settings')
    generated_defines=[]
    for node in ast.walk(project_settings):
        if isinstance(node,ast.Dict):
            generated_defines.extend(ast.literal_eval(v) for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and k.value=='scriptingDefineSymbols')
    assert len(generated_defines)==1 and generated_defines[0]==defines,'Rebuilding the map must preserve committed URP defines'
    deps=json.loads(Path('Packages/manifest.json').read_text())['dependencies'];assert deps['com.unity.modules.imgui']=='1.0.0'
    parser=Parser(Language(tree_sitter_c_sharp.language()));syntax=[]
    for p in Path('Assets/AarisWorld').rglob('*.cs'):
        tree=parser.parse(p.read_bytes());assert not tree.root_node.has_error,'C# syntax error in '+str(p);syntax.append(str(p))
    # Existing TerrainData pointer hashes or materialized bytes must match the saved map report.
    report=json.loads(Path('Docs/MAP_BUILD_REPORT.json').read_text())
    for path,expected in report['terrain_files'].items():
        raw=Path(path).read_bytes()
        if raw.startswith(b'version https://git-lfs'):
            assert ('oid sha256:'+expected['sha256']).encode() in raw
        else:assert hashlib.sha256(raw).hexdigest()==expected['sha256']
    data={'status':'passed','unity_editor_compilation_tested':False,'unity_runtime_input_tested':False,
          'saved_camera_controller_bound':True,'audio_listener_count_on_camera':1,'terrain_count':4,'vehicle_marker_count':45,
          'csharp_syntax_checked':syntax,'map_terrain_bytes_unchanged':True,'urp_compatibility_define_targets':list(compatibility_targets),'android':'ARM64 / IL2CPP / landscape / Android 8+',
          'controls':{'desktop':'WASD/arrows; Q/E height; Shift fast; right-drag look; middle-drag pan; wheel zoom; F home; O overview',
                      'touch':'Hold movement buttons; drag to look; pinch or +/- zoom; Up/Down altitude; Home/Overview/Speed buttons'}}
    Path('Docs/EXPLORER_SETUP_REPORT.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data))
if __name__=='__main__':check()
