"""Save corrected road paint meshes in place. No Unity pre/export method is needed."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
from road_markings import read_mesh,project_markings,heights_on_mesh,PAINT_OFFSET_M

def save(root):
    root=Path(root);folder=root/'Assets/AarisWorld/Surfaces'
    layout=json.loads((root/'Docs/MAP_LAYOUT.json').read_text());records=[]
    for k,road in enumerate(layout['roads']):
        paved=folder/f'Road_{k:02d}.asset';paint=folder/f'RoadMark_{k:02d}.asset'
        if not paint.exists():continue
        before_road=hashlib.sha256(paved.read_bytes()).hexdigest()
        vertices,triangles,template=read_mesh(paved)
        old,old_tri,_=read_mesh(paint)
        samples=np.vstack((old,old[old_tri].mean(axis=1)))
        old_gap=samples[:,1]-heights_on_mesh(vertices,triangles,samples)
        pos,ind,area=project_markings(vertices,triangles,road['points'])
        meta=Path(str(paint)+'.meta');old_meta=meta.read_bytes()
        # Paint normals follow each paved triangle, not the terrain beneath it.
        from surfaces import surface
        surface(paint,pos[:,[0,2]],ind,pos[:,1],template)
        meta.write_bytes(old_meta)
        actual,actual_tri,_=read_mesh(paint)
        samples=np.vstack((actual,actual[actual_tri].mean(axis=1)))
        gap=samples[:,1]-heights_on_mesh(vertices,triangles,samples)
        assert np.isfinite(gap).all(),road['name']+' paint outside road'
        assert np.max(np.abs(gap-PAINT_OFFSET_M))<.0002,(road['name'],float(gap.min()),float(gap.max()))
        assert hashlib.sha256(paved.read_bytes()).hexdigest()==before_road,'Paved mesh changed'
        first=paint.read_bytes()
        surface(paint,pos[:,[0,2]],ind,pos[:,1],template);meta.write_bytes(old_meta)
        assert paint.read_bytes()==first,'Paint serialization is not reproducible'
        finite=old_gap[np.isfinite(old_gap)]
        records.append({'road':road['name'],'mesh':str(paint.relative_to(root)),**area,
            'old_samples_below_pavement':int((finite<0).sum()),'old_min_gap_m':float(finite.min()),'old_max_gap_m':float(finite.max()),
            'saved_min_gap_m':float(gap.min()),'saved_max_gap_m':float(gap.max()),'saved_triangles':len(actual_tri)})
    assert records,'No road markings found'
    report={'status':'native_mesh_checks_passed','road_meshes_unchanged':True,'paint_meshes_saved':len(records),
        'paint_offset_m':PAINT_OFFSET_M,'reproducible_serialization_checked':True,'roads':records,
        'unity_render_tested':False,'android_device_tested':False}
    (root/'Docs/ROAD_SURFACE_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'paint_meshes_saved':len(records),'old_samples_below_pavement':sum(r['old_samples_below_pavement'] for r in records)}))
    return report

if __name__=='__main__':save(Path.cwd())
