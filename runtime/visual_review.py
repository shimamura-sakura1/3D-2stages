"""Validate current render evidence and agent-authored diagnoses; never infer scores."""
from runtime.errors import BoundaryError
from runtime.io import inside, load_data, sha256
from runtime.preview_renderer import validate_png
from runtime.scene_production import PLAN_KINDS, validate_scene_plans
from runtime.style_registry import StyleRegistry
from runtime.validators import validate_contract
from runtime.visual_contracts import document_hash, require, unique
from runtime.visual_planning import current_documents


CATEGORIES = ('plasticity', 'material_separation', 'surface_uniformity', 'composition',
              'depth_separation', 'lighting_flatness', 'contact_shadow',
              'atmospheric_depth', 'style_compatibility')
OBJECT_ACTIONS = {'roughness_variation', 'replace_geometry', 'regenerate_geometry'}
ACTION_SCOPES = {'lighting_intensity': 'lighting', 'lighting_direction': 'lighting',
                 'fog_amount': 'atmosphere', 'camera_framing': 'camera', 'exposure': 'render'}


def current_render_context(manager, manifest=None):
    return _render_context(manager, manifest, allowed_states=(
        'render_review_required', 'visual_revision', 'final_review_required'))


def _render_context(manager, manifest=None, *, allowed_states):
    """Read current completed artifacts, independent of obsolete execution-packet guards.

    A caller holding the ManifestManager lock can supply its validated snapshot.
    Current render evidence remains inspectable after a diagnosis has been recorded.
    """
    try:
        m = manager.read() if manifest is None else manifest
        require(m['schema_version'] == '0.2', 'Render review requires schema 0.2')
        require(m['mode'] in ('full_pipeline', 'stage2_only', 'repair'),
                'Render review requires authorized scene execution')
        require(m['state'] in allowed_states,
                'No current successful preview is available for review')
        plans = current_documents(manager, m, PLAN_KINDS)
        documents = {**validate_scene_plans(manager, m, plans), **plans}
        metadata = current_documents(manager, m, ('render_metadata',))['render_metadata']
        validate_contract('render_metadata', metadata)
        require((metadata['project_id'], metadata['scene_version']) ==
                (m['project_id'], m['scene_version']), 'Render project/scene identity mismatch')
        plan = plans['render_plan']
        require(metadata['render_success'], 'Failed render cannot enter visual review')
        require(metadata['render_plan_id'] == plan['document_id'] and
                metadata['render_plan_hash'] == document_hash(plan), 'Current render plan mismatch')
        require(metadata['style_profile'] == documents['style_assignment']['style_profile'],
                'Render style mismatch')
        require(metadata['renderer'] == plan['renderer'], 'Render renderer mismatch')
        require(metadata['image']['path'] == plan['output']['image_path'] ==
                f"stage2/previews/{metadata['pass_id']}/preview.png", 'Render image/pass path mismatch')
        geometry = {key: asset['versions'][-1] for key, asset in m['geometry_assets'].items()}
        build_hash = document_hash({'geometry_fingerprint_format': 2,
                                    'blockout': plans['blockout_plan'], 'geometry': geometry})
        require(metadata['build_id'] == 'build_' + build_hash[:16], 'Render build identity mismatch')
        image_path = inside(manager.root, metadata['image']['path'])
        require(image_path.is_file() and sha256(image_path) == metadata['image']['sha256'],
                'Missing or changed render image')
        validate_png(image_path, plan['preview']['width'], plan['preview']['height'])
        documents['render_metadata'] = metadata
        unique(documents.values(), 'document_id', 'current document identity')
        style = StyleRegistry().load(metadata['style_profile'], version=documents['style_assignment']['profile_version'], project_root=manager.root)
        rubric = style['critic'] if 'critic' in style else load_data(inside(style['root'], 'critic/rubric.yaml'))
        require(isinstance(rubric, dict) and isinstance(rubric.get('categories'), dict) and
                set(rubric['categories']) == set(CATEGORIES), 'Missing or invalid nine-category critic rubric')
        require(isinstance(rubric.get('score_semantics'), str) and bool(rubric['score_semantics'].strip()),
                'Critic rubric must specify score semantics')
        return {'project_id': m['project_id'], 'scene_version': m['scene_version'],
                'manifest_version': m['version'], 'state': m['state'], 'documents': documents,
                'image': {**metadata['image'], 'absolute_path': str(image_path)}, 'rubric': rubric,
                'next_review_revision': max((r['revision'] for r in m['artifacts'].get('visual_review', [])),
                                            default=-1) + 1}
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise BoundaryError(f'Invalid current render context: {exc}') from exc


def validate_render_review(manager, manifest, review):
    """Validate a diagnosis against a current snapshot without creating any artifacts."""
    validate_contract('visual_review', review)
    context = current_render_context(manager, manifest)
    if manifest['state'] == 'visual_revision':
        from runtime.visual_delivery import indexed_document, verify_files
        finals = manifest.get('final_reviews', [])
        require(finals and finals[-1]['decision'] == 'rejected', 'No final rejection requires a new diagnosis')
        final = indexed_document(manager, finals[-1], 'final_snapshot')
        verify_files(manager, final['files'])
        prior = current_documents(manager, manifest, ('visual_review',))['visual_review']
        require(final['scene_version'] == manifest['scene_version'] and
                final['pass_id'] == context['documents']['render_metadata']['pass_id'] and
                final['documents']['visual_review'] == document_hash(prior),
                'Final rejection already received a new diagnosis or is stale')
        require(review['decision'] == 'revision_required' and review['recommended_actions'],
                'Final rejection requires a concrete revision-required diagnosis')
    else:
        require(manifest['state'] == 'render_review_required', 'No current render review is pending')
    require((review['project_id'], review['scene_version']) ==
            (manifest['project_id'], manifest['scene_version']), 'Review project/scene identity mismatch')
    metadata = context['documents']['render_metadata']
    require(review['render_metadata_id'] == metadata['document_id'], 'Review render metadata mismatch')
    require(review['image_sha256'] == metadata['image']['sha256'], 'Reviewed image hash mismatch')
    require(review['revision'] == context['next_review_revision'],
            'Review must use the next immutable revision')
    prior = manifest['artifacts'].get('visual_review', [])
    require(all(r['document_id'] != review['document_id'] for r in prior), 'Review document identity already used')
    require(review['document_id'] not in {d['document_id'] for d in context['documents'].values()},
            'Review identity conflicts with a current document')
    objects = {obj['object_id'] for obj in context['documents']['scene_spec']['objects']}
    for action in review['recommended_actions']:
        if action['action'] in OBJECT_ACTIONS:
            require(action['scope'] in objects, 'Review action requires an existing object scope')
        else:
            require(action['scope'] == ACTION_SCOPES[action['action']], 'Review action scope mismatch')
    return context
