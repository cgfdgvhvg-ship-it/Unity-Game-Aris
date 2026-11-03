"""Validate the eight explicitly saved RockCover additions without Unity or LFS.

This checks serialized scene identity, parenting, exact collider gating and LOD
references. It does not claim a Unity import, ground-contact physics or FPS.
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "Docs/ROCK_CLUSTER_ADDITIONS_20261103.json"
SCENE = ROOT / "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"


def field(body, key):
    match = re.search(r"^  " + re.escape(key) + r": (.+)$", body, re.M)
    assert match is not None, ("missing field", key)
    return match.group(1)


def file_id(value):
    match = re.fullmatch(r"\{fileID: (\d+)\}", value)
    assert match, ("unexpected local Unity reference", value)
    return int(match.group(1))


def vector(value, keys):
    result = {}
    for key in keys:
        match = re.search(r"(?:\{|, )" + key + r": ([^,}]+)", value)
        assert match, (key, value)
        result[key] = float(match.group(1))
    return result


def documents(text):
    matches = list(re.finditer(r"^--- !u!(\d+) &(\d+)\n", text, re.M))
    assert matches and text.startswith("%YAML 1.1\n")
    objects = {}
    for index, match in enumerate(matches):
        klass, ident = map(int, match.groups())
        assert ident not in objects, ("duplicate Unity fileID", ident)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        objects[ident] = (klass, text[match.start():end])
    return objects


def collect(root, objects, transforms, seen=None):
    if seen is None:
        seen = set()
    assert root not in seen and root in transforms
    seen.add(root)
    body = transforms[root]
    go = file_id(field(body, "m_GameObject"))
    assert go in objects and objects[go][0] == 1
    seen.add(go)
    components = [int(x) for x in re.findall(r"^  - component: \{fileID: (\d+)\}", objects[go][1], re.M)]
    for item in components:
        assert item in objects
        if item != root:
            assert item not in seen
            seen.add(item)
    children = [int(x) for x in re.findall(r"^  - \{fileID: (\d+)\}", body, re.M)]
    for child in children:
        collect(child, objects, transforms, seen)
    return seen


def check():
    data = json.loads(MANIFEST.read_text())
    scene = SCENE.read_text()
    assert not scene.startswith("version https://git-lfs.github.com/spec/v1")
    objects = documents(scene)
    transforms = {i: b for i, (k, b) in objects.items() if k == 4}
    names = {field(b, "m_Name"): i for i, (k, b) in objects.items()
             if k == 1 and re.search(r"^  m_Name: ", b, re.M)}
    named_rocks = [name for name in names if re.fullmatch(r"RockCover_\d+", name)]
    assert len(named_rocks) == data["expected_total_rocks"] == 32, named_rocks
    assert len(data["placements"]) == data["new_authored_rocks"] == 8
    props_children = {int(n) for n in re.findall(
        r"^  - \{fileID: (\d+)\}", transforms[400001], re.M)}
    gate = next(b for klass, b in objects.values()
                if klass == 114 and "Assembly-CSharp::Aaris.MapReview.AarisNearbyColliders" in b)
    obstacles = [int(n) for n in re.findall(r"^  - \{fileID: (\d+)\}", gate, re.M)]
    collider_ids = {i for i, (kind, _) in objects.items() if kind in (64, 65)}
    assert len(obstacles) == len(set(obstacles))
    assert set(obstacles) == collider_ids, ("collider gate mismatch", len(obstacles), len(collider_ids))

    for item in data["placements"]:
        name = item["name"]
        game_object = item["game_object_file_id"]
        transform = item["transform_file_id"]
        collider = item["box_collider_file_id"]
        assert names[name] == game_object
        assert objects[game_object][0] == 1
        assert transform in props_children
        assert file_id(field(transforms[transform], "m_Father")) == 400001
        assert file_id(field(transforms[transform], "m_GameObject")) == game_object
        group = collect(transform, objects, transforms)
        kinds = [objects[x][0] for x in group]
        assert len(group) == 16
        assert kinds.count(205) == 1, (name, "LODGroup")
        assert kinds.count(23) == 3, (name, "MeshRenderers")
        assert kinds.count(33) == 3, (name, "MeshFilters")
        assert kinds.count(65) == 1 and collider in group and collider in obstacles
        lod = next(objects[x][1] for x in group if objects[x][0] == 205)
        assert lod.count("screenRelativeHeight:") == 3

        p = vector(field(transforms[transform], "m_LocalPosition"), ("x", "y", "z"))
        for key, expected in zip(("x", "y", "z"), item["position_m"]):
            assert math.isclose(p[key], expected, abs_tol=1e-5), (name, key, p[key], expected)
        assert abs(p["x"]) < 995 and abs(p["z"]) < 995
        size = vector(field(transforms[transform], "m_LocalScale"), ("x", "y", "z"))
        assert all(math.isclose(v, item["uniform_scale"], abs_tol=1e-6)
                   for v in size.values())
        rotation = vector(field(transforms[transform], "m_LocalRotation"), ("x", "y", "z", "w"))
        angle = math.radians(item["yaw_degrees"]) / 2.0
        assert math.isclose(rotation["y"], math.sin(angle), abs_tol=1e-8)
        assert math.isclose(rotation["w"], math.cos(angle), abs_tol=1e-8)

    print(json.dumps({
        "status": "serialized_rock_cluster_checks_passed",
        "saved_rock_objects": len(named_rocks),
        "new_rock_objects": len(data["placements"]),
        "gated_colliders": len(obstacles),
        "unity_imported": False,
        "native_terrain_contact_verified": False,
        "android_fps_measured": False,
    }))


if __name__ == "__main__":
    check()
