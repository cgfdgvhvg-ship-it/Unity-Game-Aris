"""Offline static FBX -> native mesh/material/prefab assets for AI authoring.

Uses the project's existing native asset writer. Import never chooses a map
location and never replaces an existing destination or existing .meta file.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import sys
import tempfile
import zipfile

import numpy as np
from PIL import Image

from unity_data import WorldError, digest, documents, safe_path


def _fbx_contract(raw):
    """Read binary FBX metadata without relying on an assumed world unit."""
    if not raw.startswith(b"Kaydara FBX Binary  \0\x1a\0"):
        raise WorldError("Only binary static FBX is currently supported by this importer")
    version = struct.unpack_from("<I", raw, 23)[0]
    wide = version >= 7500; fmt = "<QQQB" if wide else "<IIIB"; header = 25 if wide else 13
    props, unsupported = {}, []
    def values(start, count, size):
        end = start+size; result=[]
        for _ in range(count):
            kind=chr(raw[start]);start+=1
            if kind in "YCI FDL".replace(" ", ""):
                form={"Y":"h","C":"?","I":"i","F":"f","D":"d","L":"q"}[kind]
                result.append(struct.unpack_from("<"+form,raw,start)[0]);start+=struct.calcsize(form)
            elif kind in "SR":
                n=struct.unpack_from("<I",raw,start)[0];start+=4
                item=raw[start:start+n];start+=n
                result.append(item.decode("utf-8",errors="replace") if kind=="S" else None)
            elif kind in "fdlibc":
                count_, encoding, length=struct.unpack_from("<III",raw,start);start+=12+length
                result.append(None)
            else:
                raise WorldError("Unsupported FBX property encoding")
            if start>end:
                raise WorldError("Invalid FBX property bounds")
        if start!=end:
            raise WorldError("Invalid FBX property length")
        return result
    def nodes(start,end,trail=()):
        while start+header <= end:
            stop,count,size,n=struct.unpack_from(fmt,raw,start)
            if stop==0:break
            if not start+header+n+size<=stop<=len(raw):
                raise WorldError("Invalid FBX node bounds")
            name=raw[start+header:start+header+n].decode("utf-8",errors="replace")
            pstart=start+header+n
            if trail==("GlobalSettings","Properties70") and name=="P":
                v=values(pstart,count,size)
                if v and v[0] in ("UnitScaleFactor","UpAxis","UpAxisSign","FrontAxis","FrontAxisSign","CoordAxis","CoordAxisSign"):
                    props[v[0]]=v[-1]
            if trail==("Objects",) and name in ("Deformer","AnimationStack","AnimationCurve"):
                unsupported.append(name)
            if len(trail)<2 and name in ("GlobalSettings","Properties70","Objects"):
                nodes(pstart+size,stop,trail+(name,))
            start=stop
    nodes(27,len(raw))
    return {"fbx_version":version,"global_settings":props,"non_static_records":unsupported}


def _unpack(source, destination):
    if source.suffix.lower()==".fbx":
        raise WorldError("Package the binary FBX and its four PBR textures in one ZIP so source_sha256 binds every import input")
    if source.suffix.lower()!=".zip":
        raise WorldError("Supply a ZIP containing one binary static FBX and its four PBR textures")
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>256 or sum(e.file_size for e in entries)>256*1024*1024:
            raise WorldError("Model ZIP exceeds the bounded import budget")
        for entry in entries:
            path=PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or stat.S_ISLNK(entry.external_attr>>16):
                raise WorldError("Unsafe model ZIP entry")
            if entry.is_dir():continue
            target=destination/entry.filename;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(entry))
    models=list(destination.rglob("*.fbx"))+list(destination.rglob("*.FBX"))
    if len(models)!=1:
        raise WorldError("Model ZIP must contain exactly one FBX; choose a model explicitly")
    return models[0]


def _geometry(path, unit_scale):
    import assimp_py as assimp
    flags=(assimp.Process_Triangulate|assimp.Process_PreTransformVertices|assimp.Process_JoinIdenticalVertices|
           assimp.Process_GenSmoothNormals|assimp.Process_ValidateDataStructure)
    try:
        scene=assimp.import_file(str(path),flags)
    except RuntimeError as error:
        raise WorldError("Assimp could not decode the static model: "+str(error)) from error
    if scene.num_meshes!=1 or scene.num_materials!=1:
        raise WorldError("This offline importer supports one static mesh/material; split a multi-material model explicitly")
    mesh=scene.meshes[0]
    if not mesh.texcoords or mesh.normals is None or mesh.num_uv_components[0]!=2:
        raise WorldError("Static model must have normals and a two-component UV set")
    p=np.asarray(mesh.vertices,dtype=np.float32).reshape(-1,3).copy()*unit_scale
    n=np.asarray(mesh.normals,dtype=np.float32).reshape(-1,3).copy()
    uv=np.asarray(mesh.texcoords[0],dtype=np.float32).reshape(-1,2).copy()
    indices=np.asarray(mesh.indices,dtype=np.uint32).reshape(-1,3).copy()
    if len(p)>1_000_000 or len(indices)>1_000_000 or not len(p):
        raise WorldError("Model geometry exceeds the static import budget")
    if not all(np.isfinite(a).all() for a in (p,n,uv)) or indices.max()>=len(p):
        raise WorldError("Invalid model geometry")
    # Assimp's FBX hierarchy is baked first, then RH -> Unity LH is explicit.
    p[:,2]*=-1;n[:,2]*=-1;indices=indices[:,[0,2,1]]
    n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-10)
    low,high=p.min(0),p.max(0);pivot=np.array([(low[0]+high[0])/2,low[1],(low[2]+high[2])/2])
    p-=pivot
    return p,n,uv,indices.reshape(-1),pivot


def import_model(root, source, destination, source_sha256, unit_scale, texture_size=2048, write=False, freeze_static_pose=False):
    root=Path(root).resolve();source=Path(source).resolve()
    if not source.is_file() or digest(source)!=source_sha256:
        raise WorldError("Source model SHA256 is stale or missing")
    if isinstance(unit_scale,bool) or not isinstance(unit_scale,(int,float)) or not math.isfinite(unit_scale) or not 0<unit_scale<=100:
        raise WorldError("unit_scale must explicitly state finite source-units-to-metres")
    if texture_size not in (512,1024,2048,4096):
        raise WorldError("texture_size must be 512, 1024, 2048 or 4096")
    if not isinstance(destination,str) or not re.fullmatch(r"Assets/WorldImports/[A-Za-z0-9_-]+",destination):
        raise WorldError("New model destination must be Assets/WorldImports/<safe-name>")
    target=safe_path(root,destination)
    if target.exists() or Path(str(target)+".meta").exists():
        raise WorldError("Model destination already exists; imported assets and GUIDs are never overwritten")
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"MapBuild"))
    from native_assets import mesh_asset, material_asset, meta, guid
    from native_scene import Scene
    template_path=Path(__file__).resolve().parents[1]/"MapBuild/mesh_template.b64"
    template=base64.b64decode(template_path.read_text()).decode()
    with tempfile.TemporaryDirectory(prefix="aaris-static-import-") as tmp:
        temp=Path(tmp);unpacked=temp/"source";unpacked.mkdir()
        model=_unpack(source,unpacked)
        contract=_fbx_contract(model.read_bytes())
        if contract["non_static_records"] and not freeze_static_pose:
            raise WorldError("FBX contains non-static records: "+str(contract["non_static_records"])+". Explicit --freeze-static-pose imports only the authored default pose, discarding animation.")
        p,n,uv,inds,pivot=_geometry(model,float(unit_scale))
        output=temp/destination;output.mkdir(parents=True)
        textures={};source_textures={}
        images={}
        for role in ("BaseColor","Roughness","Metallic","Normal"):
            matches=[f for f in unpacked.rglob("*") if f.is_file() and f.stem.lower().endswith("_"+role.lower())]
            if len(matches)!=1:
                raise WorldError(f"Model needs exactly one explicit {role} texture")
            f=matches[0]
            with Image.open(f) as image:
                if image.width*image.height>4096*4096:
                    raise WorldError("Source texture exceeds 4096x4096 import budget")
                image.load();image.thumbnail((texture_size,texture_size),Image.Resampling.LANCZOS)
                images[role]=image.copy().convert("L" if role in ("Roughness","Metallic") else "RGB")
                source_textures[role]={"sha256":digest(f),"source_file":f.relative_to(unpacked).as_posix(),"authored_size":list(image.size)}
        if len({im.size for im in images.values()})!=1:
            raise WorldError("PBR texture dimensions must match")
        for role,filename,options in (("BaseColor","BaseColor.png",{}),("Normal","Normal.png",{"normal":True,"linear":True})):
            dest=output/filename;images[role].save(dest,optimize=True);meta(dest,texture=options)
            textures["_BaseMap" if role=="BaseColor" else "_BumpMap"]=guid(dest)
        # URP metallic comes from R; smoothness from A. Roughness is inverted.
        size=images["Metallic"].size;black=Image.new("L",size,0)
        packed=Image.merge("RGBA",(images["Metallic"],black,black,images["Roughness"].point(lambda v:255-v)))
        dest=output/"MetallicSmoothness.png";packed.save(dest,optimize=True);meta(dest,texture={"linear":True})
        textures["_MetallicGlossMap"]=guid(dest)
        mesh=mesh_asset(output/"Geometry.asset",p,n,uv,inds,template,name=target.name)
        material=material_asset(output/"Surface.mat",target.name,base=(1,1,1,1),metallic=1,smoothness=1,textures=textures)
        prefab=Scene();prefab.model(target.name,mesh["guid"],[material],bounds=mesh["bounds"],lod=False)
        prefab.save(output/(target.name+".prefab"),prefab=True);meta(output,kind="folder")
        manifest={"source_sha256":source_sha256,"source_model_sha256":digest(model),"source_contract":contract,
                  "source_unit_to_metres":unit_scale,"source_pivot_removed_m":pivot.tolist(),
                  "animation_policy":"authored_default_pose_only" if freeze_static_pose else "static_only",
                  "dimensions_m":np.ptp(p,axis=0).tolist(),"mesh":mesh,"source_textures":source_textures,
                  "prefab_path":destination+"/"+target.name+".prefab","decision_owner":"AI/caller",
                  "geometry_conversion":"Assimp static node transforms baked; explicit Z reflection and triangle winding reversal",
                  "engine_import_tested":False,"source_archive_preserved_by_caller":True}
        (output/"Import.json").write_text(json.dumps(manifest,indent=2)+"\n");meta(output/"Import.json",kind="DefaultImporter")
        # Parse native YAML before installing anything into Assets.
        for f in output.iterdir():
            if f.suffix in (".asset",".prefab",".mat"):
                documents(f)
        paths=[f for f in output.rglob("*") if f.is_file()]+[Path(str(output)+".meta")]
        manifest["authored_files"]={f.relative_to(temp).as_posix():digest(f) for f in paths}
        manifest["dry_run"]=not write
        if write:
            if digest(source)!=source_sha256 or target.exists() or Path(str(target)+".meta").exists():
                raise WorldError("Import preconditions changed; no assets installed")
            created_parents=[];created_target=False;created_target_meta=False
            try:
                parent=target.parent
                if not parent.exists():
                    parent.mkdir(parents=True);created_parents.append(parent)
                    if not Path(str(parent)+".meta").exists():meta(parent,kind="folder")
                # Single new asset directory; rollback removes only our own new paths.
                target.mkdir();created_target=True
                shutil.copytree(output,target,dirs_exist_ok=True)
                with Path(str(target)+".meta").open("xb") as f:
                    created_target_meta=True;f.write(Path(str(output)+".meta").read_bytes())
            except BaseException:
                if created_target:shutil.rmtree(target,ignore_errors=True)
                if created_target_meta:Path(str(target)+".meta").unlink(missing_ok=True)
                for parent in reversed(created_parents):
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir();Path(str(parent)+".meta").unlink(missing_ok=True)
                raise
        return manifest
