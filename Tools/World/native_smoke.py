"""Read actual LFS terrain in CI; confirm pointer identity, seams and no writes."""
import json
import math
import re
import subprocess

from unity_data import World, digest
from terrain import NativeTerrain
from world import ROOT


def main():
    w=World(ROOT); native=NativeTerrain(w); assert len(native.tiles)==4
    before={t['asset']['path']:digest(ROOT/t['asset']['path']) for t in native.tiles}
    linked=0
    for path,sha in before.items():
        r=subprocess.run(['git','show','HEAD:'+path],cwd=ROOT,capture_output=True,check=False)
        if r.returncode==0:
            m=re.search(rb'(?m)^oid sha256:([a-f0-9]{64})$',r.stdout)
            assert m and m[1].decode()==sha, 'LFS pointer/content mismatch: '+path
            linked+=1
    summary=native.summary(); assert all(t['status']=='decoded' for t in summary)
    for tile in native.tiles:
        d=native.load(tile);x,y,z=tile['origin_m']
        assert all(math.isfinite(v) for v in (d['heights'].min(),d['heights'].max()))
        sample=native.height(x+d['size_m'][0]/2,z+d['size_m'][2]/2)
        assert sample['samples'] and all(math.isfinite(r['height_m']) for r in sample['samples'])
    seams=native.seams();assert len(seams)==4 and all(s['max_delta_m']<=.05 for s in seams)
    assert all(digest(ROOT/p)==sha for p,sha in before.items()), 'Read query changed source bytes'
    if (ROOT/'.git').exists(): assert linked==4
    print(json.dumps({'native_tiles_read':4,'lfs_pointer_identities_verified':linked,
          'native_instances':sum(sum(t['instances'].values()) for t in summary),
          'max_seam_delta_m':max(s['max_delta_m'] for s in seams),'core_bytes_unchanged':True,
          'unity_engine_executed':False}))


if __name__=='__main__':main()
