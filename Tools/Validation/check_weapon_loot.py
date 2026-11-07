#!/usr/bin/env python3
"""Fail closed when offline gun assets, matches or renderer bindings drift.

No C# compiler/Unity Editor is available in this job. Native FBX bytes and
actual game-time physics/animation require separate Unity import/playmode QA.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "Assets/Resources/AarisWeapons/Models"
EXPECTED = {
    "SMG": (70348, "2fadbba99ac6d3373b8f6b04786374c42c54394f"),
    "AssaultRifle": (92204, "8f2109f415755ad0af8aaa1d911ddfea7c2064cd"),
    "BattleRifle": (91644, "24f2bfee4166e2208cb070b3de273f0989fafc9d"),
    "Sniper": (86636, "a743e79ea184966021aba937d30cb6876e2cbaba"),
    "Shotgun": (60604, "3590c4b06c378037190edd870ca0c24fdaf5ae8a"),
}
SCRIPTS = ROOT / "Assets/AarisWorld/Scripts"


def run():
    catalog = json.loads((ROOT / "Assets/Resources/AarisWeapons/weapon_catalog.json").read_text())
    ids = [entry["id"] for entry in catalog["weapons"]]
    assert ids == list(EXPECTED), ids
    for gun in catalog["weapons"]:
        name = gun["id"]
        assert gun["modelResource"] == "AarisWeapons/Models/" + name
        assert 20 <= gun["rpm"] <= 1300 and gun["magazineSize"] > 0
        assert gun["reserveAmmo"] >= 0 and gun["reloadSeconds"] > 0
        assert gun["pellets"] >= 1 and gun["damage"] > 0 and gun["weight"] > 0
        assert gun["adsFov"] >= 8 and gun["adsFov"] <= 65
        path = MODELS / (name + ".fbx")
        assert path.exists(), "Real local mesh is missing: " + str(path)
        assert path.stat().st_size == EXPECTED[name][0], "Not fully hydrated or source changed: " + name
        assert path.read_bytes()[:18].startswith(b"Kaydara FBX Binary"), "Not an FBX binary: " + name
        assert subprocess.check_output(["git", "hash-object", str(path)]).decode().strip() == EXPECTED[name][1]
        assert (MODELS / (name + ".fbx.meta")).exists(), name + " GUID missing"
    assert catalog["weapons"][3]["automatic"] is False
    assert catalog["weapons"][4]["pellets"] > 1
    loot = json.loads((ROOT / "Assets/Resources/AarisWeapons/loot_candidates.json").read_text())
    assert loot["schema"] == 1 and loot["sizeMetres"] == 2000
    source = json.loads((ROOT / "Docs/MAP_LAYOUT.json").read_text())
    origins = {x["name"] for x in source["buildings"]}
    assert any(x["kind"] == "indoor" for x in loot["candidates"])
    assert any(x["kind"] == "open" for x in loot["candidates"])
    assert all(x["origin"] in origins if x["kind"] == "indoor" else x["origin"] == "grid"
               for x in loot["candidates"])
    import importlib.util
    module_path = ROOT / "Tools/Weapons/bake_loot.py"
    spec = importlib.util.spec_from_file_location("aaris_bake_loot", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.build(source) == loot, "Authored candidates drifted from actual map layout"

    catalog_cs = (SCRIPTS / "AarisWeaponCatalog.cs").read_text()
    gun_cs = (SCRIPTS / "AarisEquippedGun.cs").read_text()
    inventory = (SCRIPTS / "AarisWeaponInventory.cs").read_text()
    world = (SCRIPTS / "AarisWeaponLootWorld.cs").read_text()
    player = (SCRIPTS / "AarisThirdPersonPlayer.cs").read_text()
    action = (SCRIPTS / "AarisBattleActions.cs").read_text()
    hud = (SCRIPTS / "AarisWeaponHUD.cs").read_text()
    assert "JsonUtility.FromJson<AarisWeaponCatalogDocument>" in catalog_cs
    assert "Resources.Load<GameObject>(doc.weapons[i].modelResource)" in catalog_cs
    assert "TryFirstOtherHit" not in gun_cs # renamed and rewritten, not a second weapon motor
    assert "FirstExternalHit" in gun_cs and "SameTarget" in gun_cs
    assert "magazine--;" in gun_cs and "nextFire = Time.time + spec.ShotInterval;" in gun_cs
    assert "BeginReload()" in gun_cs and "reloading" in gun_cs
    assert "semiShotQueued" in action and "equippedGun.Automatic" in action
    assert "new AarisEquippedGun[2]" in inventory
    assert "SetWeaponAimFov" in player and "ApplyWeaponRecoil" in player
    assert "AarisWeaponHUD.CapturesScreenPosition" in player
    assert "MaximumActiveLoot = 40" in world
    assert "ActivationMetres = 42f" in world and "ReleaseMetres = 69f" in world
    assert "TryResolve" in world and "Physics.CheckCapsule" in world
    assert "if (roof.collider is TerrainCollider)" in world
    assert "float chance = indoor ? 0.72f : 0.32f;" in world
    assert "FindObjectsByType<Collider>" not in world
    assert "TreeInstance[]" not in world
    assert "UnityWebRequest" not in "\n".join([catalog_cs,gun_cs,inventory,world,hud])
    print("PASS: 5 locally committed, SHA-verified CC0 weapon FBXs, 2-slot magazine/recoil/scope, "
          "authored 2km loot candidates, streaming and combat source contracts")
    print("Unity Editor import, playable gun handling and visible materials NOT YET TESTED")


if __name__ == "__main__":
    run()
