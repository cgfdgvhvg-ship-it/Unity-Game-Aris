#!/usr/bin/env bash
# Export immutable, already-committed Unity file edits from the ORIGINAL Codespace.
# Does not run git checkout/add/reset/stash/clean on the owner's source files.
set -Eeuo pipefail
umask 077
ROOT=/workspaces/Unity-Game-Aris
RUN=/tmp/aaris-codespaces/working-changes-checkpoint
WORKTREE="$RUN/checkout"
test -d "$WORKTREE" && test -f "$RUN/manifest.json" || { echo AARIS_EXPORT_CHECKPOINT_MISSING; exit 11; }
python3 - "$ROOT" "$WORKTREE" "$RUN" <<'PY'
import pathlib,json,sys,subprocess,hashlib,tarfile,re
src,work,run=map(pathlib.Path,sys.argv[1:])
d=json.loads((run/'manifest.json').read_text())
files=d.get('files',[])
if not isinstance(files,list) or len(files)!=210 or d.get('changedCount')!=210 or d.get('lfsChangedCount')!=1:
    print('AARIS_EXPORT_MANIFEST_INVALID');sys.exit(12)
def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args],stderr=subprocess.DEVNULL)
head=git(work,'rev-parse','HEAD').decode().strip()
parent=git(work,'rev-parse','HEAD^').decode().strip()
if not re.fullmatch('[0-9a-f]{40}',head) or parent!=d['mainHead'] or git(src,'rev-parse','HEAD').decode().strip()!=d['sourceHead']:
    print('AARIS_EXPORT_COMMIT_PARENT_INVALID');sys.exit(13)
changed=sorted(filter(None,git(work,'diff-tree','--no-commit-id','--name-only','-r','-z','HEAD').decode().split('\0')))
planned=sorted(f['path'] for f in files)
if changed!=planned or len(set(planned))!=210:
    print('AARIS_EXPORT_COMMITTED_PATHS_CHANGED');sys.exit(14)
if git(work,'status','--porcelain','--untracked-files=no'):
    print('AARIS_EXPORT_TEMP_WORKTREE_DIRTY');sys.exit(15)
lfs=[f for f in files if f['lfs']]
if len(lfs)!=1:
    print('AARIS_EXPORT_ONLY_ONE_LFS_EXPECTED');sys.exit(16)
for f in files:
    p=src/f['path']
    if not p.is_file() or p.is_symlink() or p.stat().st_size!=f['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:
        print('AARIS_EXPORT_SOURCE_CHANGED');sys.exit(17)
lfs_path=lfs[0]['path']
pointer=git(work,'show','HEAD:'+lfs_path).decode('ascii','replace')
if not pointer.startswith('version https://git-lfs.github.com/spec/v1'):
    print('AARIS_EXPORT_POINTER_INVALID');sys.exit(18)
match=re.search(r'^oid sha256:([0-9a-f]{64})$',pointer,re.M)
if match is None:
    print('AARIS_EXPORT_POINTER_OID_INVALID');sys.exit(19)
oid=match.group(1)
lfs_file=src/lfs_path
if hashlib.sha256(lfs_file.read_bytes()).hexdigest()!=oid:
    print('AARIS_EXPORT_LFS_HASH_MISMATCH');sys.exit(20)
if lfs_file.stat().st_size>512*1024**2:
    print('AARIS_EXPORT_LFS_OVER_512_MIB');sys.exit(21)
patch=git(work,'format-patch','--stdout','--binary','-1','HEAD')
if len(patch)>120*1024**2 or b'From ' not in patch[:120]:
    print('AARIS_EXPORT_PATCH_INVALID');sys.exit(22)
package=run/'validated-unity-edits.tar.gz'
with tarfile.open(package,'w:gz',compresslevel=3) as tar:
    import io
    for name,source in [('manifest.json',(run/'manifest.json').read_bytes()),('checkpoint.patch',patch),('one-lfs-object.bin',lfs_file.read_bytes())]:
        info=tarfile.TarInfo(name);info.size=len(source);info.mode=0o600
        tar.addfile(info,io.BytesIO(source))
print('AARIS_EXPORT_EXACT_210_TRACKED_EDITS')
print('tracked_changed_count=210')
print('lfs_changed_count=1')
print('package_bytes='+str(package.stat().st_size))
print('lfs_object_bytes='+str(lfs_file.stat().st_size))
PY
