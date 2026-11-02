"""Export a measured top-down review plan, explicitly not a Unity render."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap,LightSource
import numpy as np
from sculpt import SEA

def draw():
    d=json.loads(Path('Docs/MAP_LAYOUT.json').read_text());h=np.load('Tools/MapBuild/.build_geometry.npz')['height'][::4,::4]
    cmap=LinearSegmentedColormap.from_list('land',['#a5aa77','#829066','#627a52','#75826d','#b7b4a4'])
    colors=LightSource(315,45).shade(h,cmap,vert_exag=1.2,dx=2000/(len(h)-1),dy=2000/(len(h)-1),blend_mode='soft')
    colors[h<SEA]=[.09,.3,.37,1]
    fig,ax=plt.subplots(figsize=(12,13),facecolor='#10232a');ax.set_facecolor('#173c48')
    ax.imshow(colors,extent=(-1000,1000,-1000,1000),origin='lower')
    for road in d['roads']:
        p=np.array(road['points']);ax.plot(p[:,0],p[:,2],color='#e7c989',lw=2 if 'sites' in road else 1,alpha=.9,zorder=3)
    for b in d['buildings']:
        x,z,xx,zz=b['aabb_xz_m'];ax.add_patch(plt.Rectangle((x,z),xx-x,zz-z,facecolor='#e7e2d2',edgecolor='#273e44',lw=.4,zorder=5))
    for sp in d['vehicle_spawns']:
        x,y,z=sp['position_m'];a=np.radians(sp['yaw_degrees']);ax.arrow(x,z,4*np.sin(a),4*np.cos(a),color='#72e5d1',head_width=6,length_includes_head=True,zorder=6)
    for k,s in enumerate(d['districts'],1):
        name=''.join(' '+c if c.isupper() else c for c in s['name']).strip()
        ax.annotate(f'{k:02d}  {name}',(s['x'],s['z']),xytext=(0,45),textcoords='offset points',ha='center',fontsize=8,color='white',weight='bold',bbox={'facecolor':'#142b32','edgecolor':'#81a4a2','alpha':.9,'boxstyle':'round,pad=.35'},arrowprops={'arrowstyle':'-','color':'#c6dad4','lw':.7},zorder=7)
    ax.axhline(0,color='white',lw=.6,ls='--',alpha=.6);ax.axvline(0,color='white',lw=.6,ls='--',alpha=.6)
    for x,z,label in [(-960,-960,'1_1'),(-960,925,'1_2'),(905,-960,'2_1'),(905,925,'2_2')]:ax.text(x,z,label,color='#d4eeee',fontsize=11,weight='bold')
    ax.set_xlim(-1000,1000);ax.set_ylim(-1000,1000);ax.set_aspect('equal');ax.set_xticks(np.arange(-1000,1001,500));ax.set_yticks(np.arange(-1000,1001,500));ax.tick_params(colors='#bed0d0');ax.set_xlabel('World X / metres',color='#bed0d0');ax.set_ylabel('World Z / metres',color='#bed0d0')
    for spine in ax.spines.values():spine.set_color('#547578')
    fig.suptitle('AARIS  /  2 KM ISLAND',color='#eef7f4',fontsize=23,fontweight='bold',y=.96)
    fig.text(.5,.915,f'13 districts  •  {len(d["buildings"])} model instances  •  {len(d["vehicle_spawns"])} empty vehicle bays',ha='center',color='#a9ccc5',fontsize=11)
    fig.text(.5,.055,'Measured terrain and placement plan. This is not a Unity Editor render.',ha='center',color='#a9ccc5',fontsize=10)
    fig.text(.5,.035,'Gold: connected roads   |   White: model footprints   |   Cyan: vehicle exit direction',ha='center',color='#a9ccc5',fontsize=9)
    fig.subplots_adjust(top=.89,bottom=.1,left=.1,right=.95);fig.savefig('Docs/MAP_LAYOUT_2KM.png',dpi=180,facecolor=fig.get_facecolor());plt.close(fig)
if __name__=='__main__':draw()
