"""Clip paint to the actual paved triangles; offline native mesh authoring only."""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import yaml

PAINT_OFFSET_M = 0.035

def read_mesh(path):
    raw=Path(path).read_text()
    assert raw.startswith('%YAML'),f'Fetch native mesh bytes first: {path}'
    body=re.split(r'(?m)^--- .*\n',raw,maxsplit=1)[1]
    body=re.sub(r'(?m)^(\s*(?:_typelessdata|m_IndexBuffer):) ([0-9a-f]+)$',r'\1 "\2"',body)
    d=yaml.load(body,Loader=yaml.CSafeLoader)['Mesh'];vd=d['m_VertexData']
    vertex=np.frombuffer(bytes.fromhex(str(vd['_typelessdata'])),dtype='<f4').reshape(-1,12)
    assert len(vertex)==vd['m_VertexCount'] and vd['m_DataSize']==len(vertex)*48
    indices=np.frombuffer(bytes.fromhex(str(d['m_IndexBuffer'])),dtype='<u4').reshape(-1,3)
    return vertex[:,:3].astype(float),indices,raw

def cross(a,b):
    return a[...,0]*b[...,1]-a[...,1]*b[...,0]

def clip_polygon(polygon,triangle):
    """Convex intersection in XZ, accepting either winding of the road triangle."""
    orientation=np.sign(cross(triangle[1]-triangle[0],triangle[2]-triangle[0]))
    if not orientation:return []
    result=[p.copy() for p in polygon]
    for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
        if not result:break
        source=result;result=[];previous=source[-1]
        previous_distance=orientation*cross(b-a,previous-a)
        for current in source:
            distance=orientation*cross(b-a,current-a)
            inside=distance>=-1e-9;was_inside=previous_distance>=-1e-9
            if inside!=was_inside:
                weight=previous_distance/(previous_distance-distance)
                result.append(previous+(current-previous)*weight)
            if inside:result.append(current)
            previous=current;previous_distance=distance
    return result

def paint_quads(points):
    points=np.asarray(points,float)
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
    assert np.all(np.diff(distance)>0),'Repeated road centerline point'
    for start in np.arange(5,distance[-1]-5,15):
        a,b=np.array([[np.interp(d,distance,points[:,axis]) for axis in (0,2)] for d in (start,start+5)])
        delta=b-a;length=np.linalg.norm(delta)
        if length<1e-6:continue
        side=np.array([-delta[1],delta[0]])/length*.07
        yield np.array([a+side,b+side,b-side,a-side])

def project_markings(vertices,triangles,points):
    """Split every painted dash at road triangle boundaries before projecting Y."""
    road=np.asarray(vertices,float)[triangles];xz=road[:,:,[0,2]]
    low=xz.min(axis=1);high=xz.max(axis=1)
    valid=np.abs(cross(xz[:,1]-xz[:,0],xz[:,2]-xz[:,0]))>1e-9
    planes=np.zeros((len(road),3))
    planes[valid]=np.linalg.solve(np.concatenate((xz[valid],np.ones((valid.sum(),3,1))),axis=2),road[valid,:,1,None])[:,:,0]
    positions=[];indices=[];source_area=0.;covered_area=0.
    for quad in paint_quads(points):
        source_area+=abs(float(cross(quad[1]-quad[0],quad[3]-quad[0])))
        candidates=np.flatnonzero(valid & np.all(high>=quad.min(axis=0)-1e-8,axis=1)&np.all(low<=quad.max(axis=0)+1e-8,axis=1))
        for n in candidates:
            clipped=clip_polygon(quad,xz[n])
            if len(clipped)<3:continue
            p=np.asarray(clipped)
            # Clipping can repeat shared vertices; discard zero-area fans explicitly.
            local=[]
            for k in range(1,len(p)-1):
                signed=float(cross(p[k]-p[0],p[k+1]-p[0]))
                if abs(signed)<1e-9:continue
                local.append((0,k+1,k) if signed>0 else (0,k,k+1))
                covered_area+=abs(signed)*.5
            if not local:continue
            start=len(positions);y=np.column_stack((p,np.ones(len(p))))@planes[n]+PAINT_OFFSET_M
            positions.extend(np.column_stack((p[:,0],y,p[:,1])))
            indices.extend((np.asarray(local)+start).tolist())
    assert source_area>0 and covered_area>=source_area*.995,('Paint outside pavement',covered_area,source_area)
    assert covered_area<=source_area*1.005,('Overlapping paved triangles duplicate paint',covered_area,source_area)
    return np.asarray(positions),np.asarray(indices,dtype='u4'),{'paint_area_m2':source_area,'covered_area_m2':covered_area}

def heights_on_mesh(vertices,triangles,positions):
    """Measured paved height below samples; NaN means outside the paved footprint."""
    road=np.asarray(vertices)[triangles];xz=road[:,:,[0,2]];out=[]
    for point in np.asarray(positions):
        p=point[[0,2]];a=xz[:,0];u=xz[:,1]-a;v=xz[:,2]-a;den=cross(u,v)
        valid=np.abs(den)>1e-9;s=np.divide(cross(p-a,v),den,out=np.zeros(len(den)),where=valid)
        t=np.divide(cross(u,p-a),den,out=np.zeros(len(den)),where=valid)
        inside=valid&(s>=-1e-5)&(t>=-1e-5)&(s+t<=1+1e-5)
        y=road[:,0,1]+s*(road[:,1,1]-road[:,0,1])+t*(road[:,2,1]-road[:,0,1])
        out.append(float(y[inside].max()) if inside.any() else float('nan'))
    return np.asarray(out)
