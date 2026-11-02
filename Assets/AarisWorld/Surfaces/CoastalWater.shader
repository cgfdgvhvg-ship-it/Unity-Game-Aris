Shader "Aaris/URP Coastal Water" {
Properties { _BaseColor("Water",Color)=(0.03,0.22,0.28,1) _Smoothness("Smoothness",Range(0,1))=.8 }
SubShader { Tags { "RenderPipeline"="UniversalPipeline" "RenderType"="Opaque" "Queue"="Geometry-10" }
Pass { Name "ForwardLit" Tags { "LightMode"="UniversalForward" } Cull Back ZWrite On
HLSLPROGRAM
#pragma vertex vert
#pragma fragment frag
#pragma multi_compile_fog
#pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
CBUFFER_START(UnityPerMaterial)
float4 _BaseColor; float _Smoothness;
CBUFFER_END
struct A {float4 positionOS:POSITION;};
struct V {float4 positionCS:SV_POSITION;float3 world:TEXCOORD0;float fog:TEXCOORD1;};
V vert(A i) {V o;float3 p=TransformObjectToWorld(i.positionOS.xyz);p.y+=.10*sin(p.x*.045+_Time.y*.6)+.06*sin(p.z*.063-_Time.y*.45);o.world=p;o.positionCS=TransformWorldToHClip(p);o.fog=ComputeFogFactor(o.positionCS.z);return o;}
half4 frag(V i):SV_Target {float3 n=normalize(float3(-.0045*cos(i.world.x*.045+_Time.y*.6),1,-.00378*cos(i.world.z*.063-_Time.y*.45)));float3 v=GetWorldSpaceNormalizeViewDir(i.world);Light l=GetMainLight(TransformWorldToShadowCoord(i.world));float f=pow(1-saturate(dot(n,v)),5);float3 c=lerp(_BaseColor.rgb,float3(.42,.61,.7),f*.7);c*=.55+.45*saturate(dot(n,l.direction))*l.shadowAttenuation;float spec=pow(saturate(dot(n,normalize(l.direction+v))),120);c+=spec*l.color*.65;return half4(MixFog(c,i.fog),1);}
ENDHLSL } } }
