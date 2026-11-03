"""Foreground, read-only watcher of saved Unity core files.

Run in a terminal while editing. The watcher never edits assets, never starts
itself in GitHub, and never treats a partial LFS checkout as complete geometry.
JSON Lines are emitted after a stable saved change and a successful re-read.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from unity_data import World, WorldError, digest
from observations import inspect
from patching import _observation_deltas
from site_intelligence import site_summary

SUFFIXES = {
    ".unity", ".prefab", ".asset", ".mat", ".meta", ".fbx", ".obj", ".mesh",
    ".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".psd",
    ".cs", ".shader", ".shadergraph", ".shadersubgraph", ".hlsl", ".compute",
    ".asmdef", ".asmref", ".controller", ".anim", ".overridecontroller",
    ".rendertexture", ".physicmaterial", ".terrainlayer", ".json",
}
WATCH_FOLDERS = ("Assets", "Packages", "ProjectSettings")
SKIP_DIRS = {".git", ".source-cache", ".model-cache", "__pycache__", "Library", "Temp", "Logs", "obj"}


def file_inventory(root):
    """Cheap metadata pass; do not hash gigabytes of unchanged LFS assets."""
    root = Path(root).resolve()
    rows = {}
    for folder in WATCH_FOLDERS:
        directory = root / folder
        if not directory.is_dir():
            continue
        for base, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and
                             not (Path(base) / d).is_symlink())
            for name in files:
                p = Path(base) / name
                if p.suffix.lower() not in SUFFIXES or p.is_symlink():
                    continue
                try:
                    stat = p.stat()
                except FileNotFoundError:
                    continue
                rows[p.relative_to(root).as_posix()] = (
                    stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
                )
    return rows


def changed_paths(previous, current):
    return sorted(path for path in previous.keys() | current.keys()
                  if previous.get(path) != current.get(path))


def _known_hashes(inspection):
    return {path: checksum for path, checksum in
            ((inspection.get("source_fingerprint") or {}).get("files") or [])}


def file_deltas(root, before, after, changed, before_inspection):
    known = _known_hashes(before_inspection)
    result = []
    for path in changed:
        p = Path(root) / path
        old, new = before.get(path), after.get(path)
        # cap expensive hashing and don't misrepresent skipped hashes as exact
        try:
            after_sha = digest(p) if new and new[0] <= 128 * 1024 * 1024 else None
        except OSError:
            after_sha = None
        result.append({
            "path": path,
            "event": "created" if old is None else "deleted" if new is None else "modified",
            "before_bytes": old[0] if old else None,
            "after_bytes": new[0] if new else None,
            "before_sha256": known.get(path),
            "after_sha256": after_sha,
            "before_hash_status": "from_prior_inspection" if path in known else "not_previously_read",
            "after_hash_status": "computed" if after_sha is not None else "deleted_or_over_128MiB_or_unreadable",
        })
    return result


class SiteWatcher:
    def __init__(self, root, query):
        self.root = Path(root).resolve()
        self.query = dict(query)
        self.files = file_inventory(self.root)
        self.inspection = inspect(World(self.root), self.query)

    def check(self):
        """Return a read-only event, None when there are no metadata changes.

        Do not advance the baseline when a source file is mid-write or parsing
        fails: the next call retries against the last valid world snapshot.
        """
        current = file_inventory(self.root)
        changed = changed_paths(self.files, current)
        if not changed:
            return None
        fresh = inspect(World(self.root), self.query)
        deltas = _observation_deltas(
            [{"request": self.query, "result": self.inspection}],
            [{"request": self.query, "result": fresh}],
        )
        event = {
            "event": "core_files_changed",
            "source": "local_saved_filesystem",
            "query": self.query,
            "files": file_deltas(self.root, self.files, current, changed, self.inspection),
            "previous_source_fingerprint": self.inspection.get("source_fingerprint"),
            "current_source_fingerprint": fresh.get("source_fingerprint"),
            "observation_deltas": deltas,
            "current_site": site_summary(fresh),
            "limits": "A watched local process must stay running; material/mesh changes may require Unity import and capture for true rendered appearance.",
        }
        self.files = current
        self.inspection = fresh
        return event


def run(root, query, poll_seconds=2.0, quiet_seconds=1.0, max_events=0):
    if not .5 <= poll_seconds <= 60.0:
        raise WorldError("watch poll_seconds must be 0.5..60")
    if not 0 <= quiet_seconds <= 30.0:
        raise WorldError("watch quiet_seconds must be 0..30")
    if type(max_events) is not int or max_events < 0:
        raise WorldError("watch max_events must be a non-negative integer")
    watcher = SiteWatcher(root, query)
    print(json.dumps({
        "event": "watch_started", "query": query,
        "baseline": site_summary(watcher.inspection),
        "execution": "foreground_only; stop with Ctrl+C; no autonomous cloud daemon",
    }, allow_nan=False), flush=True)
    events = 0
    try:
        while not max_events or events < max_events:
            time.sleep(poll_seconds)
            # Debounce successive writes (scene then material then metadata).
            if quiet_seconds and changed_paths(watcher.files, file_inventory(watcher.root)):
                time.sleep(quiet_seconds)
            try:
                event = watcher.check()
            except (WorldError, OSError, KeyError, ValueError, ImportError) as error:
                print(json.dumps({"event": "watch_read_retry", "reason": str(error),
                                  "note": "Baseline unchanged; retry after file save completes"},
                                 allow_nan=False), flush=True)
                continue
            if event:
                print(json.dumps(event, allow_nan=False), flush=True)
                events += 1
    except KeyboardInterrupt:
        pass
    print(json.dumps({"event": "watch_stopped", "events": events}, allow_nan=False), flush=True)
    return 0
