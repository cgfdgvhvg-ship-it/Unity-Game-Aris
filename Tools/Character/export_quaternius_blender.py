#!/usr/bin/env python3
"""Run *inside Blender*: convert vetted Quaternius GLBs to native Unity FBXs.

This exporter runs once in development/CI. The game never downloads an asset.
FBX armature rigs are imported as Unity Humanoid by AarisCharacterImport.cs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import bpy


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def import_glb(path: Path) -> None:
    bpy.ops.import_scene.gltf(filepath=str(path))


def select_only(items) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in items:
        obj.select_set(True)
    if items:
        bpy.context.view_layer.objects.active = items[0]


def export_player(file: Path) -> None:
    objects = [obj for obj in bpy.context.scene.objects if obj.type in {"ARMATURE", "MESH"}]
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in objects if obj.type == "MESH"]
    if not armatures or not meshes:
        raise RuntimeError("Male character GLB missing armature or mesh")
    # Preserve original material maps; FBX exporter embeds textures and the
    # import directory also retains extracted copies for future material QA.
    texture_folder = file.parent / "Textures"
    texture_folder.mkdir(parents=True, exist_ok=True)
    for image in bpy.data.images:
        if image.name in {"Render Result", "Viewer Node"} or not image.has_data:
            continue
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", image.name)
        if not safe_name.lower().endswith((".png", ".jpg", ".jpeg")):
            safe_name += ".png"
        destination = texture_folder / safe_name
        try:
            if image.packed_file is not None:
                image.filepath_raw = str(destination)
                image.file_format = "PNG"
                image.save()
            elif image.filepath and Path(bpy.path.abspath(image.filepath)).exists():
                image.filepath_raw = str(destination)
                image.file_format = "PNG"
                image.save()
        except RuntimeError:
            pass
    select_only(armatures + meshes)
    bpy.ops.export_scene.fbx(
        filepath=str(file),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        bake_anim=False,
        add_leaf_bones=False,
        path_mode="COPY",
        embed_textures=True,
        use_mesh_modifiers=True,
        use_space_transform=True,
        apply_unit_scale=True,
    )
    if file.stat().st_size < 6000:
        raise RuntimeError("Male FBX export suspiciously small")
    print("Exported rigged male FBX", file.name, "meshes", len(meshes), "armatures", len(armatures))


def choose_actions(actions):
    # Names vary slightly across animation library versions. Explicit curated
    # matches avoid baking an arbitrary gesture as locomotion.
    rules = {
        "idle": ("idle", "breathing"),
        "walk": ("walk",),
        "run": ("sprint", "jog", "run"),
        "jump": ("jump",),
        "fall": ("fall",),
        "strafe_left": ("strafe left", "strafe_left", "left strafe"),
        "strafe_right": ("strafe right", "strafe_right", "right strafe"),
        "crouch": ("crouch idle", "crouch_idle"),
    }
    matches = {}
    for canonical, keywords in rules.items():
        for keyword in keywords:
            candidates = [a for a in actions if keyword in a.name.lower()]
            if candidates:
                # Prefer a dedicated full-body motion over a named transition.
                candidates.sort(key=lambda a: ("transition" in a.name.lower(),
                                               "start" in a.name.lower(),
                                               len(a.name)))
                matches[canonical] = candidates[0]
                break
    for required in ("idle", "walk", "run", "jump"):
        if required not in matches:
            raise RuntimeError("Missing required animation action '" + required +
                               "': " + ", ".join(sorted(a.name for a in actions)[:100]))
    return matches


def export_animation_library(file: Path, output: Path) -> None:
    reset_scene()
    import_glb(file)
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not rigs:
        raise RuntimeError("Animation library has no humanoid armature")
    rig = sorted(rigs, key=lambda o: len(o.data.bones), reverse=True)[0]
    actions = list(bpy.data.actions)
    if not actions:
        raise RuntimeError("Animation library does not contain any action")
    selected = choose_actions(actions)
    output.mkdir(parents=True, exist_ok=True)
    exported = {}
    for name, action in selected.items():
        bpy.context.scene.frame_start = int(action.frame_range[0])
        bpy.context.scene.frame_end = max(bpy.context.scene.frame_start + 1,
                                          int(action.frame_range[1]))
        rig.animation_data_create()
        # Clear the imported NLA stack, otherwise multiple actions may bake
        # together into a single clip instead of the requested source action.
        for track in list(rig.animation_data.nla_tracks):
            rig.animation_data.nla_tracks.remove(track)
        rig.animation_data.action = action
        select_only([rig])
        target = output / (name + ".fbx")
        bpy.ops.export_scene.fbx(
            filepath=str(target), use_selection=True,
            object_types={"ARMATURE"}, add_leaf_bones=False,
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_step=1.0,
            path_mode="AUTO",
        )
        if target.stat().st_size < 2000:
            raise RuntimeError("Empty FBX animation: " + name)
        exported[name] = {"source_action": action.name,
                          "frames": [bpy.context.scene.frame_start, bpy.context.scene.frame_end]}
        print("Exported animation", name, "from", action.name)
    (output / "clip-sources.json").write_text(json.dumps(exported, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    sep = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--animations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sep + 1:])
    args.output.mkdir(parents=True, exist_ok=True)
    reset_scene()
    import_glb(args.model)
    export_player(args.output / "Player.fbx")
    export_animation_library(args.animations, args.output / "Animations")
    print("Aaris Quaternius male character and animation FBXs converted.")


if __name__ == "__main__":
    main()
