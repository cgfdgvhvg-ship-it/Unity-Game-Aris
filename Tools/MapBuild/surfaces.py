"""Native geometry for paved streets, beaches, aprons, runway and ocean."""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from native_assets import mesh_asset,material_asset,meta,guid
from sculpt import SEA,sample

def texture(path,base,kind):
    rng=np.random.default_rng(1447);n=512
    grain=rng.normal(0,1,(n,n));soft=gaussian_filter(grain,5,mode='wrap')*4
    noise=(grain*.65+soft*.5)*(.032 if kind=='asphalt' else .055)
    rgb=np.clip(np.asarray(base)[None,None,:]+noise[:,:,None],0,1)
    Image.fromarray((rgb*255).astype('u1')).save(path);meta(path,texture={})
    return guid(path)

def materials(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    out={}
    for name,base,smooth in [('Asphalt',(.115,.125,.13),.15),('Concrete',(.5,.49,.46),.25),('Sand',(.63,.58,.46),.1),('RoadMark',(.88,.84,.66),.15)]:
        tx=folder/(name+'.png');texture(tx,base,name.lower())
        out[name]=material_asset(folder/(name+'.mat'),name,base=(1,1,1,1),smoothness=smooth,textures={'_BaseMap':guid(tx)})
    return out

def surface(path,xz,tri,height,template,uv=None):
    xz=np.asarray(xz,float);yy=np.asarray(height,float)
    pos=np.column_stack((xz[:,0],yy,xz[:,1])).astype('f4');ind=np.asarray(tri,dtype='u4').reshape(-1)
    # Derive smooth geometric normals. Winding uses positive-Y front faces.
    nn=np.zeros_like(pos);q=ind.reshape(-1,3);cross=np.cross(pos[q[:,1]]-pos[q[:,0]],pos[q[:,2]]-pos[q[:,0]])
    for ids in q.T:np.add.at(nn,ids,cross)
    nn/=np.maximum(np.linalg.norm(nn,axis=1)[:,None],1e-8)
    return mesh_asset(path,pos,nn,xz/4 if uv is None else uv,ind,template)

def rect(path,x,z,w,d,y,template):
    xz=np.array([[x-w/2,z-d/2],[x-w/2,z+d/2],[x+w/2,z+d/2],[x+w/2,z-d/2]])
    return surface(path,xz,[0,1,2,0,2,3],np.full(4,y),template)

def ribbon(path,points,width,h,template):
    # Native road geometry must conform BETWEEN source road waypoints.
    # A single wide quad can lie 0.4m beneath a curved Unity terrain tile.
    p=np.asarray(points,float);xz=p[:,[0,2]]
    tangent=np.gradient(xz,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-8)
    side=np.column_stack((-tangent[:,1],tangent[:,0]))*width/2
    left=xz+side;right=xz-side
    rows=[];cross_sections=4;max_step=1.75
    for k in range(len(xz)-1):
        steps=max(1,int(np.ceil(max(np.linalg.norm(left[k+1]-left[k]),np.linalg.norm(right[k+1]-right[k]))/max_step)))
        for step in range(steps):
            f=step/steps
            a=left[k]*(1-f)+left[k+1]*f;b=right[k]*(1-f)+right[k+1]*f
            rows.append(np.stack([a*(1-u)+b*u for u in np.linspace(0,1,cross_sections)]))
    rows.append(np.stack([left[-1]*(1-u)+right[-1]*u for u in np.linspace(0,1,cross_sections)]))
    flat=np.asarray(rows).reshape(-1,2)
    y=sample(h,flat[:,0],flat[:,1])+.12
    idx=[]
    for k in range(len(rows)-1):
        for col in range(cross_sections-1):
            a=k*cross_sections+col;b=a+cross_sections
            idx.extend([a,b,a+1,a+1,b,b+1])
    meshpos=np.column_stack((flat[:,0],y,flat[:,1]));tri=np.asarray(idx).reshape(-1,3)
    if np.cross(meshpos[tri[0,1]]-meshpos[tri[0,0]],meshpos[tri[0,2]]-meshpos[tri[0,0]])[1]<0:tri=tri[:,[0,2,1]]
    return surface(path,flat,tri,y,template)

def beach(path,t,template):
    axis=np.linspace(-1000,1000,513);x,z=np.meshgrid(axis,axis);flat=np.column_stack((x.ravel(),z.ravel()));y=sample(t.h,flat[:,0],flat[:,1])+.018
    coast=sample(t.coast,flat[:,0],flat[:,1]);cleared=sample(t.cleared.astype('f4'),flat[:,0],flat[:,1])
    mask=(coast<130)&(coast>50)&(y>SEA-.3)&(y<SEA+8)
    idx=[]
    for iz in range(512):
        row=iz*513
        for ix in range(512):
            a=row+ix;b=a+1;c=a+513;d=c+1
            if mask[[a,b,c,d]].all():idx.extend([a,c,b,b,c,d])
    if not idx:return None
    used,inverse=np.unique(np.asarray(idx),return_inverse=True)
    return surface(path,flat[used],inverse,y[used],template)

# The checked-in core shader is authoritative; regeneration cannot restore old lighting.
OCEAN_SHADER=(Path(__file__).resolve().parents[2]/'Assets/AarisWorld/Surfaces/CoastalWater.shader').read_text()

def ocean(folder,template):
    folder=Path(folder);p=folder/'CoastalWater.shader';p.write_text(OCEAN_SHADER);meta(p,kind='ShaderImporter')
    mat=material_asset(folder/'CoastalWater.mat','Coastal Water',base=(.03,.22,.28,1),smoothness=.82,shader=guid(p))
    axis=np.linspace(-6000,6000,129);x,z=np.meshgrid(axis,axis);flat=np.column_stack((x.ravel(),z.ravel()));idx=[]
    for iz in range(128):
        for ix in range(128):
            a=iz*129+ix;idx.extend([a,a+129,a+1,a+1,a+129,a+130])
    m=surface(folder/'Ocean.asset',flat,idx,np.full(len(flat),SEA),template)
    return m,mat

def port_dock(path,x0,x1,z,ground,template):
    positions=[];normals=[];uvs=[];indices=[]
    def box(center,size):
        c=np.array(center);s=np.array(size)/2
        corners=np.array([[-1,-1,-1],[-1,-1,1],[-1,1,-1],[-1,1,1],[1,-1,-1],[1,-1,1],[1,1,-1],[1,1,1]])*s+c
        for face,n in [([0,1,3,2],[-1,0,0]),([4,6,7,5],[1,0,0]),([0,4,5,1],[0,-1,0]),([2,3,7,6],[0,1,0]),([0,2,6,4],[0,0,-1]),([1,5,7,3],[0,0,1])]:
            p=corners[face];start=len(positions);tri=np.array([0,1,2,0,2,3]).reshape(-1,3)
            if np.dot(np.cross(p[1]-p[0],p[2]-p[0]),n)<0:tri=tri[:,[0,2,1]]
            positions.extend(p);normals.extend([n]*4);uvs.extend([[0,0],[0,2],[2,2],[2,0]]);indices.extend((tri+start).reshape(-1))
    # A 1:15 access ramp rises from the surrounding apron onto the original quay deck.
    ramp_x=np.array([[x0-8,z-4],[x0-8,z+4],[x0+10,z+4],[x0+10,z-4]])
    positions.extend(np.column_stack((ramp_x[:,0],[ground+.02,ground+.02,ground+1.2,ground+1.2],ramp_x[:,1])));normals.extend([[0,1,0]]*4);uvs.extend([[0,0],[0,2],[4,2],[4,0]]);indices.extend([0,1,2,0,2,3])
    box(((x0+10+x1)/2,ground+.8,z),(x1-x0-10,.8,8))
    box((x1-5,ground+.8,z),(10,.8,38))
    for x in np.arange(x0+14,x1,18):
        for zz in [z-3,z+3]:box((x,(ground+1.0+SEA-32)/2,zz),(1,ground+1.0-(SEA-32),1))
    for zz in [z-4,z+4]:
        box(((x0+12+x1-10)/2,ground+2.1,zz),(x1-10-x0-12,.12,.12))
        for x in np.arange(x0+12,x1-10,9):box((x,ground+1.65,zz),(.13,.9,.13))
    return mesh_asset(path,positions,normals,uvs,indices,template)
