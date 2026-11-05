"""Hash-guarded, source-only SpeedTree import profiles and matching saved colliders.

This authors existing .st.meta and .prefab core files. Unity applies the actual
continuous mesh deformation at the next import; Python never pretends to decode
or rewrite a proprietary SpeedTree binary or a TerrainData database.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

import yaml
from unity_data import WorldError, digest, documents, safe_path
from patching import Dumper, atomic_write


def plan(root, patch):
    root=Path(root).resolve()
    if patch.get('schema_version')!=1 or not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}',patch.get('transaction_id','')):
        raise WorldError('A versioned, uniquely identified tree source transaction is required')
    expected=patch.get('expected_files',{});outputs={};facts=[]
    for path,sha in expected.items():
        if not re.fullmatch(r'[a-f0-9]{64}',sha) or digest(safe_path(root,path))!=sha:
            raise WorldError('Stale tree shape source: '+path)
    profiles=patch.get('profiles',[])
    if not profiles or len(profiles)>6:raise WorldError('Supply 1..6 inspected tree profiles')
    for profile in profiles:
        prefab=profile['prefab'];source_meta=profile['source_meta']
        if (not prefab.startswith('Assets/TerrainDemoScene_URP/Prefabs/Trees/') or not prefab.endswith('.prefab') or
                not source_meta.startswith('Assets/TerrainDemoScene_URP/Prefabs/Trees/') or not source_meta.endswith('.st.meta')):
            raise WorldError('Tree authoring is confined to the inspected original prototypes')
        for path in (prefab,prefab+'.meta',source_meta):
            if path not in expected:raise WorldError('Missing tree identity/source precondition: '+path)
        h,b,c=[profile[k]for k in ('height_factor','base_width_factor','crown_width_factor')]
        if any(type(v)not in (int,float)for v in (h,b,c))or not .5<=h<=1 or not 1<=c<=b<=1.8:
            raise WorldError('Invalid explicit tree proportions')
        metadata=(root/source_meta).read_text()
        if re.search(r'aaris-tree-shape-v[0-9]+',metadata):raise WorldError('Tree profile is already authored; inspect current factors before a new edit')
        scale=re.search(r'(?m)^  scaleFactor: ([0-9.eE+-]+)$',metadata)
        if not scale:raise WorldError('Expected SpeedTreeImporter scaleFactor')
        old_scale=float(scale[1]);new_scale=old_scale*h
        metadata=metadata[:scale.start(1)]+format(new_scale,'.10g')+metadata[scale.end(1):]
        tag=f'aaris-tree-shape-v1|{b/h:.9g}|{c/h:.9g}'
        metadata,n=re.subn(r'(?m)^  userData:.*$', '  userData: '+tag,metadata)
        if n!=1:raise WorldError('Expected one SpeedTreeImporter userData field')
        parsed=yaml.safe_load(metadata)
        if parsed['guid']!=yaml.safe_load((root/source_meta).read_text())['guid']:
            raise WorldError('Tree source GUID changed')
        outputs[source_meta]=metadata
        text,docs=documents(root/prefab);edits=[];colliders=[]
        for doc in docs:
            d=doc['data'];kind=doc['kind']
            if kind=='BoxCollider':
                old=json.loads(json.dumps(d))
                d['m_Size']['x']*=b;d['m_Size']['z']*=b;d['m_Size']['y']*=h
                d['m_Center']['x']*=b;d['m_Center']['z']*=b;d['m_Center']['y']*=h
                colliders.append({'file_id':doc['file_id'],'before':{k:old[k]for k in ('m_Size','m_Center')},
                                  'after':{k:d[k]for k in ('m_Size','m_Center')}})
            elif kind=='LODGroup':
                d['m_LocalReferencePoint']['y']*=h
                d['m_LocalReferencePoint']['x']*=(b+c)*.5
                d['m_LocalReferencePoint']['z']*=(b+c)*.5
                # Keep the conservative authored screen-size envelope. The import
                # postprocessor recalculates bounds for every imported mesh/LOD.
            elif kind=='Transform':
                go=next((item['data'] for item in docs if item['kind']=='GameObject'and item['file_id']==d['m_GameObject']['fileID']),{})
                if not go.get('m_Name','').endswith('_Anchor'):continue
                d['m_LocalPosition']['y']*=h
            else:continue
            edits.append((doc,yaml.dump({kind:d},Dumper=Dumper,sort_keys=False,width=100000)))
        if len(colliders)!=1:raise WorldError('Inspect unexpected tree collider structure before editing')
        for doc,body in sorted(edits,key=lambda row:row[0]['body_start'],reverse=True):
            text=text[:doc['body_start']]+body+text[doc['end']:]
        outputs[prefab]=text
        facts.append({'prefab':prefab,'height_factor':h,'base_width_factor':b,'crown_width_factor':c,
                      'old_import_scale':old_scale,'new_import_scale':new_scale,'colliders':colliders,
                      'mesh_deformation':'Unity next import; shared smooth taper for bark, branches, leaves and every LOD',
                      'native_instances_relocated':False,'engine_import_or_render_verified':False})
    return {'transaction_id':patch['transaction_id'],'dry_run':True,'profiles':facts,
            'predicted_files':list(outputs),'requires':'Matching Unity import for actual SpeedTree mesh deformation and rendering'},outputs


def apply(root,patch,write=False):
    root=Path(root).resolve();report,outputs=plan(root,patch)
    if not write:return report
    originals={p:(root/p).read_bytes()for p in outputs}
    with tempfile.TemporaryDirectory(prefix='tree-shape-preview-') as temp:
        for index,(path,data)in enumerate(outputs.items()):
            p=Path(temp)/str(index);p.write_text(data)
            if path.endswith('.prefab'):
                _,old=documents(root/path);_,new=documents(p)
                if [(r['class_id'],r['file_id'],r['kind'])for r in old]!=[(r['class_id'],r['file_id'],r['kind'])for r in new]:
                    raise WorldError('Tree source identity changed')
            else:yaml.safe_load(data)
    for path,sha in patch['expected_files'].items():
        if digest(root/path)!=sha:raise WorldError('Tree source changed during planning')
    try:
        for path,data in outputs.items():atomic_write(root/path,data.encode())
        for path,data in outputs.items():
            if digest(root/path)!=hashlib.sha256(data.encode()).hexdigest():raise WorldError('Tree source read-back mismatch')
    except BaseException:
        for path,data in originals.items():atomic_write(root/path,data)
        raise
    return {**report,'dry_run':False,'written_file_changes':{p:{'before_sha256':hashlib.sha256(data).hexdigest(),
            'after_sha256':digest(root/p)}for p,data in originals.items()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--patch',required=True);parser.add_argument('--write',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    print(json.dumps(apply(root,json.loads(Path(args.patch).read_text()),args.write),allow_nan=False))
