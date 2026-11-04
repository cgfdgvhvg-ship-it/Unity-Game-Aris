"""Reproduce this reviewed migration in an isolated checkout; never merge or build an APK."""
import hashlib
import json
from pathlib import Path

from patching import apply_yaml,preview_yaml,atomic_write
from tree_shapes import apply as apply_trees,plan as plan_trees
from unity_data import digest,WorldError
from verify_tree_house_upgrade import CONTRACT,verify


def run(root):
    root=Path(root).resolve();contract=json.loads((root/CONTRACT).read_text())
    house=json.loads((root/'Tools/World/house-openings-20261103.json').read_text())
    trees=json.loads((root/'Tools/World/tree-proportions-20261103.json').read_text())
    expected_after={p:r['after_sha256']for p,r in contract['meshes'].items()}
    expected_after.update(contract['tree_source_files'])
    if all(digest(root/p)==sha for p,sha in expected_after.items()):
        return {'already_applied':True,**verify(root)}
    _,tree_outputs=plan_trees(root,trees)
    for path,data in tree_outputs.items():
        if hashlib.sha256(data.encode()).hexdigest()!=expected_after[path]:
            raise WorldError('Tree plan differs from the reviewed target: '+path)
    preview=preview_yaml(root,house)
    for path,change in preview['written_file_changes'].items():
        if change['after_sha256']!=expected_after[path]:
            raise WorldError('Mesh preview differs from the reviewed target: '+path)
    print(json.dumps({'preview_verified':True,'mesh_assets':len(preview['written_file_changes']),
                      'observations_available':sum('result'in o for o in preview['post_edit_observations'])}),flush=True)
    originals={p:(root/p).read_bytes()for p in expected_after}
    try:
        apply_yaml(root,house,True)
        apply_trees(root,trees,True)
        return verify(root)
    except BaseException:
        for path,data in originals.items():atomic_write(root/path,data)
        raise


if __name__=='__main__':print(json.dumps(run(Path(__file__).resolve().parents[2])),flush=True)
