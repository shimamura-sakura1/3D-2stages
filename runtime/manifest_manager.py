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
from runtime.validators import validate_contract, validate_manifest, validate_result, validate_model


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
            if expected_version is not None and value["version"] != expected_version:
                raise BoundaryError("Stale project version; reload before submitting")
            mutate(value)
            value["version"] += 1
            value["history"].append({"time": datetime.now(timezone.utc).isoformat(),
                                     "action": action, "asset_id": asset_id, "detail": detail})
            validate_manifest(value)
            atomic_write(self.path, value)
        return value

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
