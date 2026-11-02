"""Publish searchable text indexes alongside the native binary TerrainData."""
import csv,json,math
from collections import Counter
from pathlib import Path
import numpy as np
from sculpt import BASE,STEP

def export(t,docs,tools):
    docs=Path(docs);tools=Path(tools);known=json.loads((tools/'source_prototypes.json').read_text())
    paths={v:k.removesuffix('.meta') for k,v in known.items()};summary=[]
    for tag,d in t.data.items():
        i,j=map(int,tag.split('_'));ox=(i-2)*1000;oz=(j-2)*1000;e,o=t.env[tag]
        externals={}
        for index,item in enumerate(o.assets_file.externals,1):
            s=item.guid.hex();g=''.join(s[a+1]+s[a] for a in range(0,32,2));externals[index]={'guid':g,'path':paths.get(g)}
        db=d['m_DetailDatabase'];protos=[]
        for p in db['m_TreePrototypes']:
            asset=externals[p['prefab']['m_FileID']];path=asset['path'];assert path,(tag,'unresolved tree prototype',asset['guid'])
            cat='tree' if '/Trees/' in path else 'rock' if '/Rocks/' in path else 'shrub'
            protos.append({**asset,'category':cat})
        folder=docs/'TerrainInstances';folder.mkdir(exist_ok=True);counts=Counter()
        with (folder/f'Terrain_{tag}.jsonl').open('w') as f:
            for k,inst in enumerate(db['m_TreeInstances']):
                p=inst['position'];proto=protos[inst['index']];counts[proto['category']]+=1
                row={'id':f'{tag}_{k:05d}',**proto,'position_m':[round(ox+p['x']*1000,3),round(BASE+p['y']*800,3),round(oz+p['z']*1000,3)],
                     'yaw_degrees':round(math.degrees(inst['rotation']),3),'width_scale':round(inst['widthScale'],4),'height_scale':round(inst['heightScale'],4)}
                f.write(json.dumps(row,separators=(',',':'))+'\n')
        folder=docs/'TerrainHeightSamples';folder.mkdir(exist_ok=True)
        h=np.asarray(d['m_Heightmap']['m_Heights']).reshape(2049,2049)[::16,::16]/32766*800+BASE
        axis=np.arange(129)*STEP*16
        with (folder/f'Terrain_{tag}.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['world_z_m / world_x_m',*[round(ox+a,4) for a in axis]])
            for z,row in zip(axis,h):writer.writerow([round(oz+z,4),*[round(float(v),3) for v in row]])
        # Detail density is a patch distribution, not exact procedural grass positions.
        folder=docs/'TerrainDetails';folder.mkdir(exist_ok=True);patches=0
        with (folder/f'Terrain_{tag}.jsonl').open('w') as f:
            for k,patch in enumerate(db['m_Patches']):
                if not patch['layerIndices']:continue
                n=db['m_PatchSamples']**2;values=patch['numberOfObjects'];assert len(values)==n*len(patch['layerIndices'])
                row={'patch_x':k%64,'patch_z':k//64,'world_center_xz_m':[round(ox+(k%64+.5)*1000/64,4),round(oz+(k//64+.5)*1000/64,4)],
                     'patch_size_m':1000/64,'layers':[{'prototype':layer,'density_sum':sum(values[a*n:(a+1)*n])} for a,layer in enumerate(patch['layerIndices'])]}
                f.write(json.dumps(row,separators=(',',':'))+'\n');patches+=1
        summary.append({'tile':tag,'terrain_instances':dict(counts),'detail_density_patches':patches,'tree_and_rock_prototypes':protos,
                        'detail_prototypes_native_properties':db['m_DetailPrototypes']})
    (docs/'TERRAIN_INDEX.json').write_text(json.dumps({'units':'metres','height_sample_spacing_m':STEP*16,
        'height_csv_note':'Sampled world-space heights; authoritative full 0.48828125m grid remains in native TerrainData.',
        'instance_jsonl_note':'Exact retained native tree/rock/shrub instances, rounded to 1mm. Terrain uses procedural detail density patches for grass.',
        'tiles':summary},indent=2)+'\n')
