"""Production boundary tests; review/render fixtures are explicit test doubles."""
import copy
import json
import math
from pathlib import Path

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data
from runtime.style_registry import StyleRegistry
from runtime.validators import validate_contract
from tests.test_v02_production import scene_ready


def direction(project='station', subject='machine'):
    return {'schema_version': '1.0', 'project_id': project, 'scene_version': 1,
            'direction_id': 'rd_test', 'revision': 0, 'scene_type': 'industrial_environment',
            'intent': {'primary_goal': ['material_readability']},
            'camera': {'subject_ref': subject, 'framing': {'type': 'three_quarter'},
                       'azimuth_deg': 35, 'elevation_deg': 25, 'focal_length_mm': 40,
                       'subject_coverage': {'target': .55},
                       'target': {'mode': 'subject_center', 'offset_normalized': [0,0,0]}},
            'composition': {'hierarchy': 'strong_single_anchor', 'foreground': {'role': 'support', 'required': False},
                            'midground': {'required': True}, 'background': {'required': True},
                            'negative_space': {'amount': 'moderate'}},
            'lighting': {'key': {'reference_frame': 'camera_subject', 'azimuth_deg': 135,
                                'elevation_deg': 40, 'softness': 'large'},
                         'fill': {'ratio_to_key': .25}, 'silhouette_separation': 'strong'},
            'atmosphere': {'amount': 'subtle', 'depth_priority': 'moderate'},
            'exposure': {'intent': 'preserve_highlights'},
            'material_readability': {'priority': ['roughness_contrast'], 'strategy': 'Lateral light'},
            'avoid': [], 'preserve': ['approved_geometry'], 'changed_fields': []}


def inputs(tmp_path):
    from runtime.render_context_builder import build_scene_context, project_context
    manager, plans = scene_ready(tmp_path)
    from runtime.visual_planning import current_documents
    docs = current_documents(manager, manager.read())
    bounds = {o['object_id']: {'center': [0,0,2], 'size': o['size_m']}
              for o in docs['scene_spec']['objects']}
    scene = build_scene_context(manager.read(), docs['scene_spec'], bounds, blockout_plan=plans['blockout_plan'], ground_z=0,
                                environment_summary='Test measured bounds')
    context = project_context(manager, scene)
    d = direction(manager.read()['project_id'])
    return manager, plans, scene, context, d


def test_context_intent_and_no_manifest_mutation(tmp_path):
    manager, plans, scene, context, d = inputs(tmp_path)
    before = manager.path.read_bytes()
    assert context['scene']['scene_type'] == 'industrial_environment'
    assert scene['scene']['primary_subject']['bounds']['size'] == [1,1,2]
    assert context['style']['id'] == 'industrial_acg_v1'
    assert context['style']['version'] == '1.0.0'
    assert 'approved_geometry' in context['intent']['preserve']
    assert context['previous'] == {'direction': None, 'render': None, 'review': None}
    validate_contract('render_context', context)
    assert manager.path.read_bytes() == before


@pytest.mark.parametrize('size', [[2,2,2], [20,30,12], [3,3,60], [8,10,3]])
def test_camera_projection_and_lighting(tmp_path, size):
    from runtime.render_direction_adapter import compile_render_direction
    from runtime.blender_operations import resolved_lighting
    manager, plans, scene, context, d = inputs(tmp_path)
    scene['scene']['primary_subject']['bounds'] = {'center': [4,-6,40], 'size': size}
    style = StyleRegistry().load('industrial_acg_v1')
    scene['production'] = {'project_id': d['project_id'], 'scene_version': 1,
                           'style_assignment_id': 'style_assignment_01', 'material_map_id': 'map_01'}
    look, render = compile_render_direction(d, scene, style)
    assert (look, render) == compile_render_direction(d, scene, style)
    validate_contract('lookdev_plan', look); validate_contract('render_plan', render)
    assert look['render_direction'] == render['render_direction'] == {'direction_id':'rd_test','revision':0}
    camera = render['camera']; target = camera['target']; eye = camera['location']
    distance = math.dist(eye,target)
    assert distance > max(size)/2 and eye[2] > 0
    assert camera['clip_end'] > distance + max(size)
    # Project all eight AABB corners; coverage is bounded in both image axes.
    az, el = math.radians(35), math.radians(25)
    forward = [-math.cos(el)*math.cos(az),-math.cos(el)*math.sin(az),-math.sin(el)]
    right = [-math.sin(az),math.cos(az),0]
    up = [-math.sin(el)*math.cos(az),-math.sin(el)*math.sin(az),math.cos(el)]
    import itertools
    sensor_x = camera['sensor_width_mm']; sensor_y = sensor_x*render['preview']['height']/render['preview']['width']
    for signs in itertools.product((-1,1), repeat=3):
        v = [target[i]+signs[i]*size[i]/2-eye[i] for i in range(3)]
        z = sum(a*b for a,b in zip(v,forward))
        for axis, sensor in ((right,sensor_x),(up,sensor_y)):
            assert abs(sum(a*b for a,b in zip(v,axis)))*40/z/(sensor/2) <= .550001
    lights = resolved_lighting(style['lighting'],look['lighting'])
    assert lights['fill_energy']/lights['key_energy'] == pytest.approx(.25)
    assert lights['key_target'] == target


def test_atomic_provenance_and_unapproved_rejection(tmp_path):
    manager, plans, scene, context, d = inputs(tmp_path)
    before = manager.read()
    manager.submit_scene_plans(plans, render_direction=d, scene_context=scene,
                               expected_version=before['version'])
    m = manager.read(); ref = m['render_direction']
    assert m['geometry_assets'] == before['geometry_assets'] and m['approvals'] == before['approvals']
    assert load_data(manager.root/ref['artifact_path']) == d
    from runtime.render_context_builder import project_context
    assert project_context(manager,scene)['previous']['direction'] == d
    from runtime.scene_production import prepare_scene
    packet = load_data(prepare_scene(manager)['packet'])
    assert packet['plans']['render_plan']['render_direction']['direction_id'] == d['direction_id']
    original = manager.path.read_bytes()
    d['revision'] = 9
    with pytest.raises(WorkflowError):
        manager.submit_scene_plans(plans, render_direction=d, scene_context=scene,
                                   expected_version=m['version'])
    assert manager.path.read_bytes() == original


@pytest.mark.parametrize('problem', ['coverage','nan','identity','world_coordinates','review_as_direction','missing_bounds'])
def test_invalid_direction_rejected_without_writes(tmp_path, problem):
    manager, plans, scene, context, d = inputs(tmp_path)
    if problem == 'coverage': d['camera']['subject_coverage']['target'] = 0
    if problem == 'nan': d['camera']['azimuth_deg'] = float('nan')
    if problem == 'identity': d['project_id'] = 'different'
    if problem == 'world_coordinates': d['camera']['location'] = [0,0,0]
    if problem == 'review_as_direction': d = {'recommended_changes': {'camera': {}}}
    if problem == 'missing_bounds': del scene['scene']['primary_subject']['bounds']
    before = manager.path.read_bytes()
    with pytest.raises(WorkflowError):
        manager.submit_scene_plans(plans, render_direction=d, scene_context=scene,
                                   expected_version=manager.read()['version'])
    assert manager.path.read_bytes() == before and not (manager.root/'.render_direction').exists()


def test_default_plans_remain_supported(tmp_path):
    manager, plans = scene_ready(tmp_path)
    m = manager.submit_scene_plans(plans, expected_version=manager.read()['version'])
    assert 'render_direction' not in m


def test_measurements_cannot_be_reused_for_changed_blockout(tmp_path):
    manager,plans,scene,context,d=inputs(tmp_path)
    plans['blockout_plan']['objects'][0]['transform']['location'][0]+=100
    before=manager.path.read_bytes()
    with pytest.raises(WorkflowError,match='blockout'):
        manager.submit_scene_plans(plans,render_direction=d,scene_context=scene,expected_version=manager.read()['version'])
    assert manager.path.read_bytes()==before
