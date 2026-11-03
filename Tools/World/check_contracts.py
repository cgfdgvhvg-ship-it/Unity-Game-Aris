"""CI checks for the real saved scene, C# syntax and workflow request boundaries."""
import sys
import re
from pathlib import Path

import tree_sitter
import tree_sitter_c_sharp
import yaml

from unity_data import SCENE, World
from capabilities import schema as automation_schema

root=Path(__file__).resolve().parents[2]
parser=tree_sitter.Parser(tree_sitter.Language(tree_sitter_c_sharp.language()))
for path in list((root/'Assets/AarisWorld/Editor').glob('World*.cs'))+[root/'Assets/AarisWorld/Scripts/AarisMobileRuntime.cs']:
    tree=parser.parse(path.read_bytes())
    assert not tree.root_node.has_error, str(path)+' C# syntax error'
    assert Path(str(path)+'.meta').is_file(), str(path)+' requires stable metadata'
w=World(root)
assert len(w.terrains())==4
assert len([d for d in w.gos.values() if re.fullmatch(r'VehicleSpawnPoint_\d{2}',d.get('m_Name',''))])==45
contract=automation_schema()
assert contract['protocol_version']==2
for operation in ('set_transform','place_static_prefab','terrain_instance_move','terrain_instance_add','instantiate_prefab','duplicate_object','delete_object'):
    assert operation in contract['write_operations'], operation+' missing from machine contract'
bridge=(root/'Assets/AarisWorld/Editor/WorldBridge.cs').read_text()
for symbol in ('ObservationRequest','TerrainEdit','SceneEdit','ApplyTerrainInstances','ApplySceneEdits'):
    assert symbol in bridge, symbol+' missing from Unity editor bridge'
for f in ('world-query.yml','world-engine-query.yml','world-core-edit.yml','world-query-cleanup.yml','world-automation-checks.yml'):
    text=(root/'.github/workflows'/f).read_text(); doc=yaml.load(text,Loader=yaml.BaseLoader)
    assert 'on' in doc and 'jobs' in doc
    assert '${{ inputs.request_json }}' not in '\n'.join(s.get('run','') for j in doc['jobs'].values() for s in j.get('steps',[]))
    assert '${{ inputs.patch_json }}' not in '\n'.join(s.get('run','') for j in doc['jobs'].values() for s in j.get('steps',[]))
    for j in doc['jobs'].values():
        for s in j.get('steps',[]):
            if 'uses' in s: assert len(s['uses'].split('@')[-1])==40, 'Pin actions to reviewed commits'
assert 'buildGuid = Application.buildGUID' in (root/'Assets/AarisWorld/Scripts/AarisMobileRuntime.cs').read_text()
print('Real scene: four terrains and 45 spawn markers; C# syntax and workflow request boundaries passed. Unity import/physics not executed.')

