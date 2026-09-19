"""Production-owned persistence and safety boundary for the external director."""
import copy
import re

from runtime.io import inside, load_data
from runtime.validators import validate_contract
from runtime.visual_contracts import document_hash, require
from runtime.visual_planning import current_documents
from runtime.style_registry import StyleRegistry
from runtime.render_context_builder import project_context, read_direction_state
from runtime.render_direction_adapter import compile_render_direction


def compile_for_project(manager, manifest, direction, scene_context, plans):
    scene_context = copy.deepcopy(scene_context)
    context = project_context(manager,scene_context,manifest)
    require(scene_context['production'].get('blockout_hash') == document_hash(plans['blockout_plan']),
            'Measured blockout changed; measure the current placement before compiling direction')
    validate_contract('render_direction',direction)
    require(set(context['intent']['preserve']).issubset(direction['preserve']), 'Direction dropped user preserve constraints')
    docs = current_documents(manager,manifest)
    style = StyleRegistry().load(docs['style_assignment']['style_profile'],
                                version=docs['style_assignment']['profile_version'],project_root=manager.root)
    prod = scene_context['production']
    prod.update(style_assignment_id=docs['style_assignment']['document_id'],
                material_map_id=plans['semantic_material_map']['document_id'],
                look_revision=plans['lookdev_plan']['revision'],render_revision=plans['render_plan']['revision'])
    look,render = compile_render_direction(direction,scene_context,style)
    for kind,compiled in [('lookdev_plan',look),('render_plan',render)]:
        compiled['document_id'] = plans[kind]['document_id']
    render['output'] = copy.deepcopy(plans['render_plan']['output'])
    return {**copy.deepcopy(plans),'lookdev_plan':look,'render_plan':render},context,scene_context


def stage_direction(manifest, direction, context, scene_context):
    """Return immutable artifacts; only ManifestManager commits them."""
    require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',direction['direction_id']) is not None,
            'Direction ID must be a portable artifact identifier')
    prefix = f".render_direction/history/{direction['direction_id']}_r{direction['revision']}"
    old = manifest.get('render_direction',{})
    history = copy.deepcopy(old.get('history',[]))
    if old:
        history.append({k:v for k,v in old.items() if k not in ('history','reviews')})
    manifest['render_direction'] = {'current_id':direction['direction_id'],'revision':direction['revision'],
        'artifact_path':prefix+'.json','hash':document_hash(direction),
        'context_path':prefix+'_context.json','context_hash':document_hash(context),
        'scene_context_path':prefix+'_scene.json','scene_context_hash':document_hash(scene_context),
        'reviews':copy.deepcopy(old.get('reviews',[])), 'history':history}
    return [(prefix+'.json',direction),(prefix+'_context.json',context),(prefix+'_scene.json',scene_context)]


def initial_direction(manager, manifest, direction, scene_context, plans):
    validate_contract('render_direction',direction)
    require(not manifest.get('render_direction'), 'Existing direction must use reviewed refinement')
    require(direction['revision'] == 0 and not direction['changed_fields'], 'Initial direction must start at revision zero')
    require(manifest['mode'] in ('full_pipeline','stage2_only','repair') and manifest['state'] == 'geometry_approved',
            'Initial direction requires approved geometry and authorized execution')
    compiled,context,scene = compile_for_project(manager,manifest,direction,scene_context,plans)
    # A request to preserve an existing camera cannot be satisfied by inventing one.
    require(not (set(direction['preserve'])-{'approved_geometry','geometry','materials','style'}),
            'Initial preserved visual fields need an existing direction; retain the existing plans or establish a baseline')
    return compiled,stage_direction(manifest,direction,context,scene)


def validate_plan_reference(manifest, plans):
    expected = manifest.get('render_direction')
    sources = [plans[k].get('render_direction') for k in ('lookdev_plan','render_plan')]
    if expected:
        ref = {'direction_id':expected['current_id'],'revision':expected['revision']}
        require(all(source == ref for source in sources), 'Plan RenderDirection reference mismatch')
    else:
        require(not any(sources), 'Plan references an unregistered RenderDirection')
    require(('world_setup' in plans['lookdev_plan']['lighting']) == bool(expected),
            'Compiled lighting requires registered direction provenance')


def verify_compiled_plans(manager, manifest, plans):
    """Recompilation detects edits that would silently break direction provenance."""
    if not manifest.get('render_direction'):
        return
    state = read_direction_state(manager,manifest)
    compiled,_,_ = compile_for_project(manager,manifest,state['direction'],state['scene_context'],plans)
    for kind in ('lookdev_plan','render_plan'):
        require(compiled[kind] == plans[kind], 'Executable plan differs from registered RenderDirection')


def stage_review(manager, manifest, review, visual_review):
    validate_contract('render_review',review)
    state = read_direction_state(manager,manifest)
    require(bool(state), 'RenderReview requires an active RenderDirection')
    from runtime.visual_review import current_render_context
    rendered = current_render_context(manager,manifest)
    metadata = rendered['documents']['render_metadata']; d = state['direction']
    require((review['project_id'],review['scene_version'],review['direction_id'],review['direction_revision']) ==
            (manifest['project_id'],manifest['scene_version'],d['direction_id'],d['revision']), 'Stale RenderReview direction')
    require(review['render_id'] == metadata['document_id'] and review['render_sha256'] == metadata['image']['sha256'],
            'RenderReview requires the exact actual PNG')
    require(set(d['preserve']).issubset(review['preserve']), 'Review dropped preserve fields')
    require(bool(review['recommended_changes']) == (visual_review['decision'] == 'revision_required'),
            'External review and production diagnosis disagree about revision')
    path = f".render_direction/reviews/{review['render_id']}_{visual_review['document_id']}.json"
    require(all(r['path'] != path for r in manifest['render_direction']['reviews']), 'RenderReview already recorded')
    manifest['render_direction']['reviews'].append({'path':path,'hash':document_hash(review)})
    return [(path,review)]


# Public review deltas supported by this production adapter. These are numerical
# execution limits, not photographic knowledge or automatic visual judgements.
DELTAS = {
    'camera.azimuth_delta_deg': ('camera.azimuth_deg','camera_framing',10),
    'camera.elevation_delta_deg': ('camera.elevation_deg','camera_framing',10),
    'camera.focal_length_delta_mm': ('camera.focal_length_mm','camera_framing',10),
    'camera.coverage_delta': ('camera.subject_coverage.target','camera_framing',.1),
    'lighting.key_azimuth_delta_deg': ('lighting.key.azimuth_deg','lighting_direction',10),
    'lighting.key_elevation_delta_deg': ('lighting.key.elevation_deg','lighting_direction',10),
    'lighting.fill_ratio_delta': ('lighting.fill.ratio_to_key','lighting_intensity',.2),
}


def get_path(value,path):
    for key in path.split('.'):
        if not isinstance(value,dict) or key not in value:
            return None
        value = value[key]
    return value


def changed_paths(old,new,prefix=''):
    if isinstance(old,dict) and isinstance(new,dict):
        result = set()
        for key in old.keys() | new.keys():
            result |= changed_paths(old.get(key),new.get(key),prefix+'.'+key if prefix else key)
        return result
    return {prefix} if old != new else set()


def refined_direction(manager, manifest, new, revision, plans):
    validate_contract('render_direction',new)
    state = read_direction_state(manager,manifest); old = state['direction']; review = state['review']
    require(review is not None, 'Refinement requires a recorded external review')
    from runtime.visual_review import current_render_context
    metadata = current_render_context(manager,manifest)['documents']['render_metadata']
    require((review['direction_id'],review['direction_revision'],review['render_id'],review['render_sha256']) ==
            (old['direction_id'],old['revision'],metadata['document_id'],metadata['image']['sha256']),
            'Refinement requires the current reviewed PNG and direction')
    require(new['direction_id'] == old['direction_id'] and new['revision'] == old['revision']+1, 'Direction revision must advance exactly once')
    preserve = set(old['preserve']) | set(review['preserve']) | set(state['context']['intent']['preserve'])
    require(preserve.issubset(new['preserve']), 'Refinement dropped preserve fields')
    aliases = {'focal_length':'camera.focal_length_mm','composition':'composition',
               'geometry':None,'approved_geometry':None,'materials':None,'style':None}
    for field in preserve:
        path = aliases.get(field,field)
        if path is not None:
            require(get_path(old,path) is not None and get_path(old,path) == get_path(new,path),
                    'Refinement changed or cannot resolve preserved field: '+field)
    changed = changed_paths(old,new)-{'revision','changed_fields','preserve'}
    require(changed == set(new['changed_fields']) and bool(changed), 'changed_fields must describe exactly the changed visual fields')
    actions = {a['action']:a for a in revision['actions']}
    allowed = set()
    for recommendation,(path,action,bound) in DELTAS.items():
        delta = get_path(review['recommended_changes'],recommendation)
        if delta is None or path not in changed:
            continue
        require(action in actions, 'Direction change is absent from the production revision gate')
        amount = actions[action]['amount']; limit = bound*(.5 if amount == 'small' else 1)
        before,after = get_path(old,path),get_path(new,path)
        before = 0 if path == 'exposure.adjustment_ev' and before is None else before
        require(isinstance(before,(int,float)) and isinstance(after,(int,float)), 'Invalid numeric direction delta')
        actual = after-before
        require(0 < abs(actual) <= min(abs(delta),limit)+1e-9 and actual*delta > 0,
                'Direction delta exceeds reviewed bounded change')
        allowed.add(path)
    if 'atmosphere.amount' in changed:
        requested = get_path(review['recommended_changes'],'atmosphere.amount')
        require('fog_amount' in actions and requested == new['atmosphere']['amount'], 'Unreviewed atmosphere change')
        options = ['none','subtle','moderate','heavy']
        require(abs(options.index(old['atmosphere']['amount'])-options.index(requested)) <=
                (1 if actions['fog_amount']['amount'] == 'small' else 2), 'Atmosphere change exceeds bounded revision')
        allowed.add('atmosphere.amount')
    require(changed == allowed, 'Unreviewed fields or geometry changes are outside bounded direction revision')
    require(set(actions).issubset({'camera_framing','lighting_direction','lighting_intensity','fog_amount','exposure'}),
            'Director refinement cannot change material maps or geometry')
    compiled,context,scene = compile_for_project(manager,manifest,new,state['scene_context'],plans)
    return compiled,stage_direction(manifest,new,context,scene)
