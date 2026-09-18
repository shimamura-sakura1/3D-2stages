import copy
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from runtime.errors import BoundaryError
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.state_machine import check_transition
from runtime.validators import validate_contract, validate_manifest, validate_result, validate_model, require_legacy_manifest


class ManifestManager:
    """Single-writer application boundary. OS isolation is the host's responsibility."""

    def __init__(self, root, role="parent"):
        self.root = Path(root).resolve()
        self.path = inside(self.root, "manifest.yaml")
        self.role = role

    @contextmanager
    def _lock(self):
        if self.role != "parent":
            raise BoundaryError("Workers may submit isolated results, not mutate the manifest")
        self.root.mkdir(parents=True, exist_ok=True)
        lock = inside(self.root, ".manifest.lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise BoundaryError("Manifest is busy; retry after the current writer finishes") from exc
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def read(self):
        return validate_manifest(load_data(self.path))

    def create(self, manifest):
        with self._lock():
            if self.path.exists():
                raise BoundaryError("Project already exists")
            value = copy.deepcopy(manifest)
            validate_manifest(value)
            if value["schema_version"] == "0.2":
                if (value["state"] != "initialized" or value["version"] != 0 or value["scene_version"] != 1
                        or value["mode"] != "plan_only" or value["auto_approve"] or value["allow_partial"]
                        or value["approvals"] or value["history"] or value["artifacts"]
                        or value["assets"] or value["supplied_assets"] or value["legacy_manifest"] is not None
                        or value["migration_required_input"]
                        or value.get('completion_evidence') or value.get('final_reviews') or value.get('deliveries')
                        or value.get('render_direction')):
                    raise BoundaryError("New visual projects must be empty, initialized and unapproved; migration drafts are not installable")
                atomic_write(self.path, value)
                return value
            if (value["version"] != 0 or value["history"] or value["stage2"]["status"] != "not_started"
                    or value["plan_approved"] or value["supplied_assets"]
                    or any(t["status"] != "planned" or t["result"] is not None or t["revision"] != 0
                           for t in value["assets"].values())):
                raise BoundaryError("New projects must start with an unapproved plan and planned assets")
            atomic_write(self.path, value)
        return value

    def _change(self, action, mutate, asset_id=None, detail="", expected_version=None):
        with self._lock():
            value = self.read()
            require_legacy_manifest(value)
            if expected_version is not None and value["version"] != expected_version:
                raise BoundaryError("Stale project version; reload before submitting")
            mutate(value)
            value["version"] += 1
            value["history"].append({"time": datetime.now(timezone.utc).isoformat(),
                                     "action": action, "asset_id": asset_id, "detail": detail})
            validate_manifest(value)
            atomic_write(self.path, value)
        return value

    def _visual_change(self, action, mutate, expected_version):
        """Validated single-writer boundary for explicit v0.2 operations."""
        with self._lock():
            value = self.read()
            if value['schema_version'] != '0.2':
                raise BoundaryError('This operation requires schema 0.2')
            if expected_version is None or value['version'] != expected_version:
                raise BoundaryError('Stale project version; reload before submitting')
            # Mutators return staged documents; no file writes until validation succeeds.
            pending = mutate(value) or []
            value['version'] += 1
            value['history'].append({'time': datetime.now(timezone.utc).isoformat(),
                                     'action': action, 'asset_id': None, 'detail': ''})
            validate_manifest(value)
            for path, document in pending:
                if inside(self.root, path).exists():
                    raise BoundaryError('Immutable artifact path already exists')
            created = []
            try:
                for path, document in pending:
                    target = inside(self.root, path)
                    created.append(target)
                    if isinstance(document, bytes):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open('xb') as stream:
                            stream.write(document)
                            stream.flush()
                            os.fsync(stream.fileno())
                    else:
                        atomic_write(target, document)
                atomic_write(self.path, value)
            except Exception:
                # Only paths proven absent before this transaction are removed.
                # Shared content-addressed archives are verified and not staged.
                for target in reversed(created):
                    if target.is_file():
                        target.unlink()
                raise
            return value

    def import_style(self, source, *, expected_version):
        """Import package bytes without selecting a direction or approving artwork."""
        from runtime.user_styles import stage_import
        return self._visual_change('style_import', lambda m: stage_import(self, m, source), expected_version)

    def submit_visual_plan(self, documents, *, expected_version):
        from runtime.visual_planning import validate_plan, STAGE0_KINDS
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        documents = copy.deepcopy(documents)
        def mutate(m):
            if m['state'] not in ('initialized', 'visual_planning', 'visual_review_required'):
                raise BoundaryError('Visual planning requires an initialized or pending visual review project')
            validate_plan(self.root, m, documents)
            if m['state'] != 'visual_planning':
                check_scene_transition(m['state'], 'visual_planning')
                m['state'] = 'visual_planning'
            pending = []
            for kind in STAGE0_KINDS:
                doc = documents[kind]
                records = m['artifacts'].setdefault(kind, [])
                revision = max((r['revision'] for r in records), default=-1) + 1
                if doc['revision'] != revision:
                    raise BoundaryError('Document revision must be the next immutable revision')
                path = f"stage0/rev_{revision:04d}/{kind}.yaml"
                records.append({'document_id': doc['document_id'], 'revision': revision,
                                'scene_version': m['scene_version'], 'path': path, 'sha256': document_hash(doc)})
                pending.append((path, doc))
            check_scene_transition(m['state'], 'visual_review_required')
            m['state'] = 'visual_review_required'
            return pending
        return self._visual_change('stage0_submit', mutate, expected_version)

    def review_visual(self, decision, *, expected_version):
        from runtime.visual_planning import current_documents, validate_plan
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        if decision not in ('approved', 'rejected'):
            raise BoundaryError('Unknown visual decision')
        def mutate(m):
            if m['state'] != 'visual_review_required':
                raise BoundaryError('No current visual review is pending')
            docs = current_documents(self, m)
            validate_plan(self.root, m, docs)
            target = 'visual_approved' if decision == 'approved' else 'visual_planning'
            check_scene_transition(m['state'], target)
            m['approvals'].append({'scope': 'visual', 'scene_version': m['scene_version'],
                                   'reviewer': 'user', 'decision': decision,
                                   'artifact_hashes': [document_hash(d) for d in docs.values()]})
            m['state'] = target
        return self._visual_change('visual_review', mutate, expected_version)

    def configure_visual(self, mode, *, expected_version):
        if mode not in ('plan_only', 'stage1_only', 'stage2_only', 'full_pipeline', 'repair'):
            raise BoundaryError('Unknown visual execution mode')
        return self._visual_change('visual_configuration', lambda m: m.update(mode=mode), expected_version)

    def submit_geometry(self, result, *, expected_version):
        from runtime.geometry_acquisition import validate_geometry
        from runtime.visual_planning import current_documents, validate_plan
        from runtime.state_machine import check_scene_transition
        result = copy.deepcopy(result)
        def mutate(m):
            if m['mode'] not in ('full_pipeline', 'stage1_only', 'repair') or m['state'] not in ('visual_approved', 'geometry_pending'):
                raise BoundaryError('Geometry submission requires authorized mode and current visual approval')
            docs = current_documents(self, m)
            validate_plan(self.root, m, docs)
            validate_geometry(self.root, result)
            object_ids = {o['object_id'] for o in docs['scene_spec']['objects']}
            asset_id = result['asset_id']
            if asset_id not in object_ids or result['scene_version'] != m['scene_version']:
                raise BoundaryError('Geometry result identity mismatch')
            assets = m.setdefault('geometry_assets', {})
            entry = assets.get(asset_id)
            if entry and entry['status'] != 'revision_requested':
                raise BoundaryError('Geometry is already reviewable; request rework first')
            versions = entry['versions'] if entry else []
            if result['revision'] != len(versions) or len(versions) > 3:
                raise BoundaryError('Stale or excessive geometry revision')
            versions.append(result)
            assets[asset_id] = {'status': 'review_required', 'versions': versions}
            if m['state'] == 'visual_approved':
                check_scene_transition(m['state'], 'geometry_pending')
                m['state'] = 'geometry_pending'
            if set(assets) == object_ids and all(a['status'] == 'review_required' for a in assets.values()):
                check_scene_transition(m['state'], 'geometry_review_required')
                m['state'] = 'geometry_review_required'
            return [(f"stage1/results/{asset_id}_geometry_rev{result['revision']:02d}.json", result)]
        return self._visual_change('geometry_submit', mutate, expected_version)

    def review_geometry(self, decision, *, expected_version):
        from runtime.geometry_acquisition import validate_geometry
        from runtime.visual_planning import current_documents, validate_plan
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        if decision not in ('approved', 'rejected'):
            raise BoundaryError('Unknown geometry decision')
        def mutate(m):
            if m['mode'] == 'plan_only' or m['state'] != 'geometry_review_required':
                raise BoundaryError('No authorized geometry review is pending')
            docs = current_documents(self, m)
            validate_plan(self.root, m, docs)
            assets = m.get('geometry_assets', {})
            if set(assets) != {o['object_id'] for o in docs['scene_spec']['objects']}:
                raise BoundaryError('Geometry does not cover the complete scene')
            hashes = [document_hash(docs['scene_spec'])]
            for entry in assets.values():
                result = entry['versions'][-1]
                validate_geometry(self.root, result)
                hashes.append(document_hash(result))
                entry['status'] = 'approved' if decision == 'approved' else 'revision_requested'
            target = 'geometry_approved' if decision == 'approved' else 'geometry_pending'
            check_scene_transition(m['state'], target)
            m['approvals'].append({'scope': 'geometry', 'scene_version': m['scene_version'],
                                   'reviewer': 'user', 'decision': decision, 'artifact_hashes': hashes})
            m['state'] = target
        return self._visual_change('geometry_review', mutate, expected_version)

    def submit_scene_plans(self, plans, *, expected_version, render_direction=None, scene_context=None):
        from runtime.scene_production import validate_scene_plans, PLAN_KINDS
        from runtime.visual_contracts import document_hash
        from runtime.visual_planning import current_documents
        from runtime.state_machine import check_scene_transition
        plans = copy.deepcopy(plans)
        def mutate(m):
            nonlocal plans
            direction_pending = []
            if m['mode'] not in ('full_pipeline', 'stage2_only', 'repair') or m['state'] not in ('geometry_approved', 'blockout_pending'):
                raise BoundaryError('Scene plans require approved geometry and authorized execution')
            if render_direction is not None:
                from runtime.render_director import initial_direction
                plans, direction_pending = initial_direction(self,m,copy.deepcopy(render_direction),scene_context,plans)
            elif m.get('render_direction'):
                raise BoundaryError('Directed plans must use reviewed direction refinement')
            validate_scene_plans(self, m, plans)
            if m['state'] == 'blockout_pending':
                old = current_documents(self, m, ('blockout_plan',))['blockout_plan']
                if document_hash(old) != document_hash(plans['blockout_plan']):
                    raise BoundaryError('Visual plan revision must preserve the existing blockout')
            pending = direction_pending
            for kind in PLAN_KINDS:
                doc = plans[kind]
                records = m['artifacts'].setdefault(kind, [])
                if records and records[-1]['sha256'] == document_hash(doc):
                    continue
                revision = max((r['revision'] for r in records), default=-1) + 1
                if doc['revision'] != revision:
                    raise BoundaryError('Scene document must use the next immutable revision')
                path = f"stage2/plans/rev_{revision:04d}/{kind}.yaml"
                records.append({'document_id': doc['document_id'], 'revision': revision,
                                'scene_version': m['scene_version'], 'path': path, 'sha256': document_hash(doc)})
                pending.append((path, doc))
            if m['state'] == 'geometry_approved':
                check_scene_transition(m['state'], 'blockout_pending')
                m['state'] = 'blockout_pending'
            return pending
        return self._visual_change('scene_plans_submit', mutate, expected_version)

    def complete_scene_setup(self, packet_path, packet_sha, *, expected_version):
        from runtime.state_machine import check_scene_transition
        from runtime.scene_production import PLAN_KINDS, validate_scene_plans
        from runtime.visual_planning import current_documents
        def mutate(m):
            from runtime.scene_production import check_setup_receipt
            check_setup_receipt(self, packet_path, packet_sha)
            if m['state'] != 'blockout_pending' or m['mode'] not in ('full_pipeline', 'stage2_only', 'repair'):
                raise BoundaryError('No authorized scene setup is pending')
            validate_scene_plans(self, m, current_documents(self, m, PLAN_KINDS))
            for target in ('lookdev_pending', 'render_pending'):
                check_scene_transition(m['state'], target)
                m['state'] = target
        return self._visual_change('scene_setup_complete', mutate, expected_version)

    def apply_visual_revision(self, revision, *, expected_version, render_direction=None):
        from runtime.revision_controller import stage_revision
        return self._visual_change('visual_revision_applied',
                                   lambda m: stage_revision(self, m, revision, render_direction=render_direction), expected_version)

    def reserve_preview(self, *, expected_version):
        from runtime.scene_production import PLAN_KINDS, validate_scene_plans
        from runtime.visual_planning import current_documents
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        def mutate(m):
            if m['mode'] not in ('full_pipeline', 'stage2_only', 'repair') or m['state'] not in ('render_pending', 'render_review_required'):
                raise BoundaryError('Preview requires an authorized, completed scene setup')
            plans = current_documents(self, m, PLAN_KINDS)
            validate_scene_plans(self, m, plans)
            from runtime.revision_controller import enforce_preview_budget, next_preview_index
            enforce_preview_budget(self, m)
            pass_id = f"pass_{next_preview_index(self):02d}"
            plan = copy.deepcopy(plans['render_plan'])
            records = m['artifacts']['render_plan']
            plan['revision'] = max(r['revision'] for r in records) + 1
            plan['output']['image_path'] = f'stage2/previews/{pass_id}/preview.png'
            path = f"stage2/plans/rev_{plan['revision']:04d}/render_plan.yaml"
            records.append({'document_id': plan['document_id'], 'revision': plan['revision'],
                            'scene_version': m['scene_version'], 'path': path, 'sha256': document_hash(plan)})
            metadata_revision = max((r['revision'] for r in m['artifacts'].get('render_metadata', [])), default=-1) + 1
            intent = {'project_id': m['project_id'], 'scene_version': m['scene_version'],
                      'manifest_version': m['version'] + 1, 'pass_id': pass_id,
                      'render_plan_hash': document_hash(plan), 'metadata_revision': metadata_revision,
                      'nonce': uuid.uuid4().hex}
            if m['state'] == 'render_review_required':
                for target in ('visual_revision', 'render_pending'):
                    check_scene_transition(m['state'], target)
                    m['state'] = target
            return [(path, plan), (f'stage2/previews/{pass_id}/intent.json', intent)]
        return self._visual_change('preview_reserved', mutate, expected_version)

    def record_preview(self, job_path, *, expected_version):
        from runtime.preview_renderer import inspect_preview
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        def mutate(m):
            if m['state'] != 'render_pending' or m['mode'] not in ('full_pipeline', 'stage2_only', 'repair'):
                raise BoundaryError('No authorized preview is pending')
            packet, metadata = inspect_preview(self, job_path)
            records = m['artifacts'].setdefault('render_metadata', [])
            revision = max((r['revision'] for r in records), default=-1) + 1
            if metadata['revision'] != revision:
                raise BoundaryError('Stale preview metadata revision')
            path = f"stage2/previews/{metadata['pass_id']}/render_metadata.json"
            records.append({'document_id': metadata['document_id'], 'revision': revision,
                            'scene_version': m['scene_version'], 'path': path, 'sha256': document_hash(metadata)})
            from runtime.visual_delivery import capture_completion, index_record
            captured = capture_completion(self, m, packet, metadata, job_path)
            pending = [(path, metadata)]
            if captured is not None:
                completion, resources = captured
                pending.extend(resources)
                evidence_path = f"stage2/previews/{metadata['pass_id']}/completion-evidence.json"
                m.setdefault('completion_evidence', []).append(index_record(completion, evidence_path))
                pending.append((evidence_path, completion))
            if metadata['render_success']:
                check_scene_transition(m['state'], 'render_review_required')
                m['state'] = 'render_review_required'
            return pending
        return self._visual_change('preview_recorded', mutate, expected_version)

    def submit_render_review(self, review, *, expected_version, director_review=None):
        """Persist an explicit diagnosis; artistic approval remains a separate user gate."""
        from runtime.visual_review import validate_render_review
        from runtime.visual_contracts import document_hash
        from runtime.state_machine import check_scene_transition
        review = copy.deepcopy(review)
        def mutate(m):
            validate_render_review(self, m, review)
            pending = []
            if m.get('render_direction'):
                if director_review is None:
                    raise BoundaryError('Directed renders require an external RenderReview')
                from runtime.render_director import stage_review
                pending = stage_review(self,m,copy.deepcopy(director_review),review)
            elif director_review is not None:
                raise BoundaryError('No registered RenderDirection for this external review')
            target = 'visual_revision' if review['decision'] == 'revision_required' else 'final_review_required'
            if m['state'] != target:
                check_scene_transition(m['state'], target)
            path = f"stage2/reviews/rev_{review['revision']:04d}/visual_review.yaml"
            m['artifacts'].setdefault('visual_review', []).append({
                'document_id': review['document_id'], 'revision': review['revision'],
                'scene_version': m['scene_version'], 'path': path, 'sha256': document_hash(review)})
            m['state'] = target
            return [*pending,(path, review)]
        return self._visual_change('render_review_submitted', mutate, expected_version)

    def final_review_v02(self, decision, *, expected_version):
        from runtime.visual_delivery import stage_final_review
        return self._visual_change('final_review_v02',
            lambda m: stage_final_review(self, m, decision), expected_version)

    def deliver_v02(self, *, expected_version):
        from runtime.visual_delivery import publish_delivery
        from runtime.state_machine import check_scene_transition
        with self._lock():
            value = self.read()
            if value['schema_version'] != '0.2' or expected_version is None or value['version'] != expected_version:
                raise BoundaryError('Delivery requires schema 0.2 and the current expected version')
            published = None
            try:
                record, published = publish_delivery(self, value)
                if published is None:
                    return record
                check_scene_transition(value['state'], 'delivered')
                value['state'] = 'delivered'
                value.setdefault('deliveries', []).append(record)
                value['version'] += 1
                value['history'].append({'time': datetime.now(timezone.utc).isoformat(),
                                         'action': 'delivered_v02', 'asset_id': None, 'detail': record['package']})
                validate_manifest(value)
                atomic_write(self.path, value)
                return record
            except Exception as exc:
                if published is not None and published.exists():
                    shutil.rmtree(published)
                if isinstance(exc, (OSError, KeyError, ValueError, TypeError)):
                    raise BoundaryError(f'Delivery failed: {exc}') from exc
                raise

    def approve_plan(self):
        return self._change("approve_plan", lambda m: m.update(plan_approved=True))

    def configure(self, *, mode=None, auto_approve=None, allow_partial=None):
        changes = {k: v for k, v in locals().items()
                   if k != "self" and v is not None}
        return self._change("user_configuration", lambda m: m.update(changes), detail=str(changes))

    def transition(self, asset_id, target, detail=""):
        if target in ("approved", "review_required", "revision_requested"):
            raise BoundaryError("Use result submission or review for this transition")
        def mutate(m):
            if m["mode"] in ("plan_only", "stage2_only"):
                raise BoundaryError(f"Stage 1 prohibited in {m['mode']} mode")
            task = m["assets"][asset_id]
            check_transition(task["status"], target)
            if target == "reworking":
                if task["revision"] >= task["review"]["max_revisions"]:
                    raise BoundaryError("Revision limit reached; revise the plan before further work")
                task["revision"] += 1
                task["result"] = None
            task["status"] = target
            m["state"] = "stage1"
        return self._change("transition", mutate, asset_id, detail or target)

    def submit_result(self, result, expected_version=None):
        result = copy.deepcopy(result)
        validate_result(self.root, result)
        def mutate(m):
            if m["mode"] in ("plan_only", "stage2_only"):
                raise BoundaryError("This execution mode cannot accept Stage 1 results")
            task = m["assets"][result["asset_id"]]
            if result["revision"] != task["revision"]:
                raise BoundaryError("Stale worker revision")
            route_flag = {"library_direct": "allow_route_a", "library_hy3d_refine": "allow_route_b",
                          "hy3d_generate": "allow_route_c"}[result["route"]]
            if not task["routing"][route_flag]:
                raise BoundaryError("Worker selected a prohibited route")
            check_transition(task["status"], "review_required")
            task.update(result=result, status="review_required")
            m["state"] = "review_required"
        return self._change("submit_result", mutate, result["asset_id"], expected_version=expected_version)

    def review(self, report):
        validate_contract("review_report", report)
        def mutate(m):
            task = m["assets"][report["asset_id"]]
            if m["mode"] in ("plan_only", "stage2_only"):
                raise BoundaryError("Stage 1 review prohibited in this execution mode")
            if task["revision"] != report["revision"]:
                raise BoundaryError("Review refers to an old revision")
            if report["reviewer"] == "automatic" and not m["auto_approve"]:
                raise BoundaryError("Automatic approval was not explicitly enabled")
            if report["decision"] == "revision_requested" and not report["instruction"].strip():
                raise BoundaryError("Rework requires a concrete revision instruction")
            check_transition(task["status"], report["decision"])
            if report["decision"] == "approved":
                validate_result(self.root, task["result"])
            task["status"] = report["decision"]
            if report["decision"] != "approved" and m["stage2"]["status"] != "not_started":
                m["stage2"]["status"] = "stale"
            m["state"] = "review_required"
        value = self._change("review", mutate, report["asset_id"], report["instruction"])
        report_path = inside(self.root, f"stage1/reviews/{report['asset_id']}_v{value['version']}.yaml")
        atomic_write(report_path, report)
        return value

    def record_stage2(self, plan, outputs, digest, expected_version):
        def mutate(m):
            m["stage2"] = {"status": "built", "plan": plan, "outputs": outputs, "input_digest": digest}
            m["state"] = "review_required"
        return self._change("stage2_built", mutate, expected_version=expected_version)

    def approve_final(self):
        def mutate(m):
            if m["stage2"]["status"] != "built":
                raise BoundaryError("Only a current, successful build can pass final review")
            from runtime.delivery_executor import verify_current_build
            verify_current_build(self, m)
            m["stage2"]["status"] = "approved"
        return self._change("final_review_approved", mutate)

    def set_delivery_target(self, target):
        return self._change("delivery_target", lambda m: m["delivery"].update(target=target))

    def supply_asset(self, asset_id, model, source):
        from runtime.asset_router import AssetRouter
        if not AssetRouter().legal({"source": source}, modification=True):
            raise BoundaryError("Supplied asset requires verified import and modification rights")
        model = validate_model(model)
        def mutate(m):
            if m["mode"] != "stage2_only":
                raise BoundaryError("Supplied assets require stage2_only mode")
            # Check identity before constructing a filesystem path.
            import re
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", asset_id):
                raise BoundaryError("Invalid asset ID")
            relative = f"stage2/inputs/{asset_id}-{uuid.uuid4().hex[:12]}{model.suffix.lower()}"
            destination = inside(self.root, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(model, destination)
            m["supplied_assets"][asset_id] = {"model": relative, "sha256": sha256(destination), "source": source}
            if m["stage2"]["status"] != "not_started":
                m["stage2"]["status"] = "stale"
        return self._change("supply_asset", mutate, asset_id)

    def complete_delivery(self, expected_version):
        return self._change("delivery", lambda m: m.update(state="complete"), expected_version=expected_version)
