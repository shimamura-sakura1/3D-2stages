"""User-package behavior. BLENDER headers below are file-validation doubles only."""
import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from runtime.manifest_manager import ManifestManager
from runtime.style_registry import StyleRegistry
from tests.test_v02_planning import ROOT, cli, proposal


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding='utf-8')


def package(tmp_path, *, reviewed=True, resources=True, version='2.3.4'):
    folder = tmp_path / 'external-style'
    source = ROOT / 'styles/industrial_acg_v1/versions/1.1.0'
    shutil.copytree(source, folder)
    profile = load_data(folder / 'profile.yaml')
    profile.update(id='user_valley', version=version, format_version='1.0', provenance='provenance.json')
    profile['components']['critic'] = 'critic/rubric.yaml'
    write_yaml(folder / 'profile.yaml', profile)
    signature = load_data(folder / 'style_signature.yaml')
    signature.update(id=profile['id'], version=version,
                     reviewed_by='artist@example' if reviewed else 'unreviewed',
                     review_status='design_reviewed' if reviewed else 'unreviewed',
                     evidence_scope={'user_reference': 'Unverified screenshot; observation only.'})
    signature['dimensions']['palette']['painted_metal'] = [.31, .43, .27]
    write_yaml(folder / 'style_signature.yaml', signature)
    rubric = load_data(folder / 'critic/rubric.yaml')
    rubric['profile_version'] = version
    rubric['categories']['style_compatibility'] = 'Check the user valley palette and supplied reference scope.'
    write_yaml(folder / 'critic/rubric.yaml', rubric)
    (folder / 'provenance.json').write_text(json.dumps({
        'style_id': profile['id'], 'version': version,
        'evidence_limits': ['No permission or artistic approval inferred.'],
    }), encoding='utf-8')
    for relative in profile['resources'].values():
        path = folder / relative
        if resources:
            path.write_bytes(b'BLENDER explicit file-validation double')
        else:
            path.unlink(missing_ok=True)
    return folder


def tree_bytes(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def import_package(root, source, expected=None):
    manager = ManifestManager(root)
    return manager.import_style(source, expected_version=manager.read()['version'] if expected is None else expected)


def test_draft_inspection_and_preparation_preserve_input(tmp_path):
    source = package(tmp_path, reviewed=False, resources=False)
    before = tree_bytes(source)
    result = cli('style-inspect', source)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['status'] == 'pending'
    assert set(report['pending']) == {'design_review', 'library', 'calibration'}
    assert report['artistic_approval'] is False
    output = tmp_path / 'calibration-candidate'
    result = cli('style-prepare', source, '--output', output)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    assert prepared['status'] == 'prepared' and 'execute_code' in prepared
    packet = load_data(prepared['packet'])
    assert packet['style']['id'] == 'user_valley'
    assert packet['style']['materials']['materials']['painted_metal']['base_color'] == [.31, .43, .27]
    assert Path(packet['style']['library']).is_relative_to(output)
    assert not Path(packet['style']['library']).exists()
    assert load_data(output / 'style_signature.yaml')['review_status'] == 'unreviewed'
    assert tree_bytes(source) == before
    again = cli('style-prepare', source, '--output', output)
    assert again.returncode == 2 and 'exists' in json.loads(again.stderr)['error']


def test_arbitrary_release_version_and_reviewer_are_data(tmp_path):
    source = package(tmp_path)
    style = StyleRegistry().load_package(source)
    assert style['version'] == '2.3.4' and style['format_version'] == '1.0'
    assert len(style['materials']['materials']) == 7
    assert style['signature']['reviewed_by'] == 'artist@example'
    # A profile identifier describes this supplied lighting, not a built-in whitelist.
    lighting = load_data(source / 'lighting/overcast.yaml')
    lighting['profile'] = 'valley_daylight'
    write_yaml(source / 'lighting/overcast.yaml', lighting)
    assert StyleRegistry().load_package(source)['lighting']['profile'] == 'valley_daylight'


def test_project_import_is_immutable_and_portable(tmp_path):
    source = package(tmp_path)
    before = tree_bytes(source)
    root, docs = proposal(tmp_path)
    result = cli('style-import', root, source, '--expected-version', 0)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state['version'] == 1 and state['state'] == 'initialized' and state['approvals'] == []
    installed = root / 'styles/user_valley/versions/2.3.4'
    assert (installed / 'package-lock.json').is_file()
    assert tree_bytes(source) == before
    source.rename(tmp_path / 'source-no-longer-available')
    docs['style_assignment'].update(style_profile='user_valley', profile_version='2.3.4')
    manager = ManifestManager(root)
    manager.submit_visual_plan(docs, expected_version=1)
    assert manager.read()['state'] == 'visual_review_required' and manager.read()['approvals'] == []
    result = cli('style-resolve', '--project', root, '--profile', 'user_valley', '--version', '2.3.4',
                 '--material', 'painted_metal', '--condition', 'clean')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['parameters']['base_color'] == [.31, .43, .27]
    moved = tmp_path / 'moved-project'
    shutil.copytree(root, moved)
    style = StyleRegistry().load('user_valley', version='2.3.4', project_root=moved)
    assert Path(style['root']).is_relative_to(moved)
    original = (installed / 'materials/definitions.yaml').read_bytes()
    (installed / 'materials/definitions.yaml').write_bytes(original + b'\n# tampered\n')
    with pytest.raises(WorkflowError, match='changed|hash'):
        StyleRegistry().load('user_valley', version='2.3.4', project_root=root)


@pytest.mark.parametrize('problem', ['review', 'resources', 'format', 'path', 'version', 'nan', 'critic', 'provenance', 'duplicate', 'shape', 'nested_materials', 'nested_conditions', 'profile_type', 'huge_signature', 'huge_material'])
def test_invalid_packages_reject_without_project_mutation(tmp_path, problem):
    source = package(tmp_path, reviewed=problem != 'review', resources=problem != 'resources')
    profile = load_data(source / 'profile.yaml')
    if problem == 'format': profile['format_version'] = '99.0'
    if problem == 'path': profile['components']['materials'] = '../outside.yaml'
    if problem == 'version': profile['version'] = '../2.3.4'
    write_yaml(source / 'profile.yaml', profile)
    if problem == 'nan':
        data = load_data(source / 'style_signature.yaml')
        data['dimensions']['lighting']['key_scale'] = float('nan')
        write_yaml(source / 'style_signature.yaml', data)
    if problem == 'huge_signature':
        data = load_data(source / 'style_signature.yaml')
        data['dimensions']['lighting']['key_scale'] = 10**400
        write_yaml(source / 'style_signature.yaml', data)
    if problem == 'huge_material':
        data = load_data(source / 'materials/definitions.yaml')
        data['materials']['painted_metal']['emission_strength'] = 10**400
        write_yaml(source / 'materials/definitions.yaml', data)
    if problem == 'critic': (source / 'critic/rubric.yaml').unlink()
    if problem == 'provenance': (source / 'provenance.json').write_text('{}')
    if problem == 'duplicate':
        with (source / 'profile.yaml').open('a') as stream: stream.write('\nid: another_identity\n')
    if problem == 'shape': write_yaml(source / 'materials/definitions.yaml', [])
    if problem in ('nested_materials', 'nested_conditions'):
        data = load_data(source / 'materials/definitions.yaml')
        field = problem.removeprefix('nested_')
        data[field] = list(data[field])
        write_yaml(source / 'materials/definitions.yaml', data)
    if problem == 'profile_type':
        data = load_data(source / 'camera/environment.yaml')
        data['profile'] = 123
        write_yaml(source / 'camera/environment.yaml', data)
    root, _ = proposal(tmp_path)
    before = tree_bytes(root)
    result = cli('style-import', root, source, '--expected-version', 0)
    assert result.returncode == 2 and 'error' in json.loads(result.stderr)
    assert 'Traceback' not in result.stderr
    assert tree_bytes(root) == before


def test_import_refuses_overwrite_stale_worker_and_post_approval(tmp_path):
    source = package(tmp_path)
    root, docs = proposal(tmp_path)
    manager = ManifestManager(root)
    with pytest.raises(WorkflowError, match='Stale'):
        import_package(root, source, expected=5)
    with pytest.raises(WorkflowError, match='Workers'):
        ManifestManager(root, role='worker').import_style(source, expected_version=0)
    import_package(root, source)
    before = tree_bytes(root)
    with pytest.raises(WorkflowError, match='exists|Immutable'):
        import_package(root, source)
    assert tree_bytes(root) == before
    manager.submit_visual_plan(docs, expected_version=1)
    manager.review_visual('approved', expected_version=manager.read()['version'])
    with pytest.raises(WorkflowError, match='planning|approval'):
        import_package(root, source)


def test_failed_import_rolls_back_all_published_files(tmp_path, monkeypatch):
    source = package(tmp_path)
    root, _ = proposal(tmp_path)
    before = tree_bytes(root)
    import runtime.manifest_manager as module
    original = module.atomic_write
    def fail_manifest(path, value):
        if Path(path) == root / 'manifest.yaml': raise OSError('simulated manifest write failure')
        return original(path, value)
    monkeypatch.setattr(module, 'atomic_write', fail_manifest)
    with pytest.raises(OSError, match='simulated'):
        import_package(root, source)
    assert tree_bytes(root) == before


def test_default_remains_legacy_and_external_package_is_not_auto_selected(tmp_path):
    source = package(tmp_path)
    root, _ = proposal(tmp_path)
    import_package(root, source)
    result = cli('style-resolve', '--project', root, '--material', 'concrete', '--condition', 'clean')
    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    assert resolved['profile'] == 'industrial_acg_v1' and resolved['profile_version'] == '1.0.0'
    assert resolved['parameters']['roughness'] == .82
    with pytest.raises(WorkflowError, match='Unknown'):
        StyleRegistry().load('user_valley', version='2.3.4')


@pytest.mark.parametrize('problem', ['changed_input', 'wrong_material_names', 'execution_failure'])
def test_calibration_guards_and_scene_restore_with_bpy_double(tmp_path, monkeypatch, problem):
    """Only error-control behavior is simulated; this test does not render Blender."""
    import runpy
    import sys
    import types
    from contextlib import contextmanager
    from runtime.user_styles import prepare_style
    source = package(tmp_path, reviewed=False, resources=False)
    prepared = prepare_style(source, tmp_path / 'candidate')
    packet = load_data(prepared['packet'])
    original_scene = object()
    window = types.SimpleNamespace(scene=original_scene)
    @contextmanager
    def load_library(*args, **kwargs):
        yield types.SimpleNamespace(materials=['industrial_acg_v1.concrete']), types.SimpleNamespace()
    fake = types.ModuleType('bpy')
    fake.app = types.SimpleNamespace(version=(4, 5, 13))
    fake.context = types.SimpleNamespace(window=window)
    fake.data = types.SimpleNamespace(libraries=types.SimpleNamespace(load=load_library))
    mathutils = types.ModuleType('mathutils'); mathutils.Vector = object
    monkeypatch.setitem(sys.modules, 'bpy', fake)
    monkeypatch.setitem(sys.modules, 'mathutils', mathutils)
    worker = runpy.run_path(str(ROOT / 'runtime/blender_style_worker.py'))
    def calibration_double(style, output):
        window.scene = object()
        if problem == 'execution_failure': raise OSError('simulated export failure')
        for key in ('library', 'calibration'):
            path = Path(style[key]); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'BLENDER named-material validation double')
        return types.SimpleNamespace(name='candidate')
    worker['execute_calibration'].__globals__['calibration'] = calibration_double
    if problem == 'changed_input':
        with (tmp_path / 'candidate/profile.yaml').open('a') as stream: stream.write('\n# changed\n')
    expected = {'changed_input': 'input changed', 'wrong_material_names': 'named style materials',
                'execution_failure': 'simulated export failure'}[problem]
    with pytest.raises((RuntimeError, OSError), match=expected):
        worker['execute_calibration'](prepared['packet'], prepared['sha256'])
    assert window.scene is original_scene
    assert not Path(packet['receipt']).exists() and not Path(packet['preview']).exists()


def test_user_style_reaches_scene_review_and_delivery_with_provenance(tmp_path):
    """Complete deterministic flow; scene/render receipts here are explicit doubles."""
    from tests.test_v02_geometry import executor, request
    from tests.test_v02_delivery import complete_pass, review_for
    from runtime.scene_production import prepare_scene, verify_packet
    from runtime.visual_review import current_render_context
    from runtime.io import filesystem_path
    source = package(tmp_path)
    root, docs = proposal(tmp_path)
    import_package(root, source)
    manager = ManifestManager(root)
    docs['style_assignment'].update(style_profile='user_valley', profile_version='2.3.4')
    manager.submit_visual_plan(docs, expected_version=1)
    manager.review_visual('approved', expected_version=manager.read()['version'])
    manager.configure_visual('full_pipeline', expected_version=manager.read()['version'])
    for name in ('platform', 'wall', 'machine'): executor(manager).run(request(name, None, 'A'))
    manager.review_geometry('approved', expected_version=manager.read()['version'])
    original = load_data(ROOT / 'tests/fixtures/v02/industrial_station.json')['documents']
    plans = {k: copy.deepcopy(original[k]) for k in ('blockout_plan', 'semantic_material_map', 'lookdev_plan', 'render_plan')}
    for item in plans['blockout_plan']['objects']: item.update(geometry_source='library', asset_id=item['object_id'])
    for item in plans['semantic_material_map']['mappings']: item.update(slot='body', surface_source=None)
    plans['render_plan']['preview'] = {'width': 16, 'height': 16, 'samples': 1}
    manager.submit_scene_plans(plans, expected_version=manager.read()['version'])
    prepared = prepare_scene(manager)
    packet = verify_packet(prepared['packet'], prepared['sha256'])
    assert all(value['resource'].startswith('user_valley.') for value in packet['materials'].values())
    assert str(root / 'styles/user_valley/versions/2.3.4/provenance.json') in packet['guard']
    setup = Path(packet['outputs']['setup'])
    setup.parent.mkdir(parents=True, exist_ok=True)
    setup.write_bytes(b'BLENDER setup validation double')
    Path(packet['outputs']['receipt']).write_text(json.dumps({
        'status': 'setup_complete', 'build_id': packet['build_id'], 'inputs_digest': packet['inputs_digest'],
        'geometry_before': '1'*64, 'geometry_after': '1'*64, 'blend_sha256': sha256(setup),
    }))
    manager.complete_scene_setup(prepared['packet'], prepared['sha256'], expected_version=manager.read()['version'])
    job, metadata = complete_pass(manager)
    context = current_render_context(manager)
    assert context['rubric']['profile_version'] == '2.3.4'
    assert 'user valley' in context['rubric']['categories']['style_compatibility']
    manager.submit_render_review(review_for(manager, metadata, 'final_review_required'), expected_version=manager.read()['version'])
    manager.final_review_v02('approved', expected_version=manager.read()['version'])
    result = manager.deliver_v02(expected_version=manager.read()['version'])
    delivered = root / result['package'] / 'project/styles/user_valley/versions/2.3.4'
    for name in ('profile.yaml', 'provenance.json', 'package-lock.json', 'critic/rubric.yaml'):
        assert filesystem_path(delivered / name).read_bytes() == (root / 'styles/user_valley/versions/2.3.4' / name).read_bytes()
