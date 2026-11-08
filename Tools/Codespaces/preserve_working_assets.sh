#!/usr/bin/env bash
# Authorized owner backup of ACTUAL tracked Unity project changes.
# A separate temp worktree starts from latest origin/main, never touches the
# existing 210 dirty Assets, and never resets, cleans or stashes them.
set -Eeuo pipefail
umask 077
ROOT=/workspaces/Unity-Game-Aris
RUN=/tmp/aaris-codespaces/working-changes-checkpoint
BRANCH=backup/codespace-local-changes-20261108
WORKTREE="$RUN/checkout"
mkdir -p "$RUN"
cd "$ROOT"
test -e .git || { echo AARIS_CHECKPOINT_SOURCE_MISSING; exit 11; }
git rev-parse --is-inside-work-tree | grep -qx true || { echo AARIS_CHECKPOINT_SOURCE_INVALID; exit 12; }
command -v git-lfs >/dev/null 2>&1 || git lfs version >/dev/null 2>&1 || { echo AARIS_CHECKPOINT_LFS_CLI_MISSING; exit 13; }

# The source worktree remains untouched; fetch only remote refs.
if ! git fetch --quiet origin main >/dev/null 2>"$RUN/fetch-private.log"; then
  echo AARIS_CHECKPOINT_FETCH_FAILED
  exit 14
fi
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>"$RUN/remote-private.log"; then
  echo AARIS_CHECKPOINT_BRANCH_ALREADY_EXISTS
  exit 15
fi

python3 - "$ROOT" "$RUN" <<'PYAUDIT'
import collections, hashlib, json, pathlib, re, subprocess, sys
root, run = map(pathlib.Path,sys.argv[1:3])
def git(*args):
    return subprocess.check_output(['git','-C',str(root),*args])
modified=[]
statuses=collections.Counter()
original=git('status','--porcelain=v1','--untracked-files=no','-z')
entries=[v for v in original.split(b'\0') if v]
allowed_root={'Assets','Packages','ProjectSettings','Docs','Tools'}
allowed_suffix={'.mat','.asset','.unity','.prefab','.meta','.shader','.png',
                '.jpg','.jpeg','.tif','.tga','.fbx','.obj','.mtl','.json','.cs',
                '.controller','.anim','.overridecontroller','.asmdef','.uss',
                '.uxml','.terrainlayer','.txt','.md','.hlsl','.compute','.xml'}
categories=collections.Counter()
lfs=[]
source_head=git('rev-parse','HEAD').decode().strip()
main_head=git('rev-parse','refs/remotes/origin/main').decode().strip()
if len(entries)>1500:
    print('AARIS_CHECKPOINT_TOO_MANY_FILES')
    raise SystemExit(16)
def path_blob(ref,path):
    try:
        line=git('ls-tree','-z',ref,'--',path).decode('utf-8').split('\0')[0]
        return line.split('\t')[0].split()[2] if line else None
    except (ValueError,IndexError): return None

for entry in entries:
    state=entry[:2].decode('ascii','replace')
    name=entry[3:].decode('utf-8','strict')
    path=pathlib.PurePosixPath(name)
    if ('\n' in name or '\r' in name or '..' in path.parts or
        len(path.parts)<2 or path.parts[0] not in allowed_root or
        any(p.startswith('.') for p in path.parts) or
        path.suffix.lower() not in allowed_suffix):
        print('AARIS_CHECKPOINT_UNSAFE_PATH_OR_TYPE')
        raise SystemExit(17)
    if state not in (' M','M ','MM',' A','A '):
        print('AARIS_CHECKPOINT_DELETION_OR_RENAME_REVIEW_REQUIRED')
        raise SystemExit(18)
    file=root/path
    if not file.is_file() or file.is_symlink():
        print('AARIS_CHECKPOINT_UNSAFE_FILE_TYPE')
        raise SystemExit(19)
    if file.stat().st_size>600*1024**2:
        print('AARIS_CHECKPOINT_FILE_TOO_LARGE')
        raise SystemExit(20)
    if path.parts[0]=='ProjectSettings':
        # Unity Editor legitimately rewrites more than two tracked settings.
        # Copy them as independent files, never discard or hide them. Keep the
        # strict file-type, size and credential-content gates for public GitHub.
        if len(path.parts)!=2 or path.suffix.lower() not in {'.asset','.txt','.json'}:
            print('AARIS_CHECKPOINT_SETTINGS_UNEXPECTED_TYPE')
            raise SystemExit(21)
        if file.stat().st_size > 12*1024**2:
            print('AARIS_CHECKPOINT_SETTINGS_UNEXPECTED_SIZE')
            raise SystemExit(21)
        blob=file.read_bytes()
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----|'
                     rb'github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|'
                     rb'sk-[A-Za-z0-9]{25,}|xox[baprs]-[A-Za-z0-9-]{20,}',
                     blob):
            print('AARIS_CHECKPOINT_SETTINGS_SECRET_GUARD')
            raise SystemExit(21)
    # A locally changed tracked file must not override a separately changed
    # upstream file. In that case stop and do manual three-way merge.
    if path_blob('HEAD',name)!=path_blob('refs/remotes/origin/main',name):
        print('AARIS_CHECKPOINT_MAIN_CONFLICT_REVIEW_REQUIRED')
        print('conflict_count=1')
        raise SystemExit(22)
    attr=git('check-attr','filter','--',name).decode('utf-8','replace')
    if attr.endswith(': lfs\n'): lfs.append(name)
    raw_hash=hashlib.sha256(file.read_bytes()).hexdigest()
    if re.search(r'(token|password|oauth|secret|credential|\.ulf|\.pem)',name,re.I):
        print('AARIS_CHECKPOINT_POSSIBLE_SECRET_FILE')
        raise SystemExit(23)
    modified.append(dict(path=name,status=state,bytes=file.stat().st_size,
                         sha256=raw_hash, lfs=(name in lfs)))
    categories[path.parts[2] if len(path.parts)>2 and path.parts[1]=='AarisWorld' else '/'.join(path.parts[:2])]+=1
    statuses[state]+=1

if not modified:
    print('AARIS_CHECKPOINT_NO_TRACKED_DIFFERENCES')
    raise SystemExit(24)
# Untracked assets are recorded as a COUNT only and are never pushed without
# a separate review, since untracked folders might include user credentials.
untracked=git('ls-files','--others','--exclude-standard','-z').split(b'\0')
untracked_count=sum(bool(p) for p in untracked)
manifest={
  'kind':'aaris_codespace_working_assets_checkpoint',
  'sourceHead':source_head,'mainHead':main_head,'branch':
  'backup/codespace-local-changes-20261108',
  'changedCount':len(modified),'untrackedExcluded':untracked_count,
  'lfsChangedCount':len(lfs),'categories':dict(sorted(categories.items())),
  'files':modified
}
(run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('AARIS_CHECKPOINT_CHANGES_AUDITED')
print('tracked_changed_count='+str(len(modified)))
print('untracked_review_count='+str(untracked_count))
print('lfs_changed_count='+str(len(lfs)))
print('category_count='+str(len(categories)))
PYAUDIT

if test -d "$WORKTREE"; then
  echo AARIS_CHECKPOINT_TEMP_WORKTREE_ALREADY_EXISTS
  exit 25
fi
# Preserve exact source project: all changes are copied only into a NEW temp
# checkout of current main, so prior PR #159/#166/#169 commits are retained.
GIT_LFS_SKIP_SMUDGE=1 git -c filter.lfs.process= \
 -c filter.lfs.smudge=cat -c filter.lfs.required=false \
 worktree add --detach "$WORKTREE" refs/remotes/origin/main \
 > /dev/null 2>"$RUN/worktree-private.log" || {
  echo AARIS_CHECKPOINT_TEMP_WORKTREE_CREATION_FAILED
  exit 26
}
python3 - "$ROOT" "$WORKTREE" "$RUN/manifest.json" <<'PYCOPY'
import hashlib,json,os,pathlib,shutil,subprocess,sys
source,worktree,manifest=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3])
data=json.loads(manifest.read_text())
bytes_total=0
for record in data['files']:
    relative=pathlib.Path(record['path'])
    original=source/relative
    dest=worktree/relative
    if original.is_symlink() or dest.is_symlink() or not original.is_file():
        print('AARIS_CHECKPOINT_SOURCE_CHANGED')
        raise SystemExit(27)
    actual=hashlib.sha256(original.read_bytes()).hexdigest()
    if actual != record['sha256']:
        print('AARIS_CHECKPOINT_SOURCE_MODIFIED_DURING_CAPTURE')
        raise SystemExit(28)
    bytes_total += original.stat().st_size
    if bytes_total > 28*1024**3:
        print('AARIS_CHECKPOINT_COPY_TOO_LARGE')
        raise SystemExit(29)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(original,dest)
print('AARIS_CHECKPOINT_SAFE_FILES_COPIED')
print('copied_file_count='+str(len(data['files'])))
PYCOPY

# git add uses the original repository attributes and active Git LFS filters.
python3 - "$WORKTREE" "$RUN/manifest.json" <<'PYSTAGE'
import json,subprocess,sys
worktree,manifest=sys.argv[1:]
paths=[x['path'] for x in json.load(open(manifest))['files']]
process=subprocess.run(['git','-C',worktree,'add','--',*paths],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if process.returncode:
    print('AARIS_CHECKPOINT_GIT_ADD_FAILED')
    raise SystemExit(30)
staged=subprocess.check_output(['git','-C',worktree,'diff','--cached','--name-only','-z']).split(b'\0')
count=sum(bool(s) for s in staged)
if count != len(paths):
    print('AARIS_CHECKPOINT_STAGED_FILES_MISMATCH')
    raise SystemExit(31)
print('AARIS_CHECKPOINT_ALL_TRACKED_EDITS_STAGED')
print('staged_file_count='+str(count))
PYSTAGE

if ! GIT_AUTHOR_NAME="Aaris Codespace Changes" \
     GIT_AUTHOR_EMAIL="codespace-recovery@users.noreply.github.com" \
     GIT_COMMITTER_NAME="Aaris Codespace Changes" \
     GIT_COMMITTER_EMAIL="codespace-recovery@users.noreply.github.com" \
     git -C "$WORKTREE" commit -qm \
     "assets(unity): preserve reviewed Codespace working changes" \
     > /dev/null 2>"$RUN/commit-private.log"; then
  echo AARIS_CHECKPOINT_GIT_COMMIT_FAILED
  exit 32
fi
COMMIT="$(git -C "$WORKTREE" rev-parse HEAD)"
printf 'checkpoint_sha=%s\n' "$COMMIT"
# New LFS object pointer commits must never be pushed before their blobs.
if python3 - "$RUN/manifest.json" <<'PYLFS'
import json,sys
sys.exit(0 if json.load(open(sys.argv[1]))['lfsChangedCount'] else 1)
PYLFS
then
  if ! GIT_TERMINAL_PROMPT=0 timeout 420 git -C "$WORKTREE" lfs push origin HEAD \
     >/dev/null 2>"$RUN/lfs-private.log"; then
    echo AARIS_CHECKPOINT_LFS_PUSH_FAILED
    exit 33
  fi
  echo AARIS_CHECKPOINT_LFS_OBJECTS_PUSHED
else
  echo AARIS_CHECKPOINT_NO_NEW_LFS_OBJECTS
fi

if ! timeout 200 env GIT_TERMINAL_PROMPT=0 \
    git -C "$WORKTREE" push origin "HEAD:refs/heads/$BRANCH" \
    >/dev/null 2>"$RUN/push-private.log"; then
  # The local commit and manifest persist in /tmp to permit explicit retry,
  # but no false claim of a successful GitHub push is emitted.
  echo AARIS_CHECKPOINT_GITHUB_PUSH_FAILED
  exit 34
fi
echo AARIS_CHECKPOINT_REMOTE_BRANCH_PUSHED
echo 'checkpoint_branch=backup/codespace-local-changes-20261108'
echo "checkpoint_sha=$COMMIT"
echo AARIS_CHECKPOINT_ORIGINAL_WORKTREE_UNTOUCHED
