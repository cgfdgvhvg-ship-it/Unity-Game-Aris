"""Compile core water HLSL against pinned URP headers using official DXC.

This checks HLSL/API compatibility; it is not a Unity ShaderLab/Android build.
"""
import argparse,hashlib,itertools,json,re,subprocess,tempfile
from pathlib import Path

URP_COMMIT='4064d5bb6a1e3748a7cdddc244b89934ad1c3145'
SHADER=Path('Assets/AarisWorld/Surfaces/CoastalWater.shader')

def compile_shader(dxc,urp):
    urp=Path(urp);package=json.loads((urp/'Packages/com.unity.render-pipelines.universal/package.json').read_text())
    assert package['version']=='17.3.0'
    source_commit=subprocess.check_output(['git','-C',str(urp),'rev-parse','HEAD'],text=True).strip();assert source_commit==URP_COMMIT
    source=SHADER.read_text();shared=re.search(r'HLSLINCLUDE(.*?)ENDHLSL',source,re.S)[1]
    programs=re.findall(r'HLSLPROGRAM(.*?)ENDHLSL',source,re.S);assert len(programs)==2
    assert len(re.findall(r'\bWaterVertex\s*\(',shared))==1
    results=[]
    with tempfile.TemporaryDirectory(prefix='aaris-water-hlsl-') as work:
        work=Path(work)
        for number,program in enumerate(programs):
            entries={stage:re.search(r'#pragma '+stage+r'\s+(\w+)',program)[1] for stage in ['vertex','fragment']}
            hlsl=shared+'\n'+re.sub(r'(?m)^\s*#pragma.*$','',program)
            path=work/f'pass_{number}.hlsl';path.write_text(hlsl)
            configs=[()] if number==0 else [fog+light for fog,light in itertools.product([(),('FOG_LINEAR',),('FOG_EXP',),('FOG_EXP2',)],[(),('_MAIN_LIGHT_SHADOWS',),('_MAIN_LIGHT_SHADOWS_CASCADE','_SHADOWS_SOFT_MEDIUM')])]
            for platform,api in [('d3d11','SHADER_API_D3D11'),('vulkan_mobile','SHADER_API_VULKAN')]:
                for flags in configs:
                    for stage,profile in [('vertex','vs_6_0'),('fragment','ps_6_0')]:
                        defines=[api,'UNITY_COMPILER_HLSL','UNITY_VERSION=600030','SHADER_TARGET=35','SHADER_STAGE_'+stage.upper(),*flags]
                        if platform=='vulkan_mobile':defines+=['SHADER_API_MOBILE','UNITY_HARDWARE_TIER3']
                        # URP 17.3 uses legacy vector conditional expressions: HLSL 2018.
                        output=work/'compiled.bin';cmd=[str(dxc),'-E',entries[stage],'-T',profile,'-HV','2018','-I',str(urp),'-Fo',str(output)]
                        if platform=='vulkan_mobile':cmd+=['-spirv','-fspv-target-env=vulkan1.1','-fvk-use-dx-layout']
                        for define in defines:cmd+=['-D',define]
                        done=subprocess.run([*cmd,str(path)],capture_output=True,text=True)
                        assert done.returncode==0,f'{platform} pass {number} {stage} {flags}\n{done.stdout}\n{done.stderr}'
                        assert output.stat().st_size>0
                        results.append({'pass':'DepthOnly' if number==0 else 'ForwardLit','platform':platform,'stage':stage,'keywords':list(flags),'status':'compiled'})
    report={'status':'dxc_hlsl_checks_passed','shader_sha256':hashlib.sha256(SHADER.read_bytes()).hexdigest(),'urp_version':package['version'],
        'urp_source_commit':source_commit,'compiler_version':subprocess.check_output([str(dxc),'--version'],text=True).strip(),
        'hlsl_language_version':2018,'compilations_passed':len(results),'variants':results,
        'unity_shaderlab_import_tested':False,'unity_android_build_tested':False,'android_device_tested':False}
    Path('Docs/WATER_HLSL_CHECKS.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='variants'}));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dxc',required=True);p.add_argument('--urp',required=True);a=p.parse_args();compile_shader(a.dxc,a.urp)
