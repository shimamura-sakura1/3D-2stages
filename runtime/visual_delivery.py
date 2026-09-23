"""Immutable completed-preview evidence, explicit final review, and local delivery.

Execution packet guards apply at completion. Later reviews check captured bytes and
current semantic inputs without pretending an old packet's manifest is current.
"""
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from runtime.errors import BoundaryError
from runtime.io import filesystem_path, inside, load_data, sha256
from runtime.validators import validate_contract, validate_manifest
from runtime.visual_contracts import document_hash, require
from runtime.visual_planning import current_documents, STAGE0_KINDS
from runtime.scene_production import PLAN_KINDS, validate_scene_plans, check_setup_receipt

REPOSITORY = Path(__file__).resolve().parents[1]
CURRENT_KINDS = (*STAGE0_KINDS, *PLAN_KINDS)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def raw_hash(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def relative(root, path):
    path = Path(path).resolve()
    require(path.is_relative_to(root), 'Completion file escapes its declared root')
    name = path.relative_to(root).as_posix()
    require(name and all(p not in ('.env', 'configs') and not p.startswith('.env.') for p in Path(name).parts),
            'Configuration and environment secrets are outside delivery')
    return name


def anchor(root, path, namespace='project'):
    name = relative(root, path)
    path = inside(root, name)
    require(path.is_file(), 'Missing completion file: ' + name)
    return {'namespace': namespace, 'path': name, 'sha256': sha256(path)}


def sorted_files(records):
    result = {}
    for record in records:
        key = record['namespace'], record['path']
        require(key not in result or result[key] == record, 'Conflicting evidence file hashes')
        result[key] = record
    return [result[k] for k in sorted(result)]


def verify_files(manager, records):
    require(records == sorted_files(records), 'Evidence file list must be unique and sorted')
    for record in records:
        root = manager.root if record['namespace'] == 'project' else REPOSITORY
        require(anchor(root, inside(root, record['path']), record['namespace']) == record,
                'Completion evidence changed: ' + record['path'])


def archive_resources(manager, records):
    """Stage exact dependency bytes; ManifestManager alone publishes the copies."""
    files = []; resources = []; pending = []
    for record in sorted_files(records):
        if record['namespace'] == 'project':
            files.append(record)
            continue
        source = inside(REPOSITORY, record['path'])
        raw = source.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == record['sha256'], 'Repository dependency changed before archiving')
        relative_path = f"stage2/completion-resources/{record['sha256']}/{record['path']}"
        target = inside(manager.root, relative_path)
        if target.exists():
            require(target.is_file() and target.read_bytes() == raw, 'Conflicting immutable dependency archive')
        else:
            pending.append((relative_path, raw))
        files.append({'namespace': 'project', 'path': relative_path, 'sha256': record['sha256']})
        resources.append({'path': record['path'], 'sha256': record['sha256'], 'archive_path': relative_path})
    return sorted_files(files), resources, pending


def verify_completion_files(manager, completion, *, current=False):
    """Current live inputs still guard approval; history uses its immutable copies.

    Older completion records retain their original strict semantics. Missing
    archives are never reconstructed from whatever source files exist today.
    """
    verify_files(manager, completion['files'])
    resources = completion.get('repository_resources')
    if resources is None:
        return
    names = [r['path'] for r in resources]
    require(names == sorted(set(names)), 'Dependency archive mapping must be unique and sorted')
    require(all(f['namespace'] == 'project' for f in completion['files']), 'Archived completion cannot mix live historical repository pointers')
    for resource in resources:
        expected = f"stage2/completion-resources/{resource['sha256']}/{resource['path']}"
        require(resource['archive_path'] == expected and
                {'namespace': 'project', 'path': expected, 'sha256': resource['sha256']} in completion['files'],
                'Dependency archive mapping does not match its anchored bytes')
        if current:
            live = anchor(REPOSITORY, inside(REPOSITORY, resource['path']), 'repository')
            require(live['sha256'] == resource['sha256'], 'Current preview repository dependency changed: ' + resource['path'])


def geometry_hashes(manifest):
    return {key: document_hash(asset['versions'][-1]) for key, asset in manifest['geometry_assets'].items()}


def formal_files(manager, manifest, *, exclude=()):
    """Enumerate formal history only; never walk/copy the project directory."""
    records = []
    if manifest.get('visual_direction'):
        from runtime.visual_tasks import formal_task_files
        records.extend(anchor(manager.root,path) for path in formal_task_files(manager,manifest))
    if manifest.get('render_direction'):
        from runtime.render_context_builder import read_direction_state
        read_direction_state(manager,manifest)
        ref=manifest['render_direction']
        for item in [*ref.get('history',[]),ref]:
            for key,digest_key in [('artifact_path','hash'),('context_path','context_hash'),('scene_context_path','scene_context_hash')]:
                path=inside(manager.root,item[key])
                require(document_hash(load_data(path))==item[digest_key], 'Director history changed')
                records.append(anchor(manager.root,path))
        records.extend(anchor(manager.root,inside(manager.root,r['path'])) for r in ref['reviews'])
    for kind, entries in manifest['artifacts'].items():
        for entry in entries:
            if entry['path'] in exclude: continue
            path = inside(manager.root, entry['path']); doc = load_data(path)
            validate_contract(kind, doc)
            require(document_hash(doc) == entry['sha256'] and
                    (doc['document_id'], doc['revision'], doc['scene_version']) ==
                    (entry['document_id'], entry['revision'], entry['scene_version']),
                    'Formal history identity/hash mismatch')
            records.append(anchor(manager.root, path))
            if kind == 'reference_board':
                from runtime.reference_manager import check_reference
                records.extend(anchor(manager.root, check_reference(manager.root, ref)) for ref in doc['references'])
            if kind == 'render_metadata' and doc['render_success']:
                image = anchor(manager.root, inside(manager.root, doc['image']['path']))
                require(image['sha256'] == doc['image']['sha256'], 'Historical preview changed')
                records.append(image)
    from runtime.geometry_acquisition import validate_geometry
    for asset in manifest['geometry_assets'].values():
        for result in asset['versions']:
            validate_geometry(manager.root, result)
            paths = [s['path'] for s in result['surface_sources']]
            if result['geometry']['model']: paths.append(result['geometry']['model'])
            records.extend(anchor(manager.root, inside(manager.root, p)) for p in paths)
    return records


def capture_completion(manager, manifest, packet, metadata, job_path):
    """Called under the manifest lock before preview metadata is persisted.

    Historical preview fixtures may lack a current setup; they retain the old
    metadata behavior but gain no completion attestation or delivery authority.
    """
    if not metadata['render_success']: return None
    setup = Path(packet['outputs']['setup']); receipt_path = Path(packet['outputs']['receipt'])
    if not setup.exists() and not receipt_path.exists(): return None
    require(setup.exists() and receipt_path.exists(), 'Incomplete current preview setup evidence')
    job = load_data(job_path)
    checked = check_setup_receipt(manager, job['packet'], job['sha256'])
    require(checked == packet and packet['manifest_version'] == manifest['version'], 'Stale completion packet')
    require((metadata['project_id'], metadata['scene_version']) ==
            (manifest['project_id'], manifest['scene_version']), 'Completion identity mismatch')
    plans = current_documents(manager, manifest, PLAN_KINDS)
    docs = {**validate_scene_plans(manager, manifest, plans), **plans}
    geometry = {k: a['versions'][-1] for k, a in manifest['geometry_assets'].items()}
    require(packet['plans'] == plans and packet['geometry'] == geometry, 'Completion current inputs mismatch')
    require(packet['inputs_digest'] == document_hash({'plans': plans, 'style': docs['style_assignment'], 'geometry': geometry}),
            'Completion input digest mismatch')
    build_key = document_hash({'geometry_fingerprint_format': 2, 'blockout': plans['blockout_plan'], 'geometry': geometry})
    require(packet['blockout_key'] == build_key and packet['build_id'] == 'build_' + build_key[:16],
            'Completion build identity mismatch')
    directory = f"stage2/builds/{packet['build_id']}/{packet['inputs_digest'][:16]}"
    expected_outputs = {'blockout': f"stage2/builds/{packet['build_id']}/blockout.blend",
                        'setup': directory + '/setup.blend', 'receipt': directory + '/setup-receipt.json',
                        'preview': metadata['image']['path']}
    require(all(Path(packet['outputs'][k]).resolve() == inside(manager.root, v) for k,v in expected_outputs.items()),
            'Completion output paths mismatch')
    from runtime.style_registry import StyleRegistry, style_files
    style = StyleRegistry().load(docs['style_assignment']['style_profile'], version=docs['style_assignment']['profile_version'], project_root=manager.root)
    require(packet['style'] == style, 'Completion selected style mismatch')
    workers = {k: str(REPOSITORY/'runtime'/v) for k,v in
               {'operations':'blender_operations.py','geometry':'blender_geometry_worker.py','style':'blender_style_worker.py'}.items()}
    require(packet['workers'] == workers, 'Completion worker identity mismatch')
    required_guards = [manager.path, *(Path(p) for p in workers.values())]
    required_guards += [inside(style['root'], p) for p in style_files(style)]
    for kind in CURRENT_KINDS:
        entry = max((r for r in manifest['artifacts'][kind] if r['scene_version'] == manifest['scene_version']), key=lambda r:r['revision'])
        required_guards.append(inside(manager.root, entry['path']))
    for result in geometry.values():
        required_guards.extend(inside(manager.root, p) for p in
                               [s['path'] for s in result['surface_sources']] + ([result['geometry']['model']] if result['geometry']['model'] else []))
    require(all(packet['guard'].get(str(p.resolve())) == sha256(p) for p in required_guards),
            'Completion packet lacks current mandatory execution guards')
    worker = load_data(job['receipt']); setup_receipt = load_data(receipt_path)
    require(setup_receipt['geometry_before'] == setup_receipt['geometry_after'] == worker['geometry_digest'],
            'Setup and render geometry receipts disagree')
    blockout = Path(packet['outputs']['blockout'])
    require(blockout.is_file() and blockout.read_bytes()[:7] == b'BLENDER', 'Missing completed blockout')
    project_paths = [job_path, job['packet'], job['intent'], job['receipt'], setup, receipt_path,
                     blockout, inside(manager.root, metadata['image']['path'])]
    files = [anchor(manager.root, p) for p in project_paths]
    files += formal_files(manager, manifest, exclude=(f"stage2/previews/{metadata['pass_id']}/render_metadata.json",))
    for name, digest in packet['guard'].items():
        path = Path(name).resolve()
        # This guard was checked NOW. Its raw manifest hash cannot survive the
        # immediately following formal preview/critic/user review mutations.
        if path == manager.path: continue
        root, namespace = (manager.root, 'project') if path.is_relative_to(manager.root) else (REPOSITORY, 'repository')
        record = anchor(root, path, namespace)
        require(record['sha256'] == digest, 'Completion dependency changed')
        files.append(record)
    files, resources, pending = archive_resources(manager, files)
    completion = {'schema_version': '0.2', 'project_id': manifest['project_id'], 'scene_version': manifest['scene_version'],
                  'pass_id': metadata['pass_id'], 'build_id': metadata['build_id'], 'inputs_digest': packet['inputs_digest'],
                  'metadata_sha256': document_hash(metadata), 'documents': {k: document_hash(v) for k,v in docs.items()},
                  'geometry': geometry_hashes(manifest), 'geometry_digest': worker['geometry_digest'],
                  'files': files, 'repository_resources': resources, 'setup': relative(manager.root, setup),
                  'blockout': relative(manager.root, blockout), 'packet': relative(manager.root, job['packet'])}
    validate_contract('completion_evidence', completion)
    return completion, pending


def indexed_document(manager, record, schema):
    path = inside(manager.root, record['path']); doc = load_data(path)
    validate_contract(schema, doc)
    require(document_hash(doc) == record['sha256'] and sha256(path) == record['file_sha256'],
            'Immutable ' + schema + ' changed')
    require((doc['scene_version'], doc['pass_id']) == (record['scene_version'], record['pass_id']),
            'Immutable evidence index identity mismatch')
    return doc


def _snapshot(manager, manifest):
    from runtime.visual_review import _render_context
    context = _render_context(manager, manifest, allowed_states=('final_review_required', 'approved', 'delivered'))
    docs = context['documents']; metadata = docs['render_metadata']
    critic = current_documents(manager, manifest, ('visual_review',))['visual_review']
    validate_contract('visual_review', critic)
    require((critic['project_id'], critic['scene_version']) == (manifest['project_id'], manifest['scene_version']) and
            critic['decision'] == 'final_review_required' and critic['render_metadata_id'] == metadata['document_id'] and
            critic['image_sha256'] == metadata['image']['sha256'], 'Current final-review critic is required')
    docs['visual_review'] = critic
    entries = [r for r in manifest.get('completion_evidence', []) if
               r['scene_version'] == manifest['scene_version'] and r['pass_id'] == metadata['pass_id']]
    require(len(entries) == 1, 'Current preview lacks immutable completion evidence; run a new preview')
    completion = indexed_document(manager, entries[0], 'completion_evidence')
    require(completion['project_id'] == manifest['project_id'] and completion['build_id'] == metadata['build_id'] and
            completion['metadata_sha256'] == document_hash(metadata), 'Completion metadata mismatch')
    require(completion['documents'] == {k: document_hash(docs[k]) for k in CURRENT_KINDS} and
            completion['geometry'] == geometry_hashes(manifest), 'Current inputs differ from completed preview')
    verify_completion_files(manager, completion, current=True)
    files = formal_files(manager, manifest)
    for record in manifest.get('completion_evidence', []):
        evidence = indexed_document(manager, record, 'completion_evidence')
        verify_completion_files(manager, evidence)
        files.extend(evidence['files']); files.append(anchor(manager.root, inside(manager.root, record['path'])))
    value = {'schema_version': '0.2', 'project_id': manifest['project_id'], 'scene_version': manifest['scene_version'],
             'pass_id': metadata['pass_id'], 'documents': {k: document_hash(v) for k,v in docs.items()},
             'geometry': geometry_hashes(manifest), 'completion_sha256': document_hash(completion),
             'files': sorted_files(files), 'setup': completion['setup'], 'image': metadata['image']['path']}
    validate_contract('final_snapshot', value)
    return value


def final_review_context(manager, manifest=None):
    try:
        manifest = manager.read() if manifest is None else manifest
        value = _snapshot(manager, manifest)
        return {'snapshot': value, 'snapshot_sha256': document_hash(value),
                'manifest_version': manifest['version'], 'state': manifest['state'],
                'reviewable_files': value['files']}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise BoundaryError(f'Invalid final review evidence: {exc}') from exc


def index_record(value, path, **extra):
    return {'scene_version': value['scene_version'], 'pass_id': value['pass_id'], 'path': path,
            'sha256': document_hash(value), 'file_sha256': raw_hash(value), **extra}


def stage_final_review(manager, manifest, decision):
    from runtime.state_machine import check_scene_transition
    require(decision in ('approved','rejected'), 'Invalid final user decision')
    require(manifest['state'] == 'final_review_required', 'No current final user review is pending')
    context = final_review_context(manager, manifest); value = context['snapshot']
    path = f"stage2/final-reviews/review_{len(manifest.get('final_reviews', [])):04d}-{context['snapshot_sha256']}.json"
    manifest.setdefault('final_reviews', []).append(index_record(value, path, decision=decision))
    manifest['approvals'].append({'scope': 'final', 'scene_version': manifest['scene_version'], 'reviewer': 'user',
                                 'decision': decision, 'artifact_hashes': sorted(set([context['snapshot_sha256'], *value['documents'].values()]))})
    target = 'approved' if decision == 'approved' else 'visual_revision'
    check_scene_transition(manifest['state'], target); manifest['state'] = target
    return [(path, value)]


def validate_approved(manager, manifest):
    require(manifest['state'] in ('approved','delivered'), 'Explicit final approval is required for delivery')
    current = final_review_context(manager, manifest)['snapshot']
    records = manifest.get('final_reviews', [])
    require(records and records[-1]['decision'] == 'approved', 'Missing approved final snapshot')
    value = indexed_document(manager, records[-1], 'final_snapshot')
    require(value == current, 'Approved final snapshot is stale')
    approvals = [a for a in manifest['approvals'] if a['scope'] == 'final' and a['scene_version'] == manifest['scene_version']]
    require(approvals and approvals[-1]['reviewer'] == 'user' and approvals[-1]['decision'] == 'approved' and
            document_hash(value) in approvals[-1]['artifact_hashes'], 'Final approval does not bind this snapshot')
    return value


def provenance(manifest, value):
    return {'project_id': manifest['project_id'], 'scene_version': manifest['scene_version'],
            'snapshot_sha256': document_hash(value), 'geometry_assets': manifest['geometry_assets'],
            'scope': 'Existing completed preview PNG and setup BLEND; no new render, GLB export or web publication.',
            'portability': 'Project hierarchy retains dependency archives with original repository-relative mappings; legacy evidence may retain a separate repository hierarchy. Historical MCP packets are host-bound execution evidence; regenerate packets on a new host before execution.',
            'approval': 'The recorded explicit final user decision applies to this exact snapshot. Technical checks do not grant artistic approval.'}


def delivery_inputs(manager, manifest, value):
    records = list(value['files'])
    for record in manifest.get('final_reviews', []):
        indexed_document(manager, record, 'final_snapshot')
        records.append(anchor(manager.root, inside(manager.root, record['path'])))
    generated = {'approved-manifest.json': json_bytes(manifest), 'provenance.json': json_bytes(provenance(manifest, value))}
    sources = {}
    inventory_files = []
    for record in sorted_files(records):
        target = record['namespace'] + '/' + record['path']
        root = manager.root if record['namespace'] == 'project' else REPOSITORY
        sources[target] = inside(root, record['path'])
        inventory_files.append({'path': target, 'sha256': record['sha256']})
    inventory_files += [{'path': p, 'sha256': hashlib.sha256(b).hexdigest()} for p,b in generated.items()]
    inventory = {'schema_version':'0.2', 'project_id':manifest['project_id'], 'scene_version':manifest['scene_version'],
                 'pass_id':value['pass_id'], 'snapshot_sha256':document_hash(value),
                 'files':sorted(inventory_files, key=lambda r:r['path'])}
    validate_contract('delivery_inventory', inventory)
    return inventory, sources, generated


def verify_package(manager, record, value):
    package = filesystem_path(inside(manager.root, record['package']))
    inventory_path = package/'inventory.json'
    require(inventory_path.is_file() and sha256(inventory_path) == record['inventory_sha256'], 'Missing or changed delivery inventory')
    inventory = load_data(inventory_path); validate_contract('delivery_inventory', inventory)
    require(record['package'] == 'delivery/' + record['inventory_sha256'] and
            inventory['snapshot_sha256'] == record['snapshot_sha256'] == document_hash(value) and
            (inventory['project_id'],inventory['scene_version'],inventory['pass_id']) ==
            (value['project_id'],value['scene_version'],value['pass_id']), 'Delivery identity mismatch')
    names = [r['path'] for r in inventory['files']]
    require(names == sorted(set(names)) and 'inventory.json' not in names, 'Invalid delivery inventory entries')
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    require(actual == set(names) | {'inventory.json'}, 'Delivery package has missing or unexpected files')
    require(not any(p.is_symlink() for p in package.rglob('*')), 'Linked delivery content is unsupported')
    for entry in inventory['files']:
        require(sha256(inside(package, entry['path'])) == entry['sha256'], 'Delivery content changed: ' + entry['path'])
    approved = load_data(package/'approved-manifest.json'); validate_manifest(approved)
    require(approved['state'] == 'approved' and approved['final_reviews'][-1]['sha256'] == document_hash(value),
            'Delivery lacks the approved manifest snapshot')
    return record


def publish_delivery(manager, manifest):
    """Caller owns ManifestManager lock; staging is disposable, package immutable."""
    value = validate_approved(manager, manifest)
    if manifest['state'] == 'delivered':
        records = manifest.get('deliveries', [])
        require(records and records[-1]['snapshot_sha256'] == document_hash(value), 'Missing registered delivery')
        return verify_package(manager, records[-1], value), None
    inventory, sources, generated = delivery_inputs(manager, manifest, value)
    digest = raw_hash(inventory)
    record = {'scene_version':manifest['scene_version'], 'pass_id':value['pass_id'],
              'package':'delivery/'+digest, 'inventory_sha256':digest, 'snapshot_sha256':document_hash(value)}
    package = filesystem_path(inside(manager.root, record['package']))
    require(not package.exists(), 'Unregistered delivery package already occupies content address')
    stage = filesystem_path(Path(tempfile.mkdtemp(prefix='.delivery-stage-', dir=manager.root)))
    published = False
    try:
        for name, source in sources.items():
            target = inside(stage, name); target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filesystem_path(source), target)
        for name, data in generated.items(): inside(stage, name).write_bytes(data)
        (stage/'inventory.json').write_bytes(json_bytes(inventory))
        for item in inventory['files']:
            require(sha256(inside(stage,item['path'])) == item['sha256'], 'Delivery copy verification failed')
        require(manager.read() == manifest, 'Manifest changed during delivery staging')
        require(validate_approved(manager, manifest) == value, 'Inputs changed during delivery staging')
        package.parent.mkdir(parents=True, exist_ok=True)
        require(not package.exists(), 'Conflicting delivery appeared while staging')
        stage.rename(package); published = True
        verify_package(manager, record, value)
        return record, package
    except Exception:
        if published: shutil.rmtree(package)
        raise
    finally:
        if stage.exists(): shutil.rmtree(stage)
