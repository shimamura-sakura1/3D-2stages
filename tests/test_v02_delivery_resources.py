"""Repository upgrades use isolated source copies and labeled render receipt doubles."""
import json
import shutil
from pathlib import Path

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from tests.test_v02_delivery import complete_pass, approve
from tests.test_v02_preview import prepared_project, receipt
from tests.test_v02_critic import review_for, snapshot
from tests.test_v02_planning import ROOT


def isolated_repository(tmp_path, monkeypatch):
    repository=tmp_path/'repository'
    shutil.copytree(ROOT/'styles',repository/'styles')
    shutil.copytree(ROOT/'runtime',repository/'runtime',ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setattr('runtime.scene_production.__file__',str(repository/'runtime/scene_production.py'))
    monkeypatch.setattr('runtime.style_registry.__file__',str(repository/'runtime/style_registry.py'))
    monkeypatch.setattr('runtime.visual_delivery.REPOSITORY',repository)
    return repository


def submit_final_critic(manager,metadata):
    review=review_for(manager,metadata,'final_review_required')
    manager.submit_render_review(review,expected_version=manager.read()['version'])


@pytest.mark.parametrize('resource',['runtime/blender_style_worker.py','styles/industrial_acg_v1/materials/definitions.yaml'])
def test_upgrade_then_new_preview_delivers_both_resource_versions(tmp_path,monkeypatch,resource):
    repository=isolated_repository(tmp_path,monkeypatch); manager=prepared_project(tmp_path/'fixture')
    _,first=complete_pass(manager);old_snapshot=snapshot(manager)
    source=repository/resource;old_hash=sha256(source);source.write_bytes(source.read_bytes()+b'\n# Isolated test upgrade\n');new_hash=sha256(source)
    _,second=complete_pass(manager);submit_final_critic(manager,second)
    from runtime.visual_delivery import final_review_context
    context=final_review_context(manager)
    assert context['snapshot']['pass_id']==second['pass_id']=='pass_01'
    assert first['pass_id']=='pass_00'
    evidence=[load_data(manager.root/r['path']) for r in manager.read()['completion_evidence']]
    archives=[next(r for r in e['repository_resources'] if r['path']==resource) for e in evidence]
    assert [a['sha256'] for a in archives]==[old_hash,new_hash]
    assert archives[0]['archive_path']!=archives[1]['archive_path']
    assert all(sha256(manager.root/a['archive_path'])==a['sha256'] for a in archives)
    assert not any(f['namespace']=='repository' for f in context['snapshot']['files'])
    approve(manager);result=manager.deliver_v02(expected_version=manager.read()['version'])
    package=manager.root/result['package']
    assert all(sha256(package/'project'/a['archive_path'])==a['sha256'] for a in archives)
    for path,data in old_snapshot.items():
        if path!='manifest.yaml':assert (manager.root/path).read_bytes()==data
    assert manager.deliver_v02(expected_version=manager.read()['version'])==result


@pytest.mark.parametrize('target',['current_live','history_archive','current_archive'])
@pytest.mark.parametrize('when',['before','after'])
def test_resource_tamper_rejects_current_or_historical_evidence(tmp_path,monkeypatch,target,when):
    repository=isolated_repository(tmp_path,monkeypatch);manager=prepared_project(tmp_path/'fixture')
    complete_pass(manager)
    source=repository/'runtime/blender_style_worker.py';source.write_bytes(source.read_bytes()+b'\n# upgrade\n')
    _,metadata=complete_pass(manager);submit_final_critic(manager,metadata)
    if when=='after':approve(manager)
    evidence=[load_data(manager.root/r['path']) for r in manager.read()['completion_evidence']]
    if target=='current_live':path=source
    else:
        selected=evidence[0 if target=='history_archive' else -1]
        archive=next(r for r in selected['repository_resources'] if r['path']=='runtime/blender_style_worker.py')
        path=manager.root/archive['archive_path']
    path.write_bytes(path.read_bytes()+b'tampered')
    before=snapshot(manager)
    with pytest.raises(WorkflowError):
        manager.deliver_v02(expected_version=manager.read()['version']) if when=='after' else approve(manager)
    assert snapshot(manager)==before


@pytest.mark.parametrize('existing_history',[False,True])
def test_archive_transaction_failure_rolls_back_all_new_files(tmp_path,monkeypatch,existing_history):
    repository=isolated_repository(tmp_path,monkeypatch);manager=prepared_project(tmp_path/'fixture')
    if existing_history:
        complete_pass(manager)
        worker=repository/'runtime/blender_style_worker.py';worker.write_bytes(worker.read_bytes()+b'\n# upgrade\n')
    import runtime.manifest_manager as module
    real_write=module.atomic_write
    def fail_on_completion(path,value):
        if Path(path).name=='completion-evidence.json':raise OSError('simulated completion publication failure')
        return real_write(path,value)
    # Capture immediately before the formal completion boundary, after proposals.
    from runtime.preview_renderer import PreviewRenderer
    original=PreviewRenderer.complete;captured={}
    def complete_with_failure(self,job_path):
        captured['before']=snapshot(self.manager)
        monkeypatch.setattr(module,'atomic_write',fail_on_completion)
        return original(self,job_path)
    monkeypatch.setattr(PreviewRenderer,'complete',complete_with_failure)
    with pytest.raises((WorkflowError,OSError)):complete_pass(manager)
    assert snapshot(manager)==captured['before']
    assert len(manager.read().get('completion_evidence',[]))==int(existing_history)


def test_archive_collision_is_not_overwritten_or_adopted(tmp_path,monkeypatch):
    repository=isolated_repository(tmp_path,monkeypatch);manager=prepared_project(tmp_path/'fixture')
    worker=repository/'runtime/blender_style_worker.py'
    archive=manager.root/f'stage2/completion-resources/{sha256(worker)}/runtime/blender_style_worker.py'
    archive.parent.mkdir(parents=True,exist_ok=True);archive.write_bytes(b'preexisting conflict')
    from runtime.preview_renderer import PreviewRenderer
    original=PreviewRenderer.complete;captured={}
    def before_completion(self,job_path):
        captured['before']=snapshot(self.manager)
        return original(self,job_path)
    monkeypatch.setattr(PreviewRenderer,'complete',before_completion)
    with pytest.raises(WorkflowError,match='Conflicting immutable'):complete_pass(manager)
    assert snapshot(manager)==captured['before'] and archive.read_bytes()==b'preexisting conflict'
