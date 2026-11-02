"""Author native Unity assets without an Editor-time map generator.

Meshes follow the original vendor's serializedVersion=10 Mesh fixture. GLB
geometry is transformed once into Unity's left-handed frame, with matching
winding, normals and texture coordinates. Nothing executes on scene load.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import math
import re
import struct
import uuid
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

NAMESPACE = uuid.UUID('e857c283-328d-4670-8f69-1aac8db83567')
LIT_SHADER = '933532a4fcc9baf4fa0491de14d08ed7'

def guid(path):
    path=str(path).replace('\\', '/')
    if '/Assets/' in path:path='Assets/'+path.split('/Assets/',1)[1]
    return uuid.uuid5(NAMESPACE, path).hex

class Flow(dict):
    pass

class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True

Dumper.add_representer(Flow, lambda d, x: d.represent_mapping('tag:yaml.org,2002:map', x, flow_style=True))

def ref(file_id=0, asset_guid=None, kind=2):
    r = Flow(fileID=int(file_id))
    if asset_guid:
        r.update(guid=asset_guid, type=kind)
    return r

def vec(x=0, y=0, z=0):
    return Flow(x=float(x), y=float(y), z=float(z))

def quat_y(degrees=0):
    a=math.radians(degrees)/2
    return Flow(x=0, y=math.sin(a), z=0, w=math.cos(a))

def color(r,g,b,a=1):
    return Flow(r=float(r), g=float(g), b=float(b), a=float(a))

def write_yaml(path, objects):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n'
    for cls, ident, name, data in objects:
        text += f'--- !u!{cls} &{ident}\n'
        text += yaml.dump({name:data}, Dumper=Dumper, sort_keys=False, width=1000, allow_unicode=True)
    path.write_text(text)

def meta(path, kind='NativeFormatImporter', main_id=0, texture=None):
    p=Path(path)
    data={'fileFormatVersion':2,'guid':guid(p.as_posix())}
    if texture:
        imp={'internalIDToNameTable':[], 'externalObjects':{}, 'serializedVersion':12,
             'mipmaps':{'mipMapMode':0,'enableMipMap':1,'sRGBTexture':0 if texture.get('linear') else 1,
                        'linearTexture':0,'fadeOut':0,'borderMipMap':0,'mipMapsPreserveCoverage':0,'alphaTestReferenceValue':0.5,'mipMapFadeDistanceStart':1,'mipMapFadeDistanceEnd':3},
             'bumpmap':{'convertToNormalMap':0,'externalNormalMap':0,'heightScale':0.25,'normalMapFilter':0,'flipGreenChannel':0},
             'isReadable':0,'streamingMipmaps':1,'streamingMipmapsPriority':0,'vTOnly':0,'ignoreMipmapLimit':0,
             'grayScaleToAlpha':0,'generateCubemap':6,'cubemapConvolution':0,'seamlessCubemap':0,
             'textureFormat':1,'maxTextureSize':2048,'textureSettings':{'serializedVersion':2,'filterMode':2,'aniso':4,'mipBias':0,'wrapU':0,'wrapV':0,'wrapW':0},
             'nPOTScale':0,'lightmap':0,'compressionQuality':75,'spriteMode':0,'spriteExtrude':1,'spriteMeshType':1,
             'alignment':0,'spritePivot':Flow(x=0.5,y=0.5),'spritePixelsToUnits':100,'spriteBorder':Flow(x=0,y=0,z=0,w=0),
             'spriteGenerateFallbackPhysicsShape':1,'alphaUsage':1,'alphaIsTransparency':0,
             'textureType':1 if texture.get('normal') else 0,'textureShape':1,'singleChannelComponent':0,
             'flipbookRows':1,'flipbookColumns':1,
             'platformSettings':[{'serializedVersion':3,'buildTarget':'DefaultTexturePlatform','maxTextureSize':2048,'resizeAlgorithm':0,'textureFormat':-1,'textureCompression':1,'compressionQuality':75,'crunchedCompression':0,'allowsAlphaSplitting':0,'overridden':0,'ignorePlatformSupport':0,'androidETC2FallbackOverride':0,'forceMaximumCompressionQuality_BC6H_BC7':0},
                                 {'serializedVersion':3,'buildTarget':'Android','maxTextureSize':1024,'resizeAlgorithm':0,'textureFormat':-1,'textureCompression':1,'compressionQuality':75,'crunchedCompression':0,'allowsAlphaSplitting':0,'overridden':1,'ignorePlatformSupport':0,'androidETC2FallbackOverride':0,'forceMaximumCompressionQuality_BC6H_BC7':0}],
             'userData':'','assetBundleName':'','assetBundleVariant':''}
        data['TextureImporter']=imp
    elif kind=='folder':
        data['folderAsset']='yes'
        data['DefaultImporter']={'externalObjects':{},'userData':'','assetBundleName':'','assetBundleVariant':''}
    else:
        data[kind]={'externalObjects':{},'mainObjectFileID':main_id,'userData':'','assetBundleName':'','assetBundleVariant':''}
        if kind in ('PrefabImporter','ShaderImporter','DefaultImporter'):
            data[kind].pop('mainObjectFileID',None)
    Path(str(p)+'.meta').write_text(yaml.dump(data,Dumper=Dumper,sort_keys=False))
    return data['guid']

def aabb(pos):
    lo=np.min(pos,axis=0);hi=np.max(pos,axis=0)
    return {'m_Center':vec(*((lo+hi)*.5)), 'm_Extent':vec(*((hi-lo)*.5))}

def mesh_asset(path, pos, normal, uv, indices, template, name=None, tangent=None, groups=None):
    pos=np.asarray(pos,dtype='<f4');normal=np.asarray(normal,dtype='<f4');uv=np.asarray(uv,dtype='<f4')
    indices=np.asarray(indices,dtype='<u4').reshape(-1)
    assert len(pos)>0 and len(pos)==len(normal)==len(uv) and indices.max()<len(pos) and len(indices)%3==0
    assert np.isfinite(pos).all() and np.isfinite(normal).all() and np.isfinite(uv).all()
    if tangent is None:
        tangent=calculate_tangents(pos,normal,uv,indices)
    vertices=np.concatenate((pos,normal,np.asarray(tangent,dtype='<f4'),uv),axis=1).astype('<f4')
    assert vertices.shape[1]==12
    text=template
    text=re.sub(r'(?m)^  m_Name:.*$', '  m_Name: '+(name or Path(path).stem),text)
    groups=groups or [(0,len(indices))]
    subs=[]
    for first,count in groups:
        used=indices[first:first+count]
        subs.append({'serializedVersion':2,'firstByte':first*4,'indexCount':count,'topology':0,'baseVertex':0,
                     'firstVertex':int(used.min()),'vertexCount':int(used.max()-used.min()+1),'localAABB':aabb(pos[used])})
    block=yaml.dump({'m_SubMeshes':subs},Dumper=Dumper,sort_keys=False,width=1000)
    block='\n'.join('  '+line for line in block.rstrip().splitlines())+'\n'
    text=re.sub(r'(?ms)^  m_SubMeshes:.*?(?=^  m_Shapes:)',block,text)
    text=re.sub(r'(?m)^  m_IsReadable:.*$', '  m_IsReadable: 1',text)
    text=re.sub(r'(?m)^  m_IndexFormat:.*$', '  m_IndexFormat: 1',text)
    text=re.sub(r'(?m)^  m_IndexBuffer:.*$', '  m_IndexBuffer: '+indices.tobytes().hex(),text)
    channels=[]
    for i in range(14):
        off,dim={0:(0,3),1:(12,3),2:(24,4),4:(40,2)}.get(i,(0,0))
        channels.append({'stream':0,'offset':off,'format':0,'dimension':dim})
    vblock=yaml.dump({'m_VertexData':{'serializedVersion':3,'m_VertexCount':len(pos),'m_Channels':channels,'m_DataSize':vertices.nbytes}},Dumper=Dumper,sort_keys=False)
    vblock='\n'.join('  '+line for line in vblock.rstrip().splitlines())+'\n    _typelessdata: '+vertices.tobytes().hex()+'\n'
    text=re.sub(r'(?ms)^  m_VertexData:.*?(?=^  m_CompressedMesh:)',vblock,text)
    bounds=yaml.dump({'m_LocalAABB':aabb(pos)},Dumper=Dumper,sort_keys=False)
    bounds='\n'.join('  '+line for line in bounds.rstrip().splitlines())+'\n'
    text=re.sub(r'(?ms)^  m_LocalAABB:.*?(?=^  m_MeshUsageFlags:)',bounds,text)
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(text)
    meta(path,main_id=4300000)
    return {'guid':guid(path),'bounds':aabb(pos),'triangles':len(indices)//3,'vertices':len(pos),'submeshes':len(groups)}

def calculate_tangents(pos, normals, uv, inds):
    tri=inds.reshape(-1,3);a,b,c=tri.T
    e1=pos[b]-pos[a];e2=pos[c]-pos[a];d1=uv[b]-uv[a];d2=uv[c]-uv[a]
    det=d1[:,0]*d2[:,1]-d1[:,1]*d2[:,0]
    r=np.divide(1,det,out=np.zeros_like(det),where=np.abs(det)>1e-10)
    s=(e1*d2[:,1,None]-e2*d1[:,1,None])*r[:,None]
    t=(e2*d1[:,0,None]-e1*d2[:,0,None])*r[:,None]
    st=np.zeros_like(pos);bt=np.zeros_like(pos)
    for ids in (a,b,c):np.add.at(st,ids,s);np.add.at(bt,ids,t)
    st-=normals*np.sum(normals*st,axis=1)[:,None]
    leng=np.linalg.norm(st,axis=1);bad=leng<1e-9
    st[bad]=np.cross(normals[bad],np.array([0,0,1],dtype='f4'))
    bad2=np.linalg.norm(st,axis=1)<1e-9;st[bad2]=[1,0,0]
    st/=np.maximum(np.linalg.norm(st,axis=1)[:,None],1e-10)
    w=np.where(np.sum(np.cross(normals,st)*bt,axis=1)<0,-1,1)
    return np.column_stack((st,w)).astype('<f4')

class Glb:
    FILTER=re.compile(r'(^|[-_/ ])(van|truck|jeep|buggy|car|vehicle|sedan|suv|quad|bike|tug|helicopter|trailer|pickup|lorry|forklift|boat|barge|brig|sloop|ship|ships|punt|binnacle|figurehead|stern-lantern|swivel-gun|admiralty-anchor|carved-figurehead|deck-capstan|deck-hatch|cannon|rifle|pistol|weapon|operator|soldier|parachute|loot|ammunition|ammo|munitions)([-_/ ]|$)',re.I)
    def __init__(self,path):
        self.path=Path(path);raw=self.path.read_bytes()
        assert raw[:4]==b'glTF' and struct.unpack_from('<I',raw,8)[0]==len(raw)
        off=12;self.bin=b''
        while off<len(raw):
            size,kind=struct.unpack_from('<II',raw,off);off+=8
            if kind==0x4e4f534a:self.g=json.loads(raw[off:off+size])
            elif kind==0x004e4942:self.bin=raw[off:off+size]
            off+=size
        assert not any('uri' in b for b in self.g.get('buffers',[]))
        self.removed_nodes=[]
    def accessor(self,i):
        a=self.g['accessors'][i];assert 'sparse' not in a
        bv=self.g['bufferViews'][a['bufferView']]
        dtype={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];dt=np.dtype(dtype)
        start=bv.get('byteOffset',0)+a.get('byteOffset',0);stride=bv.get('byteStride',width*dt.itemsize)
        arr=np.ndarray((a['count'],width),dtype=dt,buffer=self.bin,offset=start,strides=(stride,dt.itemsize)).copy()
        if a.get('normalized') and a['componentType']!=5126:
            denom={5120:127,5121:255,5122:32767,5123:65535}[a['componentType']]
            arr=np.maximum(arr.astype('f4')/denom,-1)
        return arr
    @staticmethod
    def matrix(n):
        if 'matrix' in n:return np.asarray(n['matrix'],float).reshape(4,4,order='F')
        x,y,z,w=n.get('rotation',[0,0,0,1]);m=np.eye(4)
        m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(n.get('scale',[1,1,1]))
        m[:3,3]=n.get('translation',[0,0,0]);return m
    def geometry(self):
        groups=defaultdict(list);flip=np.diag([1,1,-1,1])
        def walk(i,parent,path):
            n=self.g['nodes'][i];name=n.get('name','node_'+str(i));path=path+'/'+name
            if self.FILTER.search(name) and not re.search(r'garage|house|warehouse|carport',name,re.I):self.removed_nodes.append(path);return
            m=parent@self.matrix(n);tm=flip@m
            if 'mesh' in n:
                normalmat=np.linalg.inv(tm[:3,:3]).T
                for pr in self.g['meshes'][n['mesh']]['primitives']:
                    assert pr.get('mode',4)==4,'Only triangle primitives are supported'
                    at=pr['attributes'];p=self.accessor(at['POSITION']).astype('f4')
                    pp=(tm@np.column_stack((p,np.ones(len(p)))).T).T[:,:3]
                    idx=self.accessor(pr['indices']).reshape(-1).astype('u4') if 'indices' in pr else np.arange(len(p),dtype='u4')
                    idx=idx.reshape(-1,3)
                    if np.linalg.det(tm[:3,:3])<0:idx=idx[:,[0,2,1]]
                    if 'NORMAL' in at:
                        nn=(normalmat@self.accessor(at['NORMAL']).T).T
                        nn/=np.maximum(np.linalg.norm(nn,axis=1)[:,None],1e-10)
                    else:
                        nn=np.zeros_like(pp);tr=idx;cross=np.cross(pp[tr[:,1]]-pp[tr[:,0]],pp[tr[:,2]]-pp[tr[:,0]])
                        for inds in tr.T:np.add.at(nn,inds,cross)
                        nn/=np.maximum(np.linalg.norm(nn,axis=1)[:,None],1e-10)
                    if 'TEXCOORD_0' in at:
                        uv=self.accessor(at['TEXCOORD_0']).astype('f4');uv[:,1]=1-uv[:,1]
                    else:
                        # World-scale box projection for the untextured modular kit.
                        axis=np.argmax(np.abs(nn),axis=1);uv=np.zeros((len(pp),2),dtype='f4')
                        uv[axis==0]=pp[axis==0][:,[2,1]]/2
                        uv[axis==1]=pp[axis==1][:,[0,2]]/2
                        uv[axis==2]=pp[axis==2][:,[0,1]]/2
                    groups[pr.get('material',-1)].append((pp,nn,uv,idx.reshape(-1)))
            for c in n.get('children',[]):walk(c,m,path)
        for i in self.g['scenes'][self.g.get('scene',0)]['nodes']:walk(i,np.eye(4),'')
        all_p=[];all_n=[];all_uv=[];all_idx=[];runs=[];mats=[];nv=0;ni=0
        for material,parts in sorted(groups.items()):
            count=0
            for p,n,u,idx in parts:
                all_p.append(p);all_n.append(n);all_uv.append(u);all_idx.append(idx+nv);nv+=len(p);count+=len(idx)
            runs.append((ni,count));ni+=count;mats.append(material)
        pos=np.concatenate(all_p);lo=pos.min(0);hi=pos.max(0)
        pivot=np.array([(lo[0]+hi[0])/2,lo[1],(lo[2]+hi[2])/2]);pos-=pivot
        return pos,np.concatenate(all_n),np.concatenate(all_uv),np.concatenate(all_idx),runs,mats,pivot
    def image(self,index):
        im=self.g['images'][index];assert 'bufferView' in im
        bv=self.g['bufferViews'][im['bufferView']];a=bv.get('byteOffset',0)
        return Image.open(BytesIO(self.bin[a:a+bv['byteLength']])).copy()

def material_asset(path,name,base=(.6,.6,.6,1),metallic=0,smoothness=.3,textures=None,transparent=False,shader=None,extra=None):
    tex=[]
    for key,value in (textures or {}).items():
        tex.append({key:{'m_Texture':ref(2800000,value,3),'m_Scale':Flow(x=1,y=1),'m_Offset':Flow(x=0,y=0)}})
    floats={'_Metallic':float(metallic),'_Smoothness':float(smoothness),'_BumpScale':1,'_OcclusionStrength':1,'_Cull':0,
            '_Surface':1 if transparent else 0,'_Blend':0,'_AlphaClip':0,'_Cutoff':.5,'_SrcBlend':5 if transparent else 1,
            '_DstBlend':10 if transparent else 0,'_ZWrite':0 if transparent else 1,'_ReceiveShadows':1,'_WorkflowMode':1}
    floats.update(extra or {})
    keywords=[]
    if textures and '_BumpMap' in textures:keywords.append('_NORMALMAP')
    if textures and '_MetallicGlossMap' in textures:keywords.append('_METALLICSPECGLOSSMAP')
    if textures and '_OcclusionMap' in textures:keywords.append('_OCCLUSIONMAP')
    if transparent:keywords+=['_SURFACE_TYPE_TRANSPARENT']
    if floats.get('_AlphaClip'):keywords+=['_ALPHATEST_ON']
    data={'serializedVersion':8,'m_ObjectHideFlags':0,'m_CorrespondingSourceObject':ref(),'m_PrefabInstance':ref(),'m_PrefabAsset':ref(),
          'm_Name':name,'m_Shader':ref(4800000,shader or LIT_SHADER,3),'m_Parent':ref(),'m_ModifiedSerializedProperties':0,
          'm_ValidKeywords':keywords,'m_InvalidKeywords':[],'m_LightmapFlags':4,'m_EnableInstancingVariants':1,
          'm_DoubleSidedGI':1,'m_CustomRenderQueue':3000 if transparent else -1,'stringTagMap':{'RenderType':'Transparent'} if transparent else {},
          'disabledShaderPasses':[],'m_LockedProperties':'','m_SavedProperties':{'serializedVersion':3,'m_TexEnvs':tex,'m_Ints':[],
          'm_Floats':[{k:v} for k,v in floats.items()],'m_Colors':[{'_BaseColor':color(*base)},{'_Color':color(*base)},{'_EmissionColor':color(0,0,0)}]},'m_BuildTextureStacks':[]}
    write_yaml(path,[(21,2100000,'Material',data)]);meta(path,main_id=2100000)
    return guid(path)

def export_model(source,path,template,shared=None,reuse_images=False):
    """Extract images and author one native, material-grouped static prefab."""
    source=Path(source);path=Path(path);path.mkdir(parents=True,exist_ok=True)
    glb=Glb(source)
    pos,norm,uv,inds,runs,mat_indices,pivot=glb.geometry()
    mesh=mesh_asset(path/'Geometry.asset',pos,norm,uv,inds,template,name=path.name,groups=runs)
    images={};materials=[]
    def image_for_texture(texture_index,kind='color',roughness=1,metallic=1):
        tx=glb.g['textures'][texture_index]
        source_index=tx.get('source',tx.get('extensions',{}).get('EXT_texture_webp',{}).get('source'))
        assert source_index is not None,'Unsupported texture encoding'
        key=(source_index,kind,roughness,metallic) if kind=='metallic' else (source_index,kind)
        if key not in images:
            img=glb.image(source_index).convert('RGBA')
            if kind=='metallic':
                a=np.asarray(img);dst=np.zeros_like(a);dst[:,:,0]=np.rint(a[:,:,2]*metallic);dst[:,:,3]=np.rint(255-a[:,:,1]*roughness);img=Image.fromarray(dst)
            filename=path/(f'Image_{source_index:02d}_{kind}'+(f'_{roughness}_{metallic}' if kind=='metallic' else '')+'.png')
            if not (reuse_images and filename.exists()):img.save(filename)
            meta(filename,texture={'normal':kind=='normal','linear':kind in ('normal','metallic','occlusion')})
            images[key]=guid(filename)
        return images[key]
    for index in mat_indices:
        material=glb.g.get('materials',[])[index] if index>=0 else {}
        name=material.get('name','Default');pbr=material.get('pbrMetallicRoughness',{})
        base=pbr.get('baseColorFactor',[1,1,1,1]);textures={};smooth=1-pbr.get('roughnessFactor',1)
        if 'baseColorTexture' in pbr:textures['_BaseMap']=image_for_texture(pbr['baseColorTexture']['index'])
        if 'metallicRoughnessTexture' in pbr:textures['_MetallicGlossMap']=image_for_texture(pbr['metallicRoughnessTexture']['index'],'metallic',pbr.get('roughnessFactor',1),pbr.get('metallicFactor',1));smooth=1
        if 'normalTexture' in material:textures['_BumpMap']=image_for_texture(material['normalTexture']['index'],'normal')
        if 'occlusionTexture' in material:textures['_OcclusionMap']=image_for_texture(material['occlusionTexture']['index'],'occlusion')
        if '_BaseMap' not in textures and shared:
            key='wood' if re.search('wood|timber|oak|thatch',name,re.I) else 'stone' if re.search('stone|brick|clay|plaster|tile',name,re.I) else None
            if key and key in shared:
                textures['_BaseMap']=shared[key]['color']
                if shared[key].get('normal'):textures['_BumpMap']=shared[key]['normal']
                # Retain authored material palette, with less extreme saturation.
                rgb=np.asarray(base[:3]);grey=float(np.mean(rgb));base=[*np.clip(.8*rgb+.2*grey,.12,.95).tolist(),base[3]]
        transparent=material.get('alphaMode')=='BLEND'
        g=material_asset(path/f'Material_{index:02d}.mat',path.name+'_'+name,base=base,
                         metallic=pbr.get('metallicFactor',1),smoothness=smooth,textures=textures,
                         transparent=transparent,extra={'_AlphaClip':1 if material.get('alphaMode')=='MASK' else 0,'_Cutoff':material.get('alphaCutoff',.5)})
        materials.append(g)
    from native_scene import Scene
    scene=Scene();scene.model(path.name,mesh['guid'],materials,bounds=mesh['bounds'])
    scene.save(path/(path.name+'.prefab'),prefab=True)
    dims=2*np.asarray(list(mesh['bounds']['m_Extent'].values()))
    return {**mesh,'materials':materials,'dimensions_m':dims.tolist(),'source_pivot':pivot.tolist(),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'excluded_source_nodes':glb.removed_nodes,
            'prefab':str(path/(path.name+'.prefab'))}
