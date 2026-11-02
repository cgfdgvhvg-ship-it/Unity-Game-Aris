"""Deterministic, spatially bounded edits to the four original TerrainData assets."""
import copy,math,re
from pathlib import Path
import numpy as np
import UnityPy
from scipy.ndimage import map_coordinates, minimum_filter, maximum_filter
SEA=-38.07552
BASE=-120.
STEP=1000/2048
KEEP=('1_1','1_2','2_1','2_2')
SOURCE_HASHES={'1_1':'006baa9c49f139f69829b1be9cb4e91d5987bd7981c41af16797e2da4d80cfe1','1_2':'7bc10da593317a896dfdf5ac3a4aa55f84e0707b335e0c843c76d8fba963bb64',
'2_1':'013ac672397ce93597189e27e4dff11a7f07933f68a0319d67cdd9d9e2768db0','2_2':'3976c773661af5af3e182c601f1f6e438db666400a6b45a43c7b0a8c02b6ea8e'}

def sample(h,x,z):
    xx,zz=np.broadcast_arrays(np.asarray(x),np.asarray(z));shape=xx.shape
    value=map_coordinates(h,[(zz.ravel()+1000)/STEP,(xx.ravel()+1000)/STEP],order=1,mode='nearest')
    return value.reshape(shape) if shape else float(value[0])
def smooth(t):
    t=np.clip(t,0,1);return t*t*(3-2*t)
class Terrain:
    def __init__(self,folder):
        self.folder=Path(folder);self.sources={};self.data={};self.env={};self.h=np.empty((4097,4097),np.float32)
        for tag in KEEP:
            p=next(p for p in self.folder.glob(f'Terrain_{tag}_*.asset') if not p.stem.endswith(' 1'))
            import hashlib
            assert hashlib.sha256(p.read_bytes()).hexdigest()==SOURCE_HASHES[tag],str(p)+' must be the original source TerrainData'
            e=UnityPy.load(str(p));o=next(x for x in e.objects if x.type.name=='TerrainData');d=o.parse_as_dict()
            self.sources[tag]=p;self.env[tag]=(e,o);self.data[tag]=d
            a=np.asarray(d['m_Heightmap']['m_Heights'],np.float32).reshape(2049,2049)/32766*800-40
            i,j=map(int,tag.split('_'));self.h[(j-1)*2048:(j-1)*2048+2049,(i-1)*2048:(i-1)*2048+2049]=a
        self.original=self.h.copy();self.cleared=np.zeros(self.h.shape,bool);self.coast=None
    def coast_sculpt(self):
        axis=np.linspace(-1000,1000,4097,dtype='f4');x=axis[None,:];z=axis[:,None]
        # Rounded rectangle: original land survives in the interior, all corners are offshore.
        qx=np.abs(x)-810;qz=np.abs(z)-810
        sd=np.hypot(np.maximum(qx,0),np.maximum(qz,0))+np.minimum(np.maximum(qx,qz),0)-190
        inland=-sd;self.coast=inland
        t=smooth((inland-25)/180)
        # No coastal spikes or open vertical Terrain edges: boundary is 24m below sea.
        beach=SEA-24+np.clip(inland/80,0,1)*27
        self.h[:]=beach*(1-t)+self.h*t
        self.cleared|=inland<185
    def region(self,x,z,hx,hz,pad=0):
        x0=max(0,int(math.floor((x-hx-pad+1000)/STEP)));x1=min(4097,int(math.ceil((x+hx+pad+1000)/STEP))+1)
        z0=max(0,int(math.floor((z-hz-pad+1000)/STEP)));z1=min(4097,int(math.ceil((z+hz+pad+1000)/STEP))+1)
        xx=np.arange(x0,x1)*STEP-1000;zz=np.arange(z0,z1)*STEP-1000
        return (slice(z0,z1),slice(x0,x1)),xx[None,:],zz[:,None]
    def pad(self,x,z,hx,hz,y,blend=18):
        sl,xx,zz=self.region(x,z,hx,hz,blend)
        dist=np.hypot(np.maximum(np.abs(xx-x)-hx,0),np.maximum(np.abs(zz-z)-hz,0))
        weight=1-smooth(dist/blend)
        self.h[sl]=self.h[sl]*(1-weight)+float(y)*weight
        self.cleared[sl]|=dist<blend*.75
    def road(self,points,width=8,shoulder=5):
        # Each segment blends onto one continuous, graded centerline.
        for a,b in zip(points[:-1],points[1:]):
            a=np.asarray(a);b=np.asarray(b);xz=b[[0,2]]-a[[0,2]];length2=float(xz@xz)
            if length2<1e-8:continue
            sl,xx,zz=self.region((a[0]+b[0])/2,(a[2]+b[2])/2,abs(xz[0])/2,abs(xz[1])/2,width+shoulder)
            t=np.clip(((xx-a[0])*xz[0]+(zz-a[2])*xz[1])/length2,0,1)
            dist=np.hypot(xx-(a[0]+t*xz[0]),zz-(a[2]+t*xz[1]))
            w=1-smooth((dist-width/2)/shoulder)
            target=a[1]+t*(b[1]-a[1]);self.h[sl]=self.h[sl]*(1-w)+target*w
            self.cleared[sl]|=dist<width/2+shoulder
    def quantize(self):
        self.raw=np.rint(np.clip((self.h-BASE)/800,0,1)*32766).astype(np.int16)
        self.h=self.raw.astype('f4')/32766*800+BASE
    def save(self):
        reports=[]
        for tag in KEEP:
            i,j=map(int,tag.split('_'));sl=(slice((j-1)*2048,(j-1)*2048+2049),slice((i-1)*2048,(i-1)*2048+2049))
            d=self.data[tag];hm=d['m_Heightmap'];raw=self.raw[sl];h=self.h[sl]
            hm['m_Heights']=raw.reshape(-1).tolist()
            # Vendor quadtree is bottom-up, row-major: 128² leaves through 1 root.
            norm=raw.astype('f4')/32766;bounds=[];errors=[]
            for stride in (16,32,64,128,256,512,1024,2048):
                lo=[];hi=[];err=[]
                for iz in range(0,2048,stride):
                    for ix in range(0,2048,stride):
                        q=norm[iz:iz+stride+1,ix:ix+stride+1];lo.append(float(q.min()));hi.append(float(q.max()))
                        if stride==16:err.append(0.)
                        else:
                            t=np.linspace(0,1,stride+1,dtype='f4');lerp=(q[0,0]*(1-t)+q[0,-1]*t)[None,:]*(1-t[:,None])+(q[-1,0]*(1-t)+q[-1,-1]*t)[None,:]*t[:,None]
                            err.append(float(np.max(np.abs(q-lerp))))
                bounds.extend(np.column_stack((lo,hi)).reshape(-1).tolist());errors.extend(err)
            assert len(bounds)==len(hm['m_MinMaxPatchHeights']) and len(errors)==len(hm['m_PrecomputedError'])
            hm['m_MinMaxPatchHeights']=bounds;hm['m_PrecomputedError']=errors
            db=d['m_DetailDatabase'];trees=[];removed=0
            for instance in db['m_TreeInstances']:
                p=instance['position'];x=(i-2)*1000+p['x']*1000;z=(j-2)*1000+p['z']*1000
                ix=int(round((x+1000)/STEP));iz=int(round((z+1000)/STEP));y=float(sample(self.h,x,z))
                if self.cleared[iz,ix] or y<SEA+1:removed+=1;continue
                p['y']=(y-BASE)/800;trees.append(instance)
            db['m_TreeInstances']=trees
            # Clear entire 15.625m density patches intersecting cleared surfaces.
            # This is deliberately conservative at roads and foundations.
            clear=maximum_filter(self.cleared[sl],size=65)[16::32,16::32]
            assert clear.shape==(64,64)
            n=0
            for idx,patch in enumerate(db['m_Patches']):
                if clear[idx//64,idx%64]:patch['layerIndices']=[];patch['numberOfObjects']=[];n+=1
            e,o=self.env[tag];o.patch(d);self.sources[tag].write_bytes(o.assets_file.save())
            reports.append({'tile':tag,'origin_m':[(i-2)*1000,BASE,(j-2)*1000],'size_m':[1000,800,1000],
                            'remaining_terrain_instances':len(trees),'removed_terrain_instances':removed,'cleared_detail_patches':n})
        return reports
