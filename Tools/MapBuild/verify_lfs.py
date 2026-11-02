"""Check actual newly authored LFS objects without downloading unrelated sources."""
import hashlib,json,re,subprocess
from pathlib import Path
root=Path.cwd();paths=list((root/'Assets/AarisWorld').rglob('*.asset'))+list((root/'Assets/AarisWorld').rglob('*.png'))+list((root/'Assets/TerrainDemoScene_URP/Terrain/Data').glob('*.asset'))
for path in paths:
    relative=str(path.relative_to(root));pointer=subprocess.check_output(['git','show','HEAD:'+relative]).decode()
    m=re.fullmatch(r'version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)\n',pointer)
    assert m,relative+' was not committed through Git LFS'
    data=path.read_bytes();assert len(data)==int(m[2]) and hashlib.sha256(data).hexdigest()==m[1],relative
    obj=root/'.git/lfs/objects'/m[1][:2]/m[1][2:4]/m[1];assert obj.is_file(),relative
print(json.dumps({'verified_new_lfs_objects':len(paths),'status':'passed'}))
