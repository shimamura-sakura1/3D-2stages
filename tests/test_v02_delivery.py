"""Final gate tests: current-pass Blender/setup/render receipts are explicit doubles."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from runtime.visual_contracts import document_hash
from tests.test_v02_preview import prepared_project, receipt
from tests.test_v02_critic import review_for, snapshot, rendered_project
from tests.test_v02_planning import cli, ROOT


def complete_pass(manager):
    from runtime.preview_renderer import PreviewRenderer
    # Real workers produce a stable initial blockout before reserving render.
    # This fixture supplies those bytes explicitly, never claims Blender ran.
    from runtime.scene_production import PLAN_KINDS
    from runtime.visual_planning import current_documents
    plans = current_documents(manager, manager.read(), PLAN_KINDS)
    geometry = {k: a['versions'][-1] for k,a in manager.read()['geometry_assets'].items()}
    key = document_hash({'geometry_fingerprint_format': 2, 'blockout': plans['blockout_plan'], 'geometry': geometry})
    blockout = manager.root / f'stage2/builds/build_{key[:16]}/blockout.blend'
    blockout.parent.mkdir(parents=True, exist_ok=True)
    if not blockout.exists(): shutil.copy2(ROOT/'styles/industrial_acg_v1/calibration/calibration.blend', blockout)
    renderer = PreviewRenderer(manager); job = renderer.prepare(); packet = load_data(job['packet'])
    setup = Path(packet['outputs']['setup']); setup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(blockout, setup)
    Path(packet['outputs']['receipt']).write_text(json.dumps({'status': 'setup_complete', 'build_id': packet['build_id'], 'inputs_digest': packet['inputs_digest'], 'geometry_before': '1'*64, 'geometry_after': '1'*64, 'blend_sha256': sha256(setup)}))
    receipt(job)
    metadata = renderer.complete(job['job'])
    return job, metadata


def final_ready(tmp_path):
    manager = prepared_project(tmp_path)
    job, metadata = complete_pass(manager)
    manager.submit_render_review(review_for(manager, metadata, 'final_review_required'), expected_version=manager.read()['version'])
    return manager, job, metadata


def approve(manager):
    return manager.final_review_v02('approved', expected_version=manager.read()['version'])


def test_explicit_final_gate_and_deterministic_delivery(tmp_path):
    from runtime.visual_delivery import final_review_context
    manager, job, metadata = final_ready(tmp_path)
    (manager.root/'.env').write_text('SECRET=do-not-copy')
    (manager.root/'unrelated-proposal.json').write_text('{}')
    before = snapshot(manager); context = final_review_context(manager)
    assert snapshot(manager) == before
    assert context['snapshot_sha256'] == document_hash(context['snapshot'])
    assert context['snapshot']['pass_id'] == metadata['pass_id']
    assert len(context['snapshot']['documents']) == 10
    assert context['reviewable_files'] and not any(a['scope']=='final' for a in manager.read()['approvals'])
    with pytest.raises(WorkflowError): manager.deliver_v02(expected_version=manager.read()['version'])
    approved = approve(manager)
    assert approved['state'] == 'approved' and approved['approvals'][-1]['reviewer'] == 'user'
    assert context['snapshot_sha256'] in approved['approvals'][-1]['artifact_hashes']
    result = manager.deliver_v02(expected_version=approved['version'])
    assert manager.read()['state'] == 'delivered'
    package = manager.root/result['package']; inventory = load_data(package/'inventory.json')
    assert sha256(package/'inventory.json') == result['inventory_sha256']
    assert (package/'project'/metadata['image']['path']).is_file()
    assert (package/'project'/Path(load_data(job['packet'])['outputs']['setup']).relative_to(manager.root)).is_file()
    assert all(sha256(package/r['path'])==r['sha256'] for r in inventory['files'])
    assert not any('.env' in r['path'] or 'unrelated-proposal' in r['path'] for r in inventory['files'])
    assert (package/'provenance.json').is_file() and (package/'approved-manifest.json').is_file()
    before = snapshot(manager)
    assert manager.deliver_v02(expected_version=manager.read()['version']) == result
    assert snapshot(manager) == before
    with pytest.raises(WorkflowError): manager.deliver_v02(expected_version=approved['version'])
    assert snapshot(manager) == before


@pytest.mark.parametrize('when', ['before', 'after'])
@pytest.mark.parametrize('target', ['visual_brief','reference_board','scene_spec','style_assignment','blockout_plan','semantic_material_map','lookdev_plan','render_plan','render_metadata','visual_review','png','blend','receipt','packet','worker','intent','completion','surface','geometry','reference','blend_receipt'])
def test_tamper_refuses_atomically(tmp_path, when, target):
    manager, job, metadata = final_ready(tmp_path); packet = load_data(job['packet'])
    if when == 'after': approve(manager)
    state = manager.read()
    if target in state['artifacts']: path = manager.root/state['artifacts'][target][-1]['path']
    elif target == 'png': path = manager.root/metadata['image']['path']
    elif target in ('blend', 'blend_receipt'): path = Path(packet['outputs']['setup'])
    elif target == 'receipt': path = Path(packet['outputs']['receipt'])
    elif target in ('packet','intent'): path = Path(job[target])
    elif target == 'worker': path = Path(job['receipt'])
    elif target == 'completion': path = manager.root/state['completion_evidence'][-1]['path']
    elif target == 'reference':
        board = load_data(manager.root/state['artifacts']['reference_board'][-1]['path']); path = manager.root/board['references'][0]['path']
    else:
        results = [a['versions'][-1] for a in state['geometry_assets'].values()]
        path = manager.root/next(r['surface_sources'][0]['path'] if target=='surface' else r['geometry']['model'] for r in results if r['geometry']['model'])
    path.write_bytes(path.read_bytes()+b'changed')
    if target == 'blend_receipt':
        setup = Path(packet['outputs']['receipt']); value = load_data(setup); value['blend_sha256'] = sha256(path); setup.write_text(json.dumps(value))
    before = snapshot(manager)
    with pytest.raises(WorkflowError):
        manager.deliver_v02(expected_version=state['version']) if when=='after' else approve(manager)
    assert snapshot(manager) == before


def test_missing_completion_and_no_backfill(tmp_path):
    manager, metadata = rendered_project(tmp_path)
    manager.submit_render_review(review_for(manager,metadata,'final_review_required'),expected_version=manager.read()['version'])
    before = snapshot(manager)
    assert not manager.read().get('completion_evidence')
    with pytest.raises(WorkflowError): approve(manager)
    assert snapshot(manager)==before


def test_rejection_allows_one_new_concrete_diagnosis_then_bounded_revision(tmp_path):
    manager, job, metadata = final_ready(tmp_path)
    rejected = manager.final_review_v02('rejected',expected_version=manager.read()['version'])
    assert rejected['state']=='visual_revision' and rejected['approvals'][-1]['decision']=='rejected'
    rejected_snapshot = snapshot(manager)
    bad = review_for(manager, metadata, 'final_review_required'); bad.update(document_id='new_diagnosis',revision=1)
    with pytest.raises(WorkflowError): manager.submit_render_review(bad,expected_version=manager.read()['version'])
    assert snapshot(manager)==rejected_snapshot
    bad['decision']='revision_required'; bad['recommended_actions']=[]
    with pytest.raises(WorkflowError): manager.submit_render_review(bad,expected_version=manager.read()['version'])
    review = review_for(manager,metadata); review.update(document_id='new_diagnosis',revision=1)
    manager.submit_render_review(review,expected_version=manager.read()['version'])
    with pytest.raises(WorkflowError): manager.submit_render_review(review,expected_version=manager.read()['version'])
    plan = {'schema_version':'0.2','project_id':manager.read()['project_id'],'scene_version':manager.read()['scene_version'],'document_id':'revision_after_rejection','revision':0,'based_on_review_id':review['document_id'],'render_metadata_id':metadata['document_id'],'pass_index':1,'max_preview_passes':3,'actions':[{'action':'roughness_variation','scope':'machine','direction':'increase','amount':'small'}]}
    manager.apply_visual_revision(plan,expected_version=manager.read()['version'])
    assert manager.read()['state']=='render_pending'
    assert len(manager.read()['artifacts']['visual_review'])==2 and len(manager.read()['final_reviews'])==1
    for path,data in rejected_snapshot.items():
        if path!='manifest.yaml': assert (manager.root/path).read_bytes()==data


def test_copy_failure_and_conflicting_package_are_atomic(tmp_path, monkeypatch):
    manager, _, _ = final_ready(tmp_path); approve(manager); before = snapshot(manager)
    def fail(*args,**kwargs): raise OSError('simulated copy failure')
    with monkeypatch.context() as mp:
        mp.setattr('runtime.visual_delivery.shutil.copy2', fail)
        with pytest.raises(WorkflowError): manager.deliver_v02(expected_version=manager.read()['version'])
    assert snapshot(manager)==before
    result=manager.deliver_v02(expected_version=manager.read()['version'])
    (manager.root/result['package']/'provenance.json').write_text('{}')
    corrupted=snapshot(manager)
    with pytest.raises(WorkflowError): manager.deliver_v02(expected_version=manager.read()['version'])
    assert snapshot(manager)==corrupted


def test_cli_and_strict_optional_indexes(tmp_path):
    manager, _, _ = final_ready(tmp_path)
    guide=(ROOT/'docs/v02/delivery.md').read_text(); assert 'final-review-context' in guide
    r=cli('final-review-context',manager.root); assert r.returncode==0,r.stderr
    version=manager.read()['version']
    r=cli('final-review-v02',manager.root,'--decision','approved','--expected-version',version); assert r.returncode==0,r.stderr
    r=cli('deliver-v02',manager.root,'--expected-version',version+1); assert r.returncode==0,r.stderr
    from runtime.validators import validate_manifest,validate_contract
    bad=copy.deepcopy(manager.read()); bad['completion_evidence'][0]['unexpected']=True
    with pytest.raises(WorkflowError): validate_manifest(bad)
    for name,key in [('completion_evidence','completion_evidence'),('final_snapshot','final_reviews')]:
        doc=load_data(manager.root/manager.read()[key][-1]['path']); validate_contract(name,doc)
        doc['unexpected']=True
        with pytest.raises(WorkflowError):validate_contract(name,doc)


@pytest.mark.parametrize('case',['legacy','plan_only','pending','failed','revision','stale_version','stale_critic'])
def test_default_and_pending_states_never_approve(tmp_path,case):
    from runtime.visual_delivery import final_review_context
    from runtime.manifest_manager import ManifestManager
    from runtime.planning import create_project,create_visual_project
    from runtime.preview_renderer import PreviewRenderer
    if case=='legacy':
        create_project(tmp_path/'legacy','legacy','fixture'); manager=ManifestManager(tmp_path/'legacy')
    elif case=='plan_only':
        create_visual_project(tmp_path/'plan','plan','fixture'); manager=ManifestManager(tmp_path/'plan')
    elif case in ('pending','failed'):
        manager=prepared_project(tmp_path); renderer=PreviewRenderer(manager); job=renderer.prepare()
        if case=='failed':receipt(job,False);renderer.complete(job['job'])
    else:
        manager,job,metadata=final_ready(tmp_path)
        if case=='revision':manager.final_review_v02('rejected',expected_version=manager.read()['version'])
        if case=='stale_critic':
            state=manager.read();record=state['artifacts']['visual_review'][-1];path=manager.root/record['path']
            review=load_data(path);review['render_metadata_id']='stale_metadata';record['sha256']=document_hash(review)
            path.write_text(json.dumps(review));manager.path.write_text(json.dumps(state))
    version=manager.read()['version'];before=snapshot(manager)
    if case!='stale_version':
        with pytest.raises(WorkflowError): final_review_context(manager)
    with pytest.raises(WorkflowError):manager.final_review_v02('approved',expected_version=version-1 if case=='stale_version' else version)
    with pytest.raises(WorkflowError):manager.deliver_v02(expected_version=version)
    assert snapshot(manager)==before


def test_latest_pass_history_and_rejection_snapshot_delivered(tmp_path):
    manager,job,metadata=final_ready(tmp_path)
    manager.final_review_v02('rejected',expected_version=manager.read()['version'])
    review=review_for(manager,metadata);review.update(document_id='post_rejection',revision=1)
    manager.submit_render_review(review,expected_version=manager.read()['version'])
    revision={'schema_version':'0.2','project_id':manager.read()['project_id'],'scene_version':manager.read()['scene_version'],'document_id':'revision_after_rejection','revision':0,'based_on_review_id':review['document_id'],'render_metadata_id':metadata['document_id'],'pass_index':1,'max_preview_passes':3,'actions':[{'action':'roughness_variation','scope':'machine','direction':'increase','amount':'small'}]}
    manager.apply_visual_revision(revision,expected_version=manager.read()['version'])
    job2,metadata2=complete_pass(manager)
    review2=review_for(manager,metadata2,'final_review_required');review2.update(document_id='review_pass_01',revision=2)
    manager.submit_render_review(review2,expected_version=manager.read()['version'])
    from runtime.visual_delivery import final_review_context
    value=final_review_context(manager)['snapshot']
    assert value['pass_id']=='pass_01' and value['image']==metadata2['image']['path']
    assert len(manager.read()['completion_evidence'])==2
    approve(manager);result=manager.deliver_v02(expected_version=manager.read()['version'])
    package=manager.root/result['package']
    for record in manager.read()['final_reviews']:
        assert (package/'project'/record['path']).is_file()
    assert (package/'project'/metadata['image']['path']).is_file()
    assert (package/'project'/metadata2['image']['path']).is_file()
    assert (package/'project'/Path(load_data(job2['packet'])['outputs']['setup']).relative_to(manager.root)).is_file()


@pytest.mark.parametrize('target',['setup_missing','receipt_missing','receipt_geometry','worker_geometry','wrong_inputs','missing_blockout'])
def test_completion_requires_matching_current_setup(tmp_path,target):
    manager=prepared_project(tmp_path)
    from runtime.preview_renderer import PreviewRenderer
    from runtime.scene_production import prepare_scene
    initial=load_data(prepare_scene(manager)['packet'])
    blockout=Path(initial['outputs']['blockout']);blockout.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'styles/industrial_acg_v1/calibration/calibration.blend',blockout)
    renderer=PreviewRenderer(manager);job=renderer.prepare();packet=load_data(job['packet'])
    setup=Path(packet['outputs']['setup']);setup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(blockout,setup)
    value={'status':'setup_complete','build_id':packet['build_id'],'inputs_digest':packet['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(setup)}
    setup_receipt=Path(packet['outputs']['receipt']);setup_receipt.write_text(json.dumps(value));worker=receipt(job)
    if target=='setup_missing':setup.unlink()
    if target=='receipt_missing':setup_receipt.unlink()
    if target=='missing_blockout':blockout.unlink()
    if target=='receipt_geometry':value['geometry_before']='2'*64;setup_receipt.write_text(json.dumps(value))
    if target=='wrong_inputs':value['inputs_digest']='2'*64;setup_receipt.write_text(json.dumps(value))
    if target=='worker_geometry':worker['geometry_digest']='2'*64;Path(job['receipt']).write_text(json.dumps(worker))
    before=snapshot(manager)
    with pytest.raises(WorkflowError):renderer.complete(job['job'])
    assert snapshot(manager)==before


def test_unregistered_package_collision_and_mid_copy_tamper(tmp_path,monkeypatch):
    manager,_,metadata=final_ready(tmp_path);approve(manager)
    from runtime.visual_delivery import validate_approved,delivery_inputs,raw_hash
    state=manager.read();value=validate_approved(manager,state);inventory,_,_=delivery_inputs(manager,state,value)
    conflict=manager.root/'delivery'/raw_hash(inventory);conflict.mkdir(parents=True);(conflict/'prior.txt').write_text('keep')
    before=snapshot(manager)
    with pytest.raises(WorkflowError):manager.deliver_v02(expected_version=state['version'])
    assert snapshot(manager)==before
    shutil.rmtree(conflict)
    original=shutil.copy2;mutated=False;image=manager.root/metadata['image']['path']
    def change_after_copy(source,destination):
        nonlocal mutated
        result=original(source,destination)
        if not mutated:image.write_bytes(image.read_bytes()+b'tampered');mutated=True
        return result
    before_manifest=manager.path.read_bytes()
    monkeypatch.setattr('runtime.visual_delivery.shutil.copy2',change_after_copy)
    with pytest.raises(WorkflowError):manager.deliver_v02(expected_version=state['version'])
    assert manager.path.read_bytes()==before_manifest and not list((manager.root/'delivery').iterdir())


def test_worker_role_and_missing_registered_package_refuse(tmp_path):
    from runtime.manifest_manager import ManifestManager
    manager,_,_=final_ready(tmp_path);worker=ManifestManager(manager.root,role='worker');before=snapshot(manager)
    with pytest.raises(WorkflowError):worker.final_review_v02('approved',expected_version=manager.read()['version'])
    with pytest.raises(WorkflowError):worker.deliver_v02(expected_version=manager.read()['version'])
    assert snapshot(manager)==before
    approve(manager);result=manager.deliver_v02(expected_version=manager.read()['version'])
    shutil.rmtree(manager.root/result['package']);before=snapshot(manager)
    with pytest.raises(WorkflowError):manager.deliver_v02(expected_version=manager.read()['version'])
    assert snapshot(manager)==before


def test_router_final_review_and_rejection_loop_are_explicit():
    """Declared Router edges must carry a critic result to delivery and back to revision."""
    import re
    router=(ROOT/'SKILL.md').read_text().split('## Execution Router',1)[1].split('\n## ',1)[0]
    steps={}
    for chunk in re.split(r'\n### Step ',router)[1:]:
        identity=chunk.split(' — ',1)[0]
        if identity not in {'6','6V','7V','8V'}: continue
        next_section=chunk.split('\nNext:\n',1)[1]
        steps[identity]=set(re.findall(r'^- (?:Step )?([A-Za-z0-9_-]+)\s*$',next_section,re.M))
    # The critic's final_review_required result must reach Step 6 directly.
    assert '6' in steps['7V'], 'A final-review critic currently has no declared final user review route'
    # Rejection must diagnose a NEW concrete correction before applying it.
    # Approval still terminates with delivery; rejection is not sent directly to 8V.
    assert '7V' in steps['6'], 'Final rejection currently has no declared new-diagnosis route'
    assert '8V' not in steps['6'], 'Final rejection must receive a fresh bounded diagnosis first'
    for route in [('7V','6','END'),('6','7V','8V','6V','7V','6','END')]:
        for source,target in zip(route,route[1:]):
            assert target in steps[source], f'Missing explicit Router edge {source} -> {target}'
