"""Bounded revisions; setup and render receipts are explicit test doubles."""
import copy
import json
import pytest
from runtime.errors import WorkflowError
from runtime.io import load_data
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, create_visual_project
from runtime.visual_contracts import document_hash
from runtime.visual_planning import current_documents
from runtime.scene_production import PLAN_KINDS
from tests.test_v02_critic import rendered_project, review_for, snapshot
from tests.test_v02_preview import receipt
from tests.test_v02_planning import cli

ACTIONS = [('roughness_variation', 'machine'), ('lighting_intensity', 'lighting'),
           ('lighting_direction', 'lighting'), ('fog_amount', 'atmosphere'),
           ('camera_framing', 'camera'), ('exposure', 'render')]


def ready(tmp_path, actions=None):
    manager, metadata = rendered_project(tmp_path)
    review = review_for(manager, metadata)
    review['recommended_actions'] = [{'action': a, 'scope': s, 'magnitude': 'medium',
                                     'reason': 'Fixture diagnosis'} for a, s in (actions or ACTIONS)]
    manager.submit_render_review(review, expected_version=manager.read()['version'])
    plan = {'schema_version': '0.2', 'project_id': manager.read()['project_id'],
            'scene_version': manager.read()['scene_version'], 'document_id': 'revision_01',
            'revision': 0, 'based_on_review_id': review['document_id'],
            'render_metadata_id': metadata['document_id'], 'pass_index': 1, 'max_preview_passes': 3,
            'actions': [{'action': a, 'scope': s, 'direction': 'increase', 'amount': 'small'}
                        for a, s in (actions or ACTIONS)]}
    return manager, plan


def apply(manager, plan, version=None):
    assert callable(getattr(manager, 'apply_visual_revision', None)), 'Missing Phase 8 bounded revision boundary'
    return manager.apply_visual_revision(plan, expected_version=manager.read()['version'] if version is None else version)


def test_six_actions_immutable_plans_geometry_and_cli(tmp_path, monkeypatch):
    manager, plan = ready(tmp_path)
    before = manager.read(); files = snapshot(manager)
    old = current_documents(manager, before, PLAN_KINDS)
    source = tmp_path / 'revision.json'; source.write_text(json.dumps(plan))
    result = cli('revision-apply', manager.root, '--revision', source, '--expected-version', before['version'])
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state['state'] == 'render_pending' and state['version'] == before['version'] + 1
    assert state['geometry_assets'] == before['geometry_assets'] and state['approvals'] == before['approvals']
    assert state['artifacts']['blockout_plan'] == before['artifacts']['blockout_plan']
    new = current_documents(manager, state, PLAN_KINDS)
    assert next(x for x in new['semantic_material_map']['mappings'] if x['object_id'] == 'machine')['roughness_variation_scale'] == 1.1
    assert new['lookdev_plan']['lighting']['intensity'] == 'high'
    assert new['lookdev_plan']['lighting']['azimuth_offset_degrees'] == 5
    assert new['lookdev_plan']['atmosphere']['amount'] == 'medium'
    assert new['render_plan']['color']['exposure'] == old['render_plan']['color']['exposure'] + .25
    camera = old['render_plan']['camera']
    assert new['render_plan']['camera']['location'] == pytest.approx([t + (p-t)*1.05 for p,t in zip(camera['location'],camera['target'])])
    for kind in PLAN_KINDS[1:]: assert new[kind]['revision'] == old[kind]['revision'] + 1
    record = state['artifacts']['revision_plan'][-1]
    assert load_data(manager.root / record['path']) == plan and record['sha256'] == document_hash(plan)
    for name, data in files.items():
        if name != 'manifest.yaml': assert (manager.root / name).read_bytes() == data
    unchanged = snapshot(manager)
    with pytest.raises(WorkflowError): apply(manager, plan)
    assert snapshot(manager) == unchanged


@pytest.mark.parametrize('problem', ['version', 'project', 'scene', 'review', 'metadata', 'pass', 'revision',
                                    'duplicate', 'scope', 'geometry', 'large', 'unrecommended', 'magnitude',
                                    'review_hash', 'image', 'review_scene', 'review_image', 'review_metadata',
                                    'limit', 'nonobject'])
def test_invalid_revision_is_atomic(tmp_path, problem):
    manager, plan = ready(tmp_path); version = manager.read()['version']
    if problem == 'version': version -= 1
    if problem == 'project': plan['project_id'] = 'another'
    if problem == 'scene': plan['scene_version'] += 1
    if problem == 'review': plan['based_on_review_id'] = 'old'
    if problem == 'metadata': plan['render_metadata_id'] = 'old'
    if problem == 'pass': plan['pass_index'] = 2
    if problem == 'revision': plan['revision'] = 1
    if problem == 'duplicate': plan['actions'].append(copy.deepcopy(plan['actions'][0]))
    if problem == 'scope': plan['actions'][0]['scope'] = 'absent'
    if problem == 'geometry': plan['actions'][0]['action'] = 'regenerate_geometry'
    if problem == 'large': plan['actions'][0]['amount'] = 'large'
    if problem == 'limit': plan['max_preview_passes'] = 1
    if problem == 'nonobject': plan = []
    if problem in ('unrecommended', 'magnitude', 'review_hash', 'review_scene', 'review_image', 'review_metadata'):
        state = manager.read(); record = state['artifacts']['visual_review'][-1]
        review = load_data(manager.root / record['path'])
        if problem == 'unrecommended': review['recommended_actions'].pop(0)
        if problem == 'magnitude': review['recommended_actions'][0]['magnitude'] = 'small'; plan['actions'][0]['amount'] = 'medium'
        if problem == 'review_scene': review['scene_version'] += 1
        if problem == 'review_image': review['image_sha256'] = '0'*64
        if problem == 'review_metadata': review['render_metadata_id'] = 'old'
        if problem == 'review_hash': review['reviewer']['id'] = 'tampered'
        (manager.root / record['path']).write_text(json.dumps(review))
        if problem != 'review_hash':
            record['sha256'] = document_hash(review); manager.path.write_text(json.dumps(state))
    if problem == 'image':
        metadata = current_documents(manager, manager.read(), ('render_metadata',))['render_metadata']
        (manager.root / metadata['image']['path']).write_bytes(b'changed')
    before = snapshot(manager)
    with pytest.raises(WorkflowError): apply(manager, plan, version)
    assert snapshot(manager) == before


def test_legacy_and_plan_only_isolation(tmp_path):
    create_project(tmp_path/'legacy', 'legacy', 'Fixture')
    create_visual_project(tmp_path/'visual', 'visual', 'Fixture')
    for root in (tmp_path/'legacy', tmp_path/'visual'):
        manager = ManifestManager(root); before = snapshot(manager)
        with pytest.raises(WorkflowError): apply(manager, {})
        assert snapshot(manager) == before


def test_failed_attempts_and_reserved_slots_consume_total_budget(tmp_path):
    from runtime.preview_renderer import PreviewRenderer
    manager, plan = ready(tmp_path); apply(manager, plan)
    renderer = PreviewRenderer(manager)
    job = renderer.prepare(); assert job['pass_id'] == 'pass_01'
    receipt(job, False); renderer.complete(job['job'])
    assert renderer.prepare()['pass_id'] == 'pass_02'
    before = snapshot(manager)
    with pytest.raises(WorkflowError): renderer.prepare()
    assert snapshot(manager) == before


def test_two_rounds_and_stricter_limit_cannot_be_relaxed(tmp_path):
    from runtime.preview_renderer import PreviewRenderer
    manager, plan = ready(tmp_path, [('exposure', 'render')]); plan['max_preview_passes'] = 2
    apply(manager, plan)
    renderer = PreviewRenderer(manager); job = renderer.prepare(); receipt(job); metadata = renderer.complete(job['job'])
    review = review_for(manager, metadata); review.update(document_id='review_second', revision=1)
    review['recommended_actions'] = [{'action': 'exposure','scope':'render','magnitude':'small','reason':'Fixture'}]
    manager.submit_render_review(review, expected_version=manager.read()['version'])
    plan.update(document_id='revision_second', revision=1, pass_index=2, based_on_review_id=review['document_id'], render_metadata_id=metadata['document_id'], max_preview_passes=3)
    before = snapshot(manager)
    with pytest.raises(WorkflowError): apply(manager, plan)
    assert snapshot(manager) == before


def test_revision_uses_completed_context_not_stale_packet_guards(tmp_path, monkeypatch):
    manager, plan = ready(tmp_path, [('exposure', 'render')])
    def forbidden(*args, **kwargs): raise AssertionError('Obsolete execution guard used after render')
    monkeypatch.setattr('runtime.preview_renderer.inspect_preview', forbidden)
    monkeypatch.setattr('runtime.scene_production.verify_packet', forbidden)
    assert apply(manager, plan)['state'] == 'render_pending'


def test_worker_parameter_resolution_matches_bounded_visual_controls():
    from runtime.blender_operations import resolved_lighting, resolved_material
    light = {'key_location':[2.,0.,3.], 'fill_location':[0.,2.,4.], 'key_energy':100., 'fill_energy':40., 'world_strength':.5}
    plan = {'intensity':'high', 'azimuth_offset_degrees':45.}
    out = resolved_lighting(light, plan)
    assert out['key_location'] == pytest.approx([2**.5,2**.5,3.])
    assert out['fill_location'] == pytest.approx([-2**.5,2**.5,4.])
    assert out['key_energy'] == 145 and out['fill_energy'] == 58
    material = {'parameters': {'roughness_variation':.2, 'roughness':.5}}
    scaled = resolved_material(material, {'roughness_variation_scale':1.5})
    assert scaled['parameters']['roughness_variation'] == pytest.approx(.3)
    assert material['parameters']['roughness_variation'] == .2 and light['key_location'] == [2.,0.,3.]


def test_prior_explicit_preview_uses_actual_next_pass_index(tmp_path):
    from runtime.preview_renderer import PreviewRenderer
    manager, metadata = rendered_project(tmp_path)
    renderer = PreviewRenderer(manager); job = renderer.prepare(); receipt(job); metadata = renderer.complete(job['job'])
    review = review_for(manager, metadata)
    manager.submit_render_review(review, expected_version=manager.read()['version'])
    plan = {'schema_version':'0.2', 'project_id':manager.read()['project_id'], 'scene_version':1,
            'document_id':'revision_after_manual', 'revision':0, 'based_on_review_id':review['document_id'],
            'render_metadata_id':metadata['document_id'], 'pass_index':2, 'max_preview_passes':3,
            'actions':[{'action':'roughness_variation','scope':'machine','direction':'increase','amount':'small'}]}
    assert apply(manager, plan)['state'] == 'render_pending'
    assert renderer.prepare()['pass_id'] == 'pass_02'
    before = snapshot(manager)
    with pytest.raises(WorkflowError): renderer.prepare()
    assert snapshot(manager) == before


@pytest.mark.parametrize('action,scope,field,value,direction', [
    ('roughness_variation','machine','roughness_variation_scale',2,'increase'),
    ('roughness_variation','machine','roughness_variation_scale',.5,'decrease'),
    ('lighting_direction','lighting','azimuth_offset_degrees',45,'increase'),
    ('lighting_direction','lighting','azimuth_offset_degrees',-45,'decrease'),
    ('lighting_intensity','lighting','intensity','high','increase'),
    ('lighting_intensity','lighting','intensity','low','decrease'),
    ('fog_amount','atmosphere','amount','dense','increase'),
    ('fog_amount','atmosphere','amount','none','decrease'),
    ('exposure','render','exposure',20,'increase'),
    ('exposure','render','exposure',-20,'decrease')])
def test_out_of_bounds_changes_reject_atomically(tmp_path, action, scope, field, value, direction):
    manager, plan = ready(tmp_path, [(action,scope)])
    state=manager.read()
    kind = 'semantic_material_map' if action=='roughness_variation' else 'render_plan' if action=='exposure' else 'lookdev_plan'
    record=state['artifacts'][kind][-1]; doc=load_data(manager.root/record['path'])
    if action=='roughness_variation': target=next(x for x in doc['mappings'] if x['object_id']==scope)
    elif action=='exposure': target=doc['color']
    elif action=='fog_amount': target=doc['atmosphere']
    else: target=doc['lighting']
    target[field]=value
    record['sha256']=document_hash(doc); (manager.root/record['path']).write_text(json.dumps(doc))
    # Keep the explicit render fixture bound to the edited current render plan.
    if kind=='render_plan':
        meta_record=state['artifacts']['render_metadata'][-1]; meta=load_data(manager.root/meta_record['path'])
        meta['render_plan_hash']=document_hash(doc);meta_record['sha256']=document_hash(meta)
        (manager.root/meta_record['path']).write_text(json.dumps(meta))
    manager.path.write_text(json.dumps(state));plan['actions'][0]['direction']=direction
    before=snapshot(manager)
    with pytest.raises(WorkflowError, match='bounded range'): apply(manager,plan)
    assert snapshot(manager)==before


def test_second_revision_preserves_build_and_default_limit(tmp_path):
    from runtime.preview_renderer import PreviewRenderer
    manager,plan=ready(tmp_path,[('exposure','render')]);plan.pop('max_preview_passes')
    apply(manager,plan);first=manager.read();saved=current_documents(manager,first,('revision_plan',))['revision_plan']
    assert saved['max_preview_passes']==3
    renderer=PreviewRenderer(manager);job=renderer.prepare();receipt(job);metadata=renderer.complete(job['job'])
    review=review_for(manager,metadata);review.update(document_id='review_second',revision=1)
    review['recommended_actions']=[{'action':'exposure','scope':'render','magnitude':'medium','reason':'Fixture'}]
    manager.submit_render_review(review,expected_version=manager.read()['version'])
    plan.update(document_id='revision_second',revision=1,pass_index=2,based_on_review_id=review['document_id'],render_metadata_id=metadata['document_id'])
    plan['actions'][0].update(direction='decrease',amount='small')
    result=apply(manager,plan)
    assert len(result['artifacts']['revision_plan'])==2
    render=current_documents(manager,result,('render_plan',))['render_plan']
    assert render['color']['exposure']==0
    final=renderer.prepare();assert final['build_id']==job['build_id'] and final['pass_id']=='pass_02'
    receipt(final);renderer.complete(final['job'])
    before=snapshot(manager)
    with pytest.raises(WorkflowError):renderer.prepare()
    assert snapshot(manager)==before


def test_preexisting_reserved_slot_blocks_revision_atomically(tmp_path):
    manager,plan=ready(tmp_path)
    (manager.root/'stage2/previews/pass_02').mkdir()
    before=snapshot(manager)
    with pytest.raises(WorkflowError,match='budget exhausted'):apply(manager,plan)
    assert snapshot(manager)==before


def test_geometry_recommendation_and_large_magnitude_require_escalation(tmp_path):
    for action,scope,magnitude in [('regenerate_geometry','machine','small'),('exposure','render','large')]:
        manager,plan=ready(tmp_path/action,[(action,scope)])
        state=manager.read();record=state['artifacts']['visual_review'][-1]
        review=load_data(manager.root/record['path']);review['recommended_actions'][0]['magnitude']=magnitude
        record['sha256']=document_hash(review);(manager.root/record['path']).write_text(json.dumps(review));manager.path.write_text(json.dumps(state))
        before=snapshot(manager)
        with pytest.raises(WorkflowError):apply(manager,plan)
        assert snapshot(manager)==before


@pytest.mark.parametrize('pass_index', [1, 2])
def test_occupied_next_slot_rejects_revision_before_writes(tmp_path, pass_index):
    manager, plan = ready(tmp_path)
    (manager.root / 'stage2/previews/pass_01').mkdir()
    plan['pass_index'] = pass_index
    before = snapshot(manager)
    with pytest.raises(WorkflowError):
        apply(manager, plan)
    assert snapshot(manager) == before
