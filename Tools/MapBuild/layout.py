"""Spatial plan. Each coordinate is measured in Unity metres, world X/Z."""
import math,heapq
import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates
from sculpt import SEA,sample
# name, x, z, full width, full depth, focal model
SITES=[
 ('ClockTowerTown',350,220,190,170,'TownHall'),
 ('HighlandObservatory',570,-630,150,140,'observatory_dome'),
 ('EasternPort',840,350,130,160,'Harbour'),
 ('SouthernAirfield',180,-430,300,160,'Airfield'),
 ('FreightDistrict',550,-160,180,150,'ParcelDepot'),
 ('CanalMarket',-120,650,160,140,'CanalTown'),
 ('OldVillage',-530,-590,180,140,'HanokVillage'),
 ('LakesideHamlet',-720,65,130,110,'pitched_roof_cottage'),
 ('ValleySettlement',-420,-210,170,150,'row_three_townhouses'),
 ('NorthernRidgeTown',300,650,180,150,'detached_two_storey_house'),
 ('CoastalHamlet',650,650,150,140,'bungalow_house'),
 ('SoutheastLighthouse',825,-750,70,70,'lighthouse'),
 ('ForestLookout',-650,-125,70,70,'watchtower')]

def create_sites(t):
    sites=[]
    for name,x,z,w,d,model in SITES:
        xx,zz=np.meshgrid(np.linspace(x-w/2,x+w/2,11),np.linspace(z-d/2,z+d/2,11))
        y=float(np.percentile(sample(t.original,xx,zz),55))
        if name=='EasternPort':y=SEA+5
        y=max(y,SEA+7)
        if name=='SoutheastLighthouse':y=max(y,10)
        t.pad(x,z,w/2,d/2,y,blend=70)
        sites.append({'name':name,'x':x,'z':z,'width':w,'depth':d,'height':y,'focal_model':model,
                      'gate':([x-w/2-42,y,z-20] if x>750 else [x-w*.16,y,z-d/2-42]),'gate_side':'west' if x>750 else 'south'})
    return sites

def road_network(t,sites):
    # MST guarantees all districts connect; three cross-links avoid a single-route layout.
    xy=np.array([[s['x'],s['z']] for s in sites]);edges=[];visited={0}
    while len(visited)<len(sites):
        _,a,b=min((np.linalg.norm(xy[a]-xy[b]),a,b) for a in visited for b in range(len(sites)) if b not in visited)
        visited.add(b);edges.append((a,b))
    for a,b in [(0,4),(3,6),(5,9),(0,9)]:
        if (a,b) not in edges and (b,a) not in edges:edges.append((a,b))
    step=8;axis=np.arange(-960,961,step);xx,zz=np.meshgrid(axis,axis);hh=sample(t.h,xx,zz)
    gz,gx=np.gradient(hh,step);slope=np.hypot(gx,gz)
    block=np.zeros(hh.shape,bool)
    # Buildings occupy the interior. Gates and the southern service strip remain open.
    for s in sites:
        block|=(np.abs(xx-s['x'])<s['width']/2+32)&(zz>s['z']-s['depth']/2-32)&(zz<s['z']+s['depth']/2+32)
    # Preserve the authored glade/lake basin, not merely the camera transform.
    block|=((xx+240)/170)**2+((zz-230)/140)**2<1
    cost=1+3*slope+np.maximum(SEA+2-hh,0)*12
    cost[block]=np.inf
    def cell(p):return (int(round((p[2]+960)/step)),int(round((p[0]+960)/step)))
    roads=[]
    for a,b in edges:
        start=cell(sites[a]['gate']);end=cell(sites[b]['gate']);cost[start]=cost[end]=1
        dist={start:0};parent={};q=[(0,start)];found=False
        while q:
            _,cur=heapq.heappop(q)
            if cur==end:found=True;break
            cy,cx=cur
            for dy,dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                ny,nx=cy+dy,cx+dx
                if not (0<=ny<len(axis) and 0<=nx<len(axis)) or not np.isfinite(cost[ny,nx]):continue
                # A road remains on dry terrain. Water has a deliberate avoidance penalty.
                nd=dist[cur]+math.hypot(dy,dx)*(cost[ny,nx]+cost[cur])/2
                if nd<dist.get((ny,nx),1e30):
                    dist[ny,nx]=nd;parent[(ny,nx)]=cur;heur=math.hypot(end[0]-ny,end[1]-nx)
                    heapq.heappush(q,(nd+heur,(ny,nx)))
        assert found,(a,b,'No connected road route')
        pts=[end]
        while pts[-1]!=start:pts.append(parent[pts[-1]])
        pts=pts[::-1];xz=np.array([[axis[x],axis[z]] for z,x in pts],float)
        xz[0]=[sites[a]['gate'][0],sites[a]['gate'][2]];xz[-1]=[sites[b]['gate'][0],sites[b]['gate'][2]]
        # Slightly rounded turns, bounded to the routed corridor; endpoint positions are exact.
        if len(xz)>4:
            xz[1:-1]=gaussian_filter1d(xz,1,axis=0)[1:-1]
        yy=gaussian_filter1d(sample(t.h,xz[:,0],xz[:,1]),2)
        yy[0]=sites[a]['height'];yy[-1]=sites[b]['height']
        yy=np.maximum(yy,SEA+2.5)
        # Raise/depress approach grades iteratively while keeping both flat site gates fixed.
        length=np.linalg.norm(np.diff(xz,axis=0),axis=1)
        for _ in range(80):
            for k in range(1,len(yy)-1):yy[k]=np.clip(yy[k],yy[k-1]-.08*length[k-1],yy[k-1]+.08*length[k-1])
            for k in range(len(yy)-2,0,-1):yy[k]=np.clip(yy[k],yy[k+1]-.08*length[k],yy[k+1]+.08*length[k])
        p=np.column_stack((xz[:,0],yy,xz[:,1]));t.road(p)
        roads.append({'name':f'{sites[a]["name"]}__{sites[b]["name"]}','sites':[a,b],'points':p.tolist(),'width':8})
    return roads
