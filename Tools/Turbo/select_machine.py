#!/usr/bin/env python3
"""Select one Codespace deterministically, or request exactly one fresh instance.

This script runs under the chosen Codespaces account's scoped GH_TOKEN.
Never auto-select across ambiguous machines, and never touch old accounts.
"""
import json
import re
import sys

VALID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{2,119}\Z")
PREFERRED = ("aaris-ai-ubuntu-minimal", "aaris-ai-unity-ssh")


def plan(machines, requested):
    if not isinstance(machines, list):
        raise ValueError("invalid_machine_list")
    for item in machines:
        if not isinstance(item, dict) or not VALID.fullmatch(str(item.get("name", ""))):
            raise ValueError("invalid_machine_entry")
    if requested and requested != "auto":
        if not VALID.fullmatch(requested):
            raise ValueError("invalid_requested_machine")
        candidates = [m for m in machines if m["name"] == requested]
        if len(candidates) != 1:
            raise ValueError("exact_machine_not_visible")
        return {"action": "reuse", "name": requested}

    if not machines:
        if requested != "auto":
            raise ValueError("no_codespace_select_auto_to_create")
        return {"action": "create", "name": None}

    candidates = machines
    for title in PREFERRED:
        preferred = [m for m in candidates if m.get("displayName") == title]
        if preferred:
            candidates = preferred
            break
    if len(candidates) != 1:
        ready = [m for m in candidates if m.get("state") == "Available"]
        if len(ready) == 1:
            candidates = ready
    if len(candidates) != 1:
        raise ValueError("ambiguous_codespaces_explicit_name_required")
    return {"action": "reuse", "name": candidates[0]["name"]}


def selftest():
    one = {"name": "new-ssh-01", "displayName": "aaris-ai-unity-ssh", "state": "Shutdown"}
    other = {"name": "other-ubuntu", "displayName": "Other", "state": "Available"}
    assert plan([], "auto") == {"action": "create", "name": None}
    assert plan([one], "auto") == {"action": "reuse", "name": "new-ssh-01"}
    assert plan([one, other], "auto")["name"] == "new-ssh-01"
    assert plan([one, other], "other-ubuntu")["name"] == "other-ubuntu"
    for machines, request in [([], ""), ([one, dict(one)], "auto"), ([other], "bad/name"),
                              ([one], "absent")]:
        try:
            plan(machines, request)
        except ValueError:
            pass
        else:
            raise AssertionError((machines, request))
    print("TURBO_DYNAMIC_SELECTION_SELFTEST_PASS")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit("usage: select_machine.py machines.json exact-name|auto")
    try:
        with open(sys.argv[1], encoding="utf-8") as file:
            print(json.dumps(plan(json.load(file), sys.argv[2]), separators=(",", ":")))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        # Return only a fixed, non-sensitive classification.
        print("TURBO_SELECTION_FAILED:" + type(exc).__name__, file=sys.stderr)
        sys.exit(12)
