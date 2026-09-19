"""Prepare a consumer tree in a clean main worktree; never commit or push."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.export_production import export_production, selected_files


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


def safe_path(root,relative):
    candidate=root/relative
    if not candidate.resolve().is_relative_to(root) or any(p.is_symlink() for p in [candidate,*candidate.parents] if p!=root and p.is_relative_to(root)):
        raise ValueError('Release path escaped its worktree or uses a link')
    return candidate


def prepare(source,target):
    source,target=Path(source).resolve(),Path(target).resolve()
    if git(source,'branch','--show-current')!='dev/v3':
        raise ValueError('Release source must be dev/v3')
    if source==target or git(target,'branch','--show-current')!='main':
        raise ValueError('Release target must be a separate main worktree')
    if Path(git(source,'rev-parse','--show-toplevel')).resolve()!=source or Path(git(target,'rev-parse','--show-toplevel')).resolve()!=target:
        raise ValueError('Use worktree roots as source and target')
    if git(source,'rev-parse','--path-format=absolute','--git-common-dir')!=git(target,'rev-parse','--path-format=absolute','--git-common-dir'):
        raise ValueError('Source and target must belong to the same Git repository')
    for root in (source,target):
        if git(root,'status','--porcelain','--untracked-files=no'):
            raise ValueError(f'Worktree has uncommitted tracked changes: {root}')
    tracked_source=set(git(source,'ls-files','-z').split('\0'))
    if set(selected_files(source)) - tracked_source:
        raise ValueError('Export would contain untracked source resources')
    scratch=source/'.deps'
    if scratch.is_symlink():
        raise ValueError('Release scratch directory must not be linked')
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-',dir=scratch) as temp:
        temporary=Path(temp).resolve()
        if not temporary.is_relative_to(scratch.resolve()):
            raise ValueError('Temporary release directory escaped source workspace')
        output=temporary/'consumer'
        export_production(source,output)
        published={p.relative_to(output).as_posix():p for p in output.rglob('*') if p.is_file()}
        tracked_target=set(filter(None,git(target,'ls-files','-z').split('\0')))
        for relative in published:
            path=safe_path(target,relative)
            if path.exists() and relative not in tracked_target:
                raise ValueError(f'Release would overwrite an untracked file: {relative}')
        # Validate every target before performing any deletion or replacement.
        for relative in tracked_target:
            safe_path(target,relative)
        removed=sorted(tracked_target-published.keys())
        for relative in removed:
            safe_path(target,relative).unlink(missing_ok=True)
        for relative,path in published.items():
            destination=safe_path(target,relative)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination)
        hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sorted(published.items())}
        receipt={'source_branch':'dev/v3','source_commit':git(source,'rev-parse','HEAD'),'target_branch':'main','target_base':git(target,'rev-parse','HEAD'),'files':len(published),'removed_files':removed,'content_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),'committed':False,'pushed':False}
        (scratch/'last-release-preparation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(prepare(ROOT,args.target),indent=2))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'status':'error','message':str(exc)}))
        return 2


if __name__=='__main__':
    sys.exit(main())
