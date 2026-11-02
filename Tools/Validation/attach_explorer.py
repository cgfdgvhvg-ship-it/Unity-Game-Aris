"""Attach saved camera components; does not alter TerrainData or model placements."""
import re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'MapBuild'))
from native_assets import ref,guid,Flow,write_yaml,meta
from build_map import unity_docs

SCRIPT='Assets/AarisWorld/Scripts/AarisMapExplorer.cs'
def components():
    return {'m_Enabled':1,'m_EditorHideFlags':0,'m_Script':ref(11500000,guid(SCRIPT),3),
            'm_Name':'','m_EditorClassIdentifier':'Assembly-CSharp::Aaris.MapReview.AarisMapExplorer',
            'moveSpeed':45,'fastMultiplier':4,'mouseLookSensitivity':.15,'touchLookSensitivity':.10,
            'terrainClearance':2.5,'mapBoundary':980,'maximumAltitude':1800,'showHelp':1}

def attach(path):
    path=Path(path);objects=list(unity_docs(path.read_text()))
    go=next(i for c,i,n,d in objects if c==1 and d['m_Name']=='Main Camera')
    gd=next(d for c,i,n,d in objects if i==go)
    used={i for c,i,n,d in objects};ident=max(i for i in used if i<2**62)+1
    def add(cls,name,fields):
        nonlocal ident
        while ident in used:ident+=1
        data={'m_ObjectHideFlags':0,'m_CorrespondingSourceObject':ref(),'m_PrefabInstance':ref(),'m_PrefabAsset':ref(),'m_GameObject':ref(go),**fields}
        objects.insert(-1,(cls,ident,name,data));gd['m_Component'].append({'component':ref(ident)});used.add(ident);ident+=1
    if not any(c==114 and d.get('m_GameObject',{}).get('fileID')==go and d.get('m_Script',{}).get('guid')==guid(SCRIPT) for c,i,n,d in objects):add(114,'MonoBehaviour',components())
    if not any(c==81 and d.get('m_GameObject',{}).get('fileID')==go for c,i,n,d in objects):add(81,'AudioListener',{'m_Enabled':1})
    # Flow style on references is cosmetic; fileIDs and every existing object are preserved.
    write_yaml(path,objects)
    print('Saved camera explorer and AudioListener in',path)
if __name__=='__main__':attach('Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity')
