"""Exact authored foliage addition proof; never edits runtime assets."""
import hashlib
import json
import re
from pathlib import Path
CONTRACT = 'Tools/World/foliage-core-20261104.json'
SCENE = 'Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity'
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blocks(source):
    return re.split(rb'(?=^--- !u!)', source, flags=re.M)
def identity(block):
    m = re.match(rb'--- !u!\d+ &(-?\d+)', block)
    return m.group(1).decode() if m else 'header'
def restore_foliage_additions(root, source):
    root = Path(root)
    path = root / CONTRACT
    if not path.exists():
        return source
    try:
        c = json.loads(path.read_text())
        if sha(source) != c['after_scene_sha256']:
            return None
        for name, expected in c['asset_sha256'].items():
            if not name.startswith('Assets/AarisWorld/Foliage/') and name != 'Assets/AarisWorld/Foliage.meta':
                return None
            if sha((root / name).read_bytes()) != expected:
                return None
        if sha((root / (SCENE + '.meta')).read_bytes()) != c['scene_meta_sha256']:
            return None
        result, seen = [], set()
        for block in blocks(source):
            key = identity(block)
            if key in seen:
                return None
            seen.add(key)
            if key in c['added_blocks']:
                if sha(block) != c['added_blocks'][key]:
                    return None
                continue
            if key in c['replaced_blocks']:
                row = c['replaced_blocks'][key]
                if sha(block) != row['after_sha256']:
                    return None
                block = row['before_utf8'].encode('utf-8')
            result.append(block)
        if not set(c['added_blocks']).issubset(seen) or not set(c['replaced_blocks']).issubset(seen):
            return None
        restored = b''.join(result)
        return restored if sha(restored) == c['before_scene_sha256'] else None
    except (OSError, ValueError, KeyError, TypeError):
        return None
def verify(root):
    root = Path(root)
    restored = restore_foliage_additions(root, (root / SCENE).read_bytes())
    assert restored is not None, 'Unreviewed foliage or protected scene change'
    c = json.loads((root / CONTRACT).read_text())
    return {'saved_bushes': c['bush_count'], 'clusters': c['cluster_count'], 'native_asset_files_checked': len(c['asset_sha256']), 'existing_scene_restored_exactly': True, 'render_or_physics_tested': False}
if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[2])))
