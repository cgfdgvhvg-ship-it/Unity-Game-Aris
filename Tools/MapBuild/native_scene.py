"""Small, explicit writer for saved Unity Scene/prefab objects."""
import copy
import math
from pathlib import Path
from native_assets import Flow, ref, vec, quat_y, color, write_yaml, meta, guid

class Scene:
    def __init__(self):
        self.objects=[];self.transforms={};self.next_id=10000;self.renderers=[]
    def object(self,name,position=(0,0,0),yaw=0,parent=0,scale=(1,1,1),static=True):
        go=self.next_id;tr=go+1;self.next_id+=10
        gd={'m_ObjectHideFlags':0,'m_CorrespondingSourceObject':ref(),'m_PrefabInstance':ref(),'m_PrefabAsset':ref(),
            'serializedVersion':6,'m_Component':[{'component':ref(tr)}],'m_Layer':0,'m_Name':name,'m_TagString':'Untagged',
            'm_Icon':ref(),'m_NavMeshLayer':0,'m_StaticEditorFlags':12 if static else 0,'m_IsActive':1}
        td={'m_ObjectHideFlags':0,'m_CorrespondingSourceObject':ref(),'m_PrefabInstance':ref(),'m_PrefabAsset':ref(),
            'm_GameObject':ref(go),'serializedVersion':2,'m_LocalRotation':quat_y(yaw),'m_LocalPosition':vec(*position),
            'm_LocalScale':vec(*scale),'m_ConstrainProportionsScale':0,'m_Children':[],'m_Father':ref(parent),'m_LocalEulerAnglesHint':vec(0,yaw,0)}
        self.objects.extend([(1,go,'GameObject',gd),(4,tr,'Transform',td)])
        self.transforms[tr]=td
        if parent:self.transforms[parent]['m_Children'].append(ref(tr))
        return go,tr,gd
    def component(self,go,gd,cls,name,fields):
        ident=self.next_id;self.next_id+=1
        data={'m_ObjectHideFlags':0,'m_CorrespondingSourceObject':ref(),'m_PrefabInstance':ref(),'m_PrefabAsset':ref(),'m_GameObject':ref(go)}
        data.update(fields);gd['m_Component'].append({'component':ref(ident)})
        self.objects.append((cls,ident,name,data));return ident
    def model(self,name,mesh_guid,materials,position=(0,0,0),yaw=0,parent=0,collider=True,bounds=None,lod=True):
        go,tr,gd=self.object(name,position,yaw,parent)
        self.component(go,gd,33,'MeshFilter',{'m_Mesh':ref(4300000,mesh_guid)})
        renderer=self.component(go,gd,23,'MeshRenderer',{
            'm_Enabled':1,'m_CastShadows':1,'m_ReceiveShadows':1,'m_DynamicOccludee':1,'m_StaticShadowCaster':0,
            'm_MotionVectors':1,'m_LightProbeUsage':1,'m_ReflectionProbeUsage':1,'m_RayTracingMode':2,'m_RayTraceProcedural':0,
            'm_RenderingLayerMask':1,'m_RendererPriority':0,'m_Materials':[ref(2100000,g) for g in materials],
            'm_StaticBatchInfo':{'firstSubMesh':0,'subMeshCount':0},'m_StaticBatchRoot':ref(),'m_ProbeAnchor':ref(),
            'm_LightProbeVolumeOverride':ref(),'m_ScaleInLightmap':1,'m_ReceiveGI':2,'m_PreserveUVs':0,
            'm_IgnoreNormalsForChartDetection':0,'m_ImportantGI':0,'m_StitchLightmapSeams':1,'m_SelectedEditorRenderState':3,
            'm_MinimumChartSize':4,'m_AutoUVMaxDistance':0.5,'m_AutoUVMaxAngle':89,'m_LightmapParameters':ref(),
            'm_SortingLayerID':0,'m_SortingLayer':0,'m_SortingOrder':0,'m_AdditionalVertexStreams':ref()})
        self.renderers.append(renderer)
        if collider:
            self.component(go,gd,64,'MeshCollider',{'m_Material':ref(),'m_IncludeLayers':{'serializedVersion':2,'m_Bits':0},
                'm_ExcludeLayers':{'serializedVersion':2,'m_Bits':0},'m_LayerOverridePriority':0,'m_IsTrigger':0,'m_ProvidesContacts':0,
                'm_Enabled':1,'serializedVersion':5,'m_Convex':0,'m_CookingOptions':30,'m_Mesh':ref(4300000,mesh_guid)})
        if lod and bounds:
            ext=bounds['m_Extent'];size=2*max(ext.values())
            self.component(go,gd,205,'LODGroup',{'serializedVersion':2,'m_LocalReferencePoint':bounds['m_Center'],'m_Size':size,
                'm_FadeMode':1,'m_AnimateCrossFading':1,'m_LastLODIsBillboard':0,
                'm_LODs':[{'screenRelativeHeight':0.012,'fadeTransitionWidth':0.15,'renderers':[{'renderer':ref(renderer)}]}],
                'm_Enabled':1})
        return go,tr
    def terrain(self,name,data_guid,position,terrain_template,parent=0):
        go,tr,gd=self.object(name,position,parent=parent)
        fields=copy.deepcopy(terrain_template)
        for k in ('m_ObjectHideFlags','m_CorrespondingSourceObject','m_PrefabInstance','m_PrefabAsset','m_GameObject'):fields.pop(k,None)
        fields['m_TerrainData']=ref(15600000,data_guid)
        fields.update(m_AllowAutoConnect=1,m_GroupingID=0,m_DrawInstanced=1,m_TreeDistance=600,m_TreeBillboardDistance=100,
                      m_TreeCrossFadeLength=25,m_DetailObjectDistance=100,m_DetailObjectDensity=.65,m_CastShadows=1)
        self.component(go,gd,218,'Terrain',fields)
        self.component(go,gd,154,'TerrainCollider',{'m_Material':ref(),'m_IncludeLayers':{'serializedVersion':2,'m_Bits':0},
            'm_ExcludeLayers':{'serializedVersion':2,'m_Bits':0},'m_LayerOverridePriority':0,'m_IsTrigger':0,
            'm_ProvidesContacts':0,'m_Enabled':1,'serializedVersion':3,'m_TerrainData':ref(15600000,data_guid),'m_EnableTreeColliders':1})
    def environment(self,render_settings):
        rs=copy.deepcopy(render_settings);rs.update(m_Fog=1,m_FogMode=3,m_FogDensity=.00018,m_LinearFogStart=650,m_LinearFogEnd=4000,
            m_AmbientIntensity=1,m_ReflectionIntensity=.8,m_CustomReflection=ref(),m_Sun=ref())
        rs['m_FogColor']=color(.69,.79,.84,1)
        self.objects.insert(0,(104,2,'RenderSettings',rs))
        go,tr,gd=self.object('Sun',position=(0,300,0),static=False)
        # 50 degree elevation, 35 degree azimuth.
        self.transforms[tr]['m_LocalRotation']=Flow(x=.402,y=.273,z=-.127,w=.865)
        light=self.component(go,gd,108,'Light',{'m_Enabled':1,'serializedVersion':11,'m_Type':1,'m_Shape':0,
            'm_Color':color(1,.955,.86),'m_Intensity':1.4,'m_Range':10,'m_SpotAngle':30,'m_InnerSpotAngle':21.8,'m_CookieSize':10,
            'm_Shadows':{'m_Type':2,'m_Resolution':-1,'m_CustomResolution':-1,'m_Strength':.8,'m_Bias':.05,'m_NormalBias':.25,
                         'm_NearPlane':.2,'m_CullingMatrixOverride':{'e00':1,'e01':0,'e02':0,'e03':0,'e10':0,'e11':1,'e12':0,'e13':0,'e20':0,'e21':0,'e22':1,'e23':0,'e30':0,'e31':0,'e32':0,'e33':1},'m_UseCullingMatrixOverride':0},
            'm_Cookie':ref(),'m_DrawHalo':0,'m_Flare':ref(),'m_RenderMode':0,'m_CullingMask':{'serializedVersion':2,'m_Bits':4294967295},
            'm_RenderingLayerMask':1,'m_Lightmapping':4,'m_LightShadowCasterMode':0,'m_AreaSize':Flow(x=1,y=1),
            'm_BounceIntensity':1,'m_ColorTemperature':5800,'m_UseColorTemperature':0,'m_BoundingSphereOverride':Flow(x=0,y=0,z=0,w=0),
            'm_UseBoundingSphereOverride':0,'m_UseViewFrustumForShadowCasterCull':1,'m_ShadowRadius':0,'m_ShadowAngle':0})
        rs['m_Sun']=ref(light)
        go,tr,gd=self.object('Main Camera',position=(-649.7,8,-194.1),static=False)
        gd['m_TagString']='MainCamera'
        self.transforms[tr]['m_LocalRotation']=Flow(x=.23,y=-.13,z=.031,w=.964)
        self.component(go,gd,20,'Camera',{'m_Enabled':1,'serializedVersion':2,'m_ClearFlags':1,'m_BackGroundColor':color(.4,.65,.8),
            'm_projectionMatrixMode':1,'m_GateFitMode':2,'m_FOVAxisMode':0,'m_Iso':200,'m_ShutterSpeed':.005,'m_Aperture':16,
            'm_FocusDistance':10,'m_FocalLength':50,'m_BladeCount':5,'m_Curvature':Flow(x=2,y=11),'m_BarrelClipping':.25,'m_Anamorphism':0,
            'm_SensorSize':Flow(x=36,y=24),'m_LensShift':Flow(x=0,y=0),'m_NormalizedViewPortRect':{'serializedVersion':2,'x':0,'y':0,'width':1,'height':1},
            'near clip plane':.3,'far clip plane':8000,'field of view':60,'orthographic':0,'orthographic size':5,'m_Depth':-1,
            'm_CullingMask':{'serializedVersion':2,'m_Bits':4294967295},'m_RenderingPath':-1,'m_TargetTexture':ref(),'m_TargetDisplay':0,
            'm_TargetEye':3,'m_HDR':1,'m_AllowMSAA':1,'m_AllowDynamicResolution':0,'m_ForceIntoRT':0,'m_OcclusionCulling':1,
            'm_StereoConvergence':10,'m_StereoSeparation':.022})
        self.component(go,gd,81,'AudioListener',{'m_Enabled':1})
    def save(self,path,prefab=False):
        objects=list(self.objects)
        if not prefab:
            objects.append((1660057539,9223372036854775807,'SceneRoots',{'m_ObjectHideFlags':0,'m_Roots':[ref(t) for t,v in self.transforms.items() if v['m_Father']['fileID']==0]}))
        write_yaml(path,objects)
        meta(path,kind='PrefabImporter' if prefab else 'DefaultImporter')
