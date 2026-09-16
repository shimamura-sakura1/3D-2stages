"""Deterministic, bounded visual corrections; geometry and approvals are immutable."""
import copy
import math
import re

from runtime.io import inside, load_data
from runtime.validators import validate_contract
from runtime.visual_contracts import document_hash, require
from runtime.visual_planning import current_documents
from runtime.visual_review import ACTION_SCOPES, current_render_context
from runtime.scene_production import PLAN_KINDS, validate_scene_plans
from runtime.state_machine import check_scene_transition

VISUAL_KINDS = PLAN_KINDS[1:]


def next_preview_index(manager):
    """Use the same occupied-slot rule when validating and reserving a pass."""
    folder = inside(manager.root, 'stage2/previews')
    slots = [int(p.name[5:]) for p in folder.iterdir()
             if re.fullmatch(r'pass_[0-9]{2,}', p.name)] if folder.exists() else []
    return max(slots, default=-1) + 1


def preview_attempt_count(manager, manifest):
    """Count reservations, including failed/uncompleted passes and occupied slots."""
    count = sum(h['action'] == 'preview_reserved' for h in manifest['history'])
    return max(count, next_preview_index(manager))


def prior_revisions(manager, manifest):
    documents = []
    for record in manifest['artifacts'].get('revision_plan', []):
        doc = load_data(inside(manager.root, record['path']))
        validate_contract('revision_plan', doc)
        require(document_hash(doc) == record['sha256'] and doc['document_id'] == record['document_id']
                and doc['revision'] == record['revision'] and doc['scene_version'] == record['scene_version'],
                'Revision history identity/hash mismatch')
        documents.append(doc)
    return documents


def enforce_preview_budget(manager, manifest):
    previous = prior_revisions(manager, manifest)
    if previous:
        require(preview_attempt_count(manager, manifest) < min(p['max_preview_passes'] for p in previous),
                'Total preview attempt budget exhausted (failed and reserved attempts count)')


def bounded(value, minimum, maximum, label):
    require(math.isfinite(value) and minimum <= value <= maximum, label + ' exceeds bounded range')
    return value


def revise_plans(plans, actions):
    """Apply explicit deltas; reject overflow rather than silently clamp.

    Increase camera framing means a wider view (distance +5/10%). Decrease moves
    inward by 5/10% of current distance. Enum steps are 1/2; angular steps 5/10
    degrees, roughness scale .1/.2, exposure .25/.5 EV. Opposite additive actions
    reverse exactly; camera moves are relative to each current camera distance.
    """
    revised = copy.deepcopy(plans)
    for item in actions:
        action, scope = item['action'], item['scope']
        sign = 1 if item['direction'] == 'increase' else -1
        step = 1 if item['amount'] == 'small' else 2
        look = revised['lookdev_plan']; render = revised['render_plan']
        if action == 'roughness_variation':
            mapping = next(x for x in revised['semantic_material_map']['mappings'] if x['object_id'] == scope)
            mapping['roughness_variation_scale'] = bounded(round(mapping.get('roughness_variation_scale', 1) + sign*step*.1, 10), .5, 2, action)
        elif action == 'lighting_direction':
            lighting = look['lighting']
            lighting['azimuth_offset_degrees'] = bounded(lighting.get('azimuth_offset_degrees', 0) + sign*step*5, -45, 45, action)
        elif action in ('lighting_intensity', 'fog_amount'):
            section, field, options = (look['lighting'], 'intensity', ['low', 'medium', 'high']) if action == 'lighting_intensity' else (look['atmosphere'], 'amount', ['none', 'subtle', 'medium', 'dense'])
            index = options.index(section[field]) + sign*step
            bounded(index, 0, len(options)-1, action)
            section[field] = options[index]
        elif action == 'camera_framing':
            camera = render['camera']; factor = 1 + sign*step*.05
            camera['location'] = [bounded(t + (p-t)*factor, -1e6, 1e6, action)
                                  for p,t in zip(camera['location'], camera['target'])]
        elif action == 'exposure':
            render['color']['exposure'] = bounded(render['color']['exposure'] + sign*step*.25, -20, 20, action)
    for kind in VISUAL_KINDS: revised[kind]['revision'] += 1
    return revised


def stage_revision(manager, manifest, revision):
    revision = copy.deepcopy(revision)
    if isinstance(revision, dict): revision.setdefault('max_preview_passes', 3)
    validate_contract('revision_plan', revision)
    require(manifest['state'] == 'visual_revision', 'No diagnosed visual revision is pending')
    context = current_render_context(manager, manifest)
    review = current_documents(manager, manifest, ('visual_review',))['visual_review']
    validate_contract('visual_review', review)
    identity = (manifest['project_id'], manifest['scene_version'])
    require((review['project_id'], review['scene_version']) == identity ==
            (revision['project_id'], revision['scene_version']), 'Revision/review project or scene mismatch')
    metadata = context['documents']['render_metadata']
    require(review['decision'] == 'revision_required', 'Review does not authorize bounded revision')
    require(review['render_metadata_id'] == revision['render_metadata_id'] == metadata['document_id']
            and review['image_sha256'] == metadata['image']['sha256'], 'Revision requires the exact current reviewed render')
    require(revision['based_on_review_id'] == review['document_id'], 'Revision requires the current immutable review')
    previous = prior_revisions(manager, manifest)
    require(all(p['based_on_review_id'] != review['document_id'] for p in previous), 'Review already used for a revision')
    require(revision['revision'] == len(previous) and revision['pass_index'] == int(metadata['pass_id'].split('_')[1])+1,
            'Stale revision or incorrect revision pass')
    used_ids = {r['document_id'] for records in manifest['artifacts'].values() for r in records}
    require(revision['document_id'] not in used_ids, 'Revision document identity already used')
    limit = min([revision['max_preview_passes'], *(p['max_preview_passes'] for p in previous)])
    require(revision['max_preview_passes'] == limit, 'Previously selected preview limit cannot be relaxed')
    require(preview_attempt_count(manager, manifest) < limit, 'Total preview attempt budget exhausted')
    require(next_preview_index(manager) == revision['pass_index'],
            'Next available preview slot differs from the reviewed next pass')
    objects = {o['object_id'] for o in context['documents']['scene_spec']['objects']}
    recommended = {(a['action'], a['scope']): a for a in review['recommended_actions']}
    seen = set()
    for action in revision['actions']:
        key = (action['action'], action['scope'])
        require(key not in seen, 'Duplicate revision action/scope'); seen.add(key)
        require(action['action'] in {'roughness_variation', *ACTION_SCOPES}, 'Geometry regeneration/replacement is outside bounded revision')
        require(action['scope'] in objects if action['action'] == 'roughness_variation'
                else action['scope'] == ACTION_SCOPES[action['action']], 'Invalid revision action scope')
        require(key in recommended, 'Revision action was not recommended by current review')
        magnitude = recommended[key]['magnitude']
        require(magnitude in ('small', 'medium') and
                ('small', 'medium').index(action['amount']) <= ('small', 'medium').index(magnitude),
                'Revision exceeds recommended bounded magnitude')
    plans = {k: context['documents'][k] for k in PLAN_KINDS}
    revised = revise_plans(plans, revision['actions'])
    validate_scene_plans(manager, manifest, revised)
    pending = []
    for kind, doc in [(k, revised[k]) for k in VISUAL_KINDS] + [('revision_plan', revision)]:
        path = (f"stage2/revisions/rev_{doc['revision']:04d}/revision_plan.yaml" if kind == 'revision_plan'
                else f"stage2/plans/rev_{doc['revision']:04d}/{kind}.yaml")
        manifest['artifacts'].setdefault(kind, []).append({'document_id': doc['document_id'], 'revision': doc['revision'],
                    'scene_version': manifest['scene_version'], 'path': path, 'sha256': document_hash(doc)})
        pending.append((path, doc))
    check_scene_transition(manifest['state'], 'render_pending')
    manifest['state'] = 'render_pending'
    return pending
