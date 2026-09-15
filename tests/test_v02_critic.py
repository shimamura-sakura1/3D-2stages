"""Critic persistence/gates; Blender setup/render receipts are explicit test doubles."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, create_visual_project
from runtime.visual_contracts import document_hash
from tests.test_v02_preview import prepared_project, receipt, png
from tests.test_v02_planning import cli, ROOT

CATEGORIES = ('plasticity', 'material_separation', 'surface_uniformity', 'composition',
              'depth_separation', 'lighting_flatness', 'contact_shadow',
              'atmospheric_depth', 'style_compatibility')


def rendered_project(tmp_path):
    from runtime.preview_renderer import PreviewRenderer
    manager = prepared_project(tmp_path)
    renderer = PreviewRenderer(manager)
    job = renderer.prepare()
    receipt(job)
    metadata = renderer.complete(job['job'])
    return manager, metadata


def review_for(manager, metadata, decision='revision_required'):
    return {'schema_version': '0.2', 'project_id': manager.read()['project_id'],
            'scene_version': manager.read()['scene_version'], 'document_id': 'review_pass_00',
            'revision': 0, 'render_metadata_id': metadata['document_id'],
            'image_sha256': metadata['image']['sha256'], 'reviewer': {'kind': 'codex', 'id': 'codex'},
            'decision': decision, 'categories': {k: {'score': 0.2, 'issues': ['Fixture diagnosis']} for k in CATEGORIES},
            'recommended_actions': [{'action': 'roughness_variation', 'scope': 'machine',
                                     'magnitude': 'small', 'reason': 'Fixture surface diagnosis'}]}


def snapshot(manager):
    return {p.relative_to(manager.root).as_posix(): p.read_bytes()
            for p in manager.root.rglob('*') if p.is_file()}


def test_context_cli_is_read_only_and_contains_rubric(tmp_path):
    manager, metadata = rendered_project(tmp_path)
    before = snapshot(manager)
    result = cli('review-context', manager.root)
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)
    assert context['documents']['render_metadata'] == metadata
    assert len(context['documents']) == 9 and set(context['rubric']['categories']) == set(CATEGORIES)
    assert '0' in context['rubric']['score_semantics'] and '1' in context['rubric']['score_semantics']
    assert context['manifest_version'] == manager.read()['version'] and context['next_review_revision'] == 0
    assert Path(context['image']['absolute_path']).read_bytes() == png()
    assert snapshot(manager) == before


@pytest.mark.parametrize('decision,target', [('revision_required', 'visual_revision'),
                                             ('final_review_required', 'final_review_required')])
def test_submit_cli_records_diagnosis_without_approval(tmp_path, decision, target):
    manager, metadata = rendered_project(tmp_path)
    before = manager.read()
    review = review_for(manager, metadata, decision)
    source = tmp_path / 'review.json'; source.write_text(json.dumps(review))
    result = cli('visual-review-submit', manager.root, '--review', source,
                 '--expected-version', before['version'])
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state['state'] == target and state['version'] == before['version'] + 1
    assert state['geometry_assets'] == before['geometry_assets'] and state['approvals'] == before['approvals']
    record = state['artifacts']['visual_review'][-1]
    assert load_data(manager.root / record['path']) == review and record['sha256'] == document_hash(review)
    assert state['artifacts']['blockout_plan'] == before['artifacts']['blockout_plan']
    from runtime.visual_review import current_render_context
    assert current_render_context(manager)['state'] == target
    unchanged = snapshot(manager)
    with pytest.raises(WorkflowError):
        manager.submit_render_review(review, expected_version=state['version'])
    assert snapshot(manager) == unchanged


@pytest.mark.parametrize('problem', ['version', 'project', 'scene', 'metadata', 'image', 'revision',
                                     'missing_category', 'extra_category', 'score', 'scope', 'decision', 'nonobject'])
def test_invalid_review_rejects_atomically(tmp_path, problem):
    manager, metadata = rendered_project(tmp_path)
    review = review_for(manager, metadata); version = manager.read()['version']
    if problem == 'version': version -= 1
    if problem == 'project': review['project_id'] = 'another_project'
    if problem == 'scene': review['scene_version'] += 1
    if problem == 'metadata': review['render_metadata_id'] = 'old_metadata'
    if problem == 'image': review['image_sha256'] = '0' * 64
    if problem == 'revision': review['revision'] = 1
    if problem == 'missing_category': review['categories'].pop('plasticity')
    if problem == 'extra_category': review['categories']['invented'] = {'score': 0, 'issues': []}
    if problem == 'score': review['categories']['plasticity']['score'] = 1.1
    if problem == 'scope': review['recommended_actions'][0]['scope'] = 'absent'
    if problem == 'decision': review['decision'] = 'approved'
    if problem == 'nonobject': review = []
    before = snapshot(manager)
    assert callable(getattr(manager, 'submit_render_review', None)), 'Missing Phase 7 submission boundary'
    with pytest.raises(WorkflowError): manager.submit_render_review(review, expected_version=version)
    assert snapshot(manager) == before


@pytest.mark.parametrize('kind', ['visual_brief', 'reference_board', 'scene_spec', 'style_assignment',
                                 'blockout_plan', 'semantic_material_map', 'lookdev_plan', 'render_plan',
                                 'render_metadata', 'png', 'missing_png'])
def test_tampered_current_inputs_reject_atomically(tmp_path, kind):
    manager, metadata = rendered_project(tmp_path)
    if kind in ('png', 'missing_png'):
        path = manager.root / metadata['image']['path']
        if kind == 'png': path.write_bytes(png(17, 16))
        else: path.unlink()
    else:
        path = manager.root / manager.read()['artifacts'][kind][-1]['path']; path.write_text('{}')
    before = snapshot(manager)
    from runtime.visual_review import current_render_context
    with pytest.raises(WorkflowError): current_render_context(manager)
    with pytest.raises(WorkflowError):
        manager.submit_render_review(review_for(manager, metadata), expected_version=manager.read()['version'])
    assert snapshot(manager) == before


@pytest.mark.parametrize('problem', ['render_plan_id', 'render_plan_hash', 'style_profile', 'renderer',
                                    'project_id', 'scene_version', 'image_path', 'dimensions', 'failed'])
def test_metadata_links_verified_even_with_matching_index_hash(tmp_path, problem):
    manager, metadata = rendered_project(tmp_path)
    state = manager.read(); record = state['artifacts']['render_metadata'][-1]
    if problem in ('render_plan_id', 'style_profile', 'project_id'): metadata[problem] = 'wrong'
    if problem == 'render_plan_hash': metadata[problem] = '0' * 64
    if problem == 'renderer': metadata['renderer'] = 'eevee' if metadata['renderer'] == 'cycles' else 'cycles'
    if problem == 'scene_version': metadata['scene_version'] += 1
    if problem == 'image_path': metadata['image']['path'] = 'other.png'
    if problem == 'dimensions':
        path = manager.root / metadata['image']['path']; path.write_bytes(png(32, 16)); metadata['image']['sha256'] = sha256(path)
    if problem == 'failed': metadata.update(render_success=False, image=None, error='Fixture failed render')
    record['sha256'] = document_hash(metadata)
    (manager.root / record['path']).write_text(json.dumps(metadata)); manager.path.write_text(json.dumps(state))
    before = snapshot(manager)
    from runtime.visual_review import current_render_context
    with pytest.raises(WorkflowError): current_render_context(manager)
    assert snapshot(manager) == before


@pytest.mark.parametrize('action,scope', [('roughness_variation', 'machine'), ('replace_geometry', 'machine'),
                                         ('regenerate_geometry', 'machine'), ('lighting_intensity', 'lighting'),
                                         ('lighting_direction', 'lighting'), ('fog_amount', 'atmosphere'),
                                         ('camera_framing', 'camera'), ('exposure', 'render')])
def test_action_scopes_are_explicit_and_no_execution(tmp_path, monkeypatch, action, scope):
    manager, metadata = rendered_project(tmp_path)
    review = review_for(manager, metadata); review['recommended_actions'][0].update(action=action, scope=scope)
    def forbidden(*args, **kwargs): raise AssertionError('Critic must not execute Blender or subprocesses')
    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('runtime.scene_production.verify_packet', forbidden)
    monkeypatch.setattr('runtime.preview_renderer.inspect_preview', forbidden)
    bad = copy.deepcopy(review); bad['recommended_actions'][0]['scope'] = 'wrong'
    before = snapshot(manager)
    with pytest.raises(WorkflowError): manager.submit_render_review(bad, expected_version=manager.read()['version'])
    assert snapshot(manager) == before
    state = manager.submit_render_review(review, expected_version=manager.read()['version'])
    assert state['state'] == 'visual_revision'


def test_legacy_plan_only_and_missing_preview_isolation(tmp_path):
    from runtime.visual_review import current_render_context
    legacy = tmp_path / 'legacy'; create_project(legacy, 'legacy', 'Legacy fixture')
    plan = tmp_path / 'plan'; create_visual_project(plan, 'plan', 'Plan fixture')
    ready = prepared_project(tmp_path / 'ready')
    for manager in (ManifestManager(legacy), ManifestManager(plan), ready):
        before = snapshot(manager)
        with pytest.raises(WorkflowError): current_render_context(manager)
        with pytest.raises(WorkflowError): manager.submit_render_review({}, expected_version=manager.read()['version'])
        assert snapshot(manager) == before


def test_prior_review_identity_and_immutable_path_reject(tmp_path):
    manager, metadata = rendered_project(tmp_path)
    review = review_for(manager, metadata)
    state = manager.submit_render_review(review, expected_version=manager.read()['version'])
    # Explicit manifest state fixture for a later pending review, not a workflow execution claim.
    state['state'] = 'render_review_required'; manager.path.write_text(json.dumps(state))
    review['revision'] = 1
    before = snapshot(manager)
    with pytest.raises(WorkflowError): manager.submit_render_review(review, expected_version=state['version'])
    assert snapshot(manager) == before
    review['document_id'] = 'review_pass_01'
    result = manager.submit_render_review(review, expected_version=state['version'])
    assert len(result['artifacts']['visual_review']) == 2
    for path, data in before.items():
        if path != manager.path.relative_to(manager.root).as_posix(): assert (manager.root / path).read_bytes() == data


def test_missing_rubric_rejects_read_only(tmp_path, monkeypatch):
    manager, _ = rendered_project(tmp_path)
    from runtime.style_registry import StyleRegistry
    from runtime.visual_review import current_render_context
    styles = tmp_path / 'styles'; shutil.copytree(ROOT / 'styles', styles)
    (styles / 'industrial_acg_v1/critic/rubric.yaml').unlink()
    monkeypatch.setattr('runtime.visual_review.StyleRegistry', lambda: StyleRegistry(styles))
    before = snapshot(manager)
    with pytest.raises(WorkflowError): current_render_context(manager)
    assert snapshot(manager) == before
