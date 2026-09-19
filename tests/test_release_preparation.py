"""Exercise release safeguards in a real disposable repository and worktree."""
import subprocess
from pathlib import Path

import pytest


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args], text=True).strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path/'dev'
    root.mkdir()
    git(root,'init','-b','dev/v3')
    git(root,'config','user.name','Release Test')
    git(root,'config','user.email','release@example.invalid')
    (root/'SKILL.md').write_text('skill')
    (root/'old.txt').write_text('old release file')
    (root/'.gitignore').write_text('.deps/\nprojects/\n')
    git(root,'add','.')
    git(root,'commit','-m','fixture')
    target=tmp_path/'main'
    git(root,'worktree','add','-b','main',str(target))
    return root,target


def test_release_preserves_private_files_and_source(repository, monkeypatch):
    from scripts import prepare_release as module
    root,target=repository
    (target/'projects').mkdir()
    private=target/'projects/user.blend'
    private.write_bytes(b'private scene')
    def export(source,destination):
        destination.mkdir()
        (destination/'SKILL.md').write_text('new published skill')
    monkeypatch.setattr(module,'export_production',export)
    monkeypatch.setattr(module,'selected_files',lambda root:['SKILL.md'])
    receipt=module.prepare(root,target)
    assert receipt['source_commit']==git(root,'rev-parse','HEAD')
    assert (target/'SKILL.md').read_text()=='new published skill'
    assert not (target/'old.txt').exists()
    assert private.read_bytes()==b'private scene'
    assert (root/'old.txt').read_text()=='old release file'
    assert git(root,'status','--porcelain','--untracked-files=no')==''


def test_wrong_branch_or_dirty_target_rejects(repository):
    from scripts.prepare_release import prepare
    root,target=repository
    (target/'SKILL.md').write_text('user edit')
    with pytest.raises(ValueError,match='uncommitted'):
        prepare(root,target)
    assert (target/'SKILL.md').read_text()=='user edit'
    with pytest.raises(ValueError,match='main'):
        prepare(root,root)


def test_untracked_output_collision_rejects_without_removals(repository,monkeypatch):
    from scripts import prepare_release as module
    root,target=repository
    (target/'new.txt').write_text('user note')
    def export(source,destination):
        destination.mkdir()
        (destination/'new.txt').write_text('release')
    monkeypatch.setattr(module,'export_production',export)
    monkeypatch.setattr(module,'selected_files',lambda root:['SKILL.md'])
    with pytest.raises(ValueError,match='untracked'):
        module.prepare(root,target)
    assert (target/'new.txt').read_text()=='user note'
    assert (target/'old.txt').exists()


def test_uncommitted_source_and_untracked_selected_resources_reject(repository,monkeypatch):
    from scripts import prepare_release as module
    root,target=repository
    monkeypatch.setattr(module,'selected_files',lambda root:['untracked.txt'])
    with pytest.raises(ValueError,match='untracked'):
        module.prepare(root,target)
    (root/'SKILL.md').write_text('not committed')
    with pytest.raises(ValueError,match='uncommitted'):
        module.prepare(root,target)
