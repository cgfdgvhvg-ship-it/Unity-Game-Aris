#!/usr/bin/env bash
# Resume the ALREADY CREATED Unity-asset snapshot in the SAME Codespace.
# Never stage/checkout/reset anything in /workspaces/Unity-Game-Aris.
set -Eeuo pipefail
umask 077
ROOT=/workspaces/Unity-Game-Aris
RUN=/tmp/aaris-codespaces/working-changes-checkpoint
WORKTREE="$RUN/checkout"
BRANCH=backup/codespace-local-changes-20261108
MANIFEST="$RUN/manifest.json"
test -e "$ROOT/.git" && test -d "$WORKTREE" && test -s "$MANIFEST" || {
  echo AARIS_RETRY_SNAPSHOT_MISSING; exit 11;
}
command -v flock >/dev/null || { echo AARIS_RETRY_LOCK_TOOL_MISSING; exit 12; }
exec 9>"$RUN/retry.lock"
flock -n 9 || { echo AARIS_RETRY_ALREADY_RUNNING; exit 13; }

# Only the originally captured, named, tracked project edits; no new files.
python3 - "$ROOT" "$WORKTREE" "$MANIFEST" "$BRANCH" <<'PYVERIFY'
import hashlib,json,pathlib,subprocess,sys,re
source,worktree,manifest,branch=map(str,sys.argv[1:])
d=json.loads(pathlib.Path(manifest).read_text())
if d.get('kind')!='aaris_codespace_working_assets_checkpoint' or d.get('branch')!=branch:
    print('AARIS_RETRY_MANIFEST_INVALID');sys.exit(14)
files=d.get('files')
if not isinstance(files,list) or len(files)!=d.get('changedCount') or len(files)!=210:
    print('AARIS_RETRY_SNAPSHOT_COUNT_MISMATCH');sys.exit(15)
def git(*args):
    return subprocess.check_output(['git','-C',worktree,*args],stderr=subprocess.DEVNULL).decode().strip()
def source_git(*args):
    return subprocess.check_output(['git','-C',source,*args],stderr=subprocess.DEVNULL).decode().strip()
head=git('rev-parse','HEAD')
parent=git('rev-parse','HEAD^')
if len(head)!=40 or parent!=d.get('mainHead') or source_git('rev-parse','HEAD')!=d.get('sourceHead'):
    print('AARIS_RETRY_SNAPSHOT_BASE_CHANGED');sys.exit(16)
if source_git('status','--porcelain=v1','--untracked-files=no','-z')=='':
    print('AARIS_RETRY_SOURCE_UNEXPECTEDLY_CLEAN');sys.exit(17)
staged=subprocess.check_output(
    ['git','-C',worktree,'diff-tree','--no-commit-id','--name-only','-r','-z','HEAD'],
    stderr=subprocess.DEVNULL
).decode('utf-8','replace').split('\0')
staged=sorted(filter(None,staged))
planned=sorted(r['path'] for r in files)
if planned!=staged or len(set(planned))!=len(planned):
    print('AARIS_RETRY_COMMITTED_FILES_MISMATCH');sys.exit(18)
if subprocess.check_output(['git','-C',worktree,'status','--porcelain=v1','--untracked-files=no'],
                           stderr=subprocess.DEVNULL).strip():
    print('AARIS_RETRY_TEMP_WORKTREE_DIRTY');sys.exit(19)
lfs=[r for r in files if r['lfs']]
if len(lfs)!=1 or d.get('lfsChangedCount')!=1:
    print('AARIS_RETRY_LFS_COUNT_REVIEW_REQUIRED');sys.exit(20)
for r in files:
    src=pathlib.Path(source)/r['path']
    if not src.is_file() or src.is_symlink() or src.stat().st_size!=r['bytes'] or \
        hashlib.sha256(src.read_bytes()).hexdigest()!=r['sha256']:
        print('AARIS_RETRY_ORIGINAL_FILE_CHANGED_SINCE_CHECKPOINT');sys.exit(21)
name=lfs[0]['path']
blob=subprocess.check_output(['git','-C',worktree,'show','HEAD:'+name],
                             stderr=subprocess.DEVNULL).decode('ascii','replace')
match=re.search(r'^oid sha256:([0-9a-f]{64})$',blob,re.M)
if not match or not blob.startswith('version https://git-lfs.github.com/spec/v1'):
    print('AARIS_RETRY_CHANGED_LFS_POINTER_MISSING');sys.exit(22)
pathlib.Path(manifest).parent.joinpath('one-lfs-object-id').write_text(match.group(1)+'\n')
print('AARIS_RETRY_CHECKPOINT_COMMIT_VERIFIED')
print('tracked_changed_count='+str(len(files)))
print('lfs_changed_count=1')
print('checkpoint_sha='+head)
PYVERIFY

OID="$(cat "$RUN/one-lfs-object-id")"
[[ "$OID" =~ ^[0-9a-f]{64}$ ]] || { echo AARIS_RETRY_LFS_HASH_INVALID; exit 23; }

# The prior failure came from 'lfs push origin HEAD', which may traverse the
# ENTIRE preexisting LFS history. Upload ONLY the one new changed object.
if ! timeout 360 env GIT_TERMINAL_PROMPT=0 \
    git -C "$WORKTREE" lfs push --object-id origin "$OID" \
    >"$RUN/lfs-retry-private-stdout.log" 2>"$RUN/lfs-retry-private-stderr.log"; then
    python3 - "$RUN/lfs-retry-private-stdout.log" "$RUN/lfs-retry-private-stderr.log" <<'PYERR'
import re,sys,pathlib
data='\n'.join(pathlib.Path(p).read_text(errors='replace')[-30000:] for p in sys.argv[1:])
patterns=[
 ('AUTH_DENIED',r'authentication required|not authorized|HTTP 401|access denied|HTTP 403|forbidden|permission denied'),
 ('QUOTA',r'bandwidth quota|storage quota|billing|LFS quota|quota exceeded'),
 ('MISSING_LOCAL_OBJECT',r'file does not exist|no such file|does not exist locally|missing.*object'),
 ('LFS_SERVER_ERROR',r'HTTP 5\d\d|server error|Internal Server Error'),
 ('NETWORK',r'Could not resolve host|timeout|connection reset|TLS handshake|network is unreachable'),
 ('INVALID_BATCH',r'batch response|invalid oid|unsupported protocol'),
]
for label,pattern in patterns:
    if re.search(pattern,data,re.I):
        print('AARIS_RETRY_LFS_ERROR_'+label)
        break
else:
    print('AARIS_RETRY_LFS_ERROR_OTHER')
PYERR
    exit 24
fi
echo AARIS_RETRY_ONE_LFS_OBJECT_UPLOADED

# The immutable checkpoint commit remains unchanged. Publish the branch only
# once the exact new LFS object was uploaded successfully.
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo AARIS_RETRY_REMOTE_BRANCH_ALREADY_EXISTS_REVIEW_REQUIRED
  exit 25
fi
if ! timeout 240 env GIT_TERMINAL_PROMPT=0 \
     git -C "$WORKTREE" push origin "HEAD:refs/heads/$BRANCH" \
     >"$RUN/git-push-private-stdout.log" 2>"$RUN/git-push-private-stderr.log"; then
  python3 - "$RUN/git-push-private-stderr.log" <<'PYPUSH'
import pathlib,re,sys
s=pathlib.Path(sys.argv[1]).read_text(errors='replace')[-12000:]
if re.search(r'403|permission denied|write access|not authorized|authentication failed',s,re.I):
    print('AARIS_RETRY_GIT_PUSH_AUTH_DENIED')
elif re.search(r'protected|rejected|non-fast-forward',s,re.I):
    print('AARIS_RETRY_GIT_PUSH_REJECTED')
else:
    print('AARIS_RETRY_GIT_PUSH_FAILED')
PYPUSH
  exit 26
fi
echo AARIS_RETRY_GITHUB_BRANCH_PUSHED
echo 'checkpoint_branch=backup/codespace-local-changes-20261108'
git -C "$WORKTREE" rev-parse HEAD | sed 's/^/checkpoint_sha=/'
echo AARIS_RETRY_SOURCE_WORKTREE_PRESERVED
