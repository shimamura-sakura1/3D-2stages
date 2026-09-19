"""Aggregate production facts for an external visual director; never infer a shot."""
import copy
import json

from runtime.io import inside, load_data, sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import document_hash, require
from runtime.visual_planning import current_documents
from runtime.style_registry import StyleRegistry


SCENE_TYPES = {'hero_prop','industrial_environment','industrial_megastructure','interior'}
SCENE_ALIASES = {'industrial_station':'industrial_environment'}


def build_scene_context(manifest, scene_spec, bounds_by_object, *, blockout_plan, ground_z, environment_summary, scene_type=None):
    """Consume measured world-space AABBs after geometry/placement, not guessed sizes.

    The caller obtains these from Blender (including parent transforms, rotation,
    scale and repeated instances). A spec's target size is not measured geometry.
    """
    objects = {o['object_id'] for o in scene_spec['objects']}
    assets = manifest.get('geometry_assets', {})
    validate_contract('blockout_plan',blockout_plan)
    require((blockout_plan['project_id'],blockout_plan['scene_version']) ==
            (manifest['project_id'],manifest['scene_version']), 'Measured blockout identity mismatch')
    require(objects == set(assets) and all(a['status'] == 'approved' for a in assets.values()),
            'Scene context requires the complete approved geometry set')
    require(set(bounds_by_object) == objects, 'Measured world bounds must cover every object')
    primary = scene_spec['composition']['focal_subject']
    scene_type = scene_type or SCENE_ALIASES.get(scene_spec['scene_type'],scene_spec['scene_type'])
    require(scene_type in SCENE_TYPES, 'Supply an explicit supported Render Director scene_type')
    subjects = [{'object_id': key, 'bounds': copy.deepcopy(bounds_by_object[key])} for key in sorted(objects)]
    # Validate each measurement before indexing it or performing arithmetic.
    for item in subjects:
        probe = {'scene': {'scene_type': scene_type, 'primary_subject': item,
                          'secondary_subjects': [], 'bounds': item['bounds'], 'ground_z': ground_z,
                          'environment_summary': environment_summary},
                 'production': {'project_id': manifest['project_id'], 'scene_version': manifest['scene_version']}}
        validate_contract('scene_context', probe)
    low = [min(s['bounds']['center'][i]-s['bounds']['size'][i]/2 for s in subjects) for i in range(3)]
    high = [max(s['bounds']['center'][i]+s['bounds']['size'][i]/2 for s in subjects) for i in range(3)]
    result = {'scene': {'scene_type': scene_type,
                        'primary_subject': next(s for s in subjects if s['object_id'] == primary),
                        'secondary_subjects': [s for s in subjects if s['object_id'] != primary],
                        'bounds': {'center': [(a+b)/2 for a,b in zip(low,high)], 'size': [b-a for a,b in zip(low,high)]},
                        'ground_z': ground_z, 'environment_summary': environment_summary},
              'production': {'project_id': manifest['project_id'], 'scene_version': manifest['scene_version'],
                             'geometry_hash': document_hash(assets), 'scene_spec_hash': document_hash(scene_spec),
                             'blockout_hash':document_hash(blockout_plan)}}
    return validate_contract('scene_context', result)


def build_render_context(manifest, visual_brief, scene_context, resolved_style, references,
                         current_scene_observations):
    validate_contract('scene_context', scene_context)
    production = scene_context['production']
    require((production['project_id'], production['scene_version']) ==
            (manifest['project_id'], manifest['scene_version']), 'Scene context project/scene mismatch')
    constraints = visual_brief['constraints']
    observations = current_scene_observations or {}
    scene = scene_context['scene']
    # The external 1.0 protocol has no extension fields. Preserve production intent
    # as labelled text within its supported fields instead of inventing wire keys.
    intent_details = {'visual_goal':visual_brief['priorities'], 'required_elements':constraints['required'],
                      'avoid':constraints['avoid']}
    summary = {'primary_subject_bounds':scene['primary_subject']['bounds'],
               'secondary_subject_bounds':scene['secondary_subjects'],'ground_z':scene['ground_z'],
               'scene_observations':observations.get('observations',[]),
               'style_direction_prior':resolved_style.get('direction_prior',{})}
    result = {'schema_version': '1.0',
              'project': {'project_id': manifest['project_id'], 'scene_version': manifest['scene_version']},
              'intent': {'visual_brief_id': visual_brief['document_id'], 'user_prompt': manifest['user_brief']['raw'],
                         'user_constraints': list(dict.fromkeys([*constraints.get('user_constraints', []),
                             'Stage 0 intent: '+json.dumps(intent_details,ensure_ascii=False)])),
                         'preserve': sorted(set(['approved_geometry', *constraints.get('preserve', [])]))},
              'scene': {'scene_type':scene['scene_type'],'primary_subject':{'object_id':scene['primary_subject']['object_id']},
                        'secondary_subjects':[{'object_id':s['object_id']} for s in scene['secondary_subjects']],
                        'bounds':copy.deepcopy(scene['bounds']),
                        'environment_summary':scene['environment_summary']+'\nProduction facts: '+json.dumps(summary,ensure_ascii=False)},
              'style': {'id': resolved_style['id'], 'version': resolved_style['version']},
              'references': [{'id': r['reference_id'], 'role': {'material_language':'material_readability','surface_condition':'material_readability','geometry':'style','architecture':'style','palette':'style','vegetation':'style','prop_language':'style'}.get(role,role),
                              'path': r['path'], 'description':json.dumps({'source_role':role,'source':r['source']},ensure_ascii=False)}
                             for r in references for role in r['roles']],
              'previous': {key: copy.deepcopy(observations.get(key)) for key in ('direction','render','review')}}
    return validate_contract('render_context', result)


def read_direction_state(manager, manifest):
    ref = manifest.get('render_direction')
    if not ref:
        return {}
    values = {}
    for name, path_key, hash_key in [('direction','artifact_path','hash'),
                                     ('context','context_path','context_hash'),
                                     ('scene_context','scene_context_path','scene_context_hash')]:
        value = load_data(inside(manager.root, ref[path_key]))
        require(document_hash(value) == ref[hash_key], 'Changed Render Director artifact: '+name)
        validate_contract('render_'+name if name in ('direction','context') else name, value)
        values[name] = value
    d = values['direction']
    require((d['direction_id'],d['revision'],d['project_id'],d['scene_version']) ==
            (ref['current_id'],ref['revision'],manifest['project_id'],manifest['scene_version']),
            'Stale RenderDirection identity')
    reviews = []
    for record in ref['reviews']:
        review = load_data(inside(manager.root,record['path']))
        validate_contract('render_review',review)
        require(document_hash(review) == record['hash'], 'Changed RenderReview artifact')
        require((review['project_id'],review['scene_version']) == (manifest['project_id'],manifest['scene_version']),
                'RenderReview scene mismatch')
        reviews.append(review)
    values['review'] = reviews[-1] if reviews else None
    values['observations'] = [{'render_id': r['render_id'], 'scene_version': r['scene_version'],
                               'findings': r['findings']} for r in reviews]
    return values


def project_context(manager, scene_context, manifest=None, *, review=False):
    m = manager.read() if manifest is None else manifest
    docs = current_documents(manager,m)
    validate_contract('scene_context',scene_context)
    production = scene_context['production']
    require(production.get('geometry_hash') == document_hash(m.get('geometry_assets',{})), 'Stale measured geometry context')
    require(production.get('scene_spec_hash') == document_hash(docs['scene_spec']), 'Stale scene specification context')
    require(scene_context['scene']['scene_type'] in SCENE_TYPES and
            scene_context['scene']['primary_subject']['object_id'] == docs['scene_spec']['composition']['focal_subject'],
            'Scene context subject/type mismatch')
    style = StyleRegistry().load(docs['style_assignment']['style_profile'],
                                version=docs['style_assignment']['profile_version'],project_root=manager.root)
    previous = read_direction_state(manager,m)
    if previous.get('review') and previous['review']['direction_revision'] != previous['direction']['revision']:
        previous['review'] = None
    if review:
        from runtime.visual_review import current_render_context
        rendered = current_render_context(manager,m)
        metadata = rendered['documents']['render_metadata']
        previous['render'] = {'render_id':metadata['document_id'], 'png_path':metadata['image']['path']}
    return build_render_context(m,docs['visual_brief'],scene_context,style,
                                docs['reference_board']['references'],previous)
