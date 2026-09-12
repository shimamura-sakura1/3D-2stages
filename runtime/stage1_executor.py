import shutil
import copy
from dataclasses import asdict

from runtime.asset_router import AssetRouter
from runtime.asset_search import search_assets
from runtime.errors import BoundaryError, WorkflowError
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.validators import validate_model, validate_contract


class Stage1Executor:
    def __init__(self, manager, providers, hy3d=None):
        self.manager = manager
        self.providers = providers
        self.hy3d = hy3d

    def run(self, asset_id):
        manifest = self.manager.read()
        if manifest["mode"] in ("plan_only", "stage2_only"):
            raise BoundaryError(f"Stage 1 prohibited in {manifest['mode']} mode")
        if not manifest["plan_approved"]:
            raise BoundaryError("Approve the refined plan before asset execution")
        task = manifest["assets"][asset_id]
        if task["status"] in ("revision_requested", "failed"):
            manifest = self.manager.transition(asset_id, "reworking")
            task = manifest["assets"][asset_id]
        if task["status"] not in ("planned", "reworking"):
            raise BoundaryError(f"Asset is already {task['status']}; review it or request rework")
        revision = task["revision"]
        root = self.manager.root
        style = load_data(inside(root, manifest["style_bible"]))
        self.manager.transition(asset_id, "searching")
        try:
            report = search_assets(task, self.providers)
            atomic_write(inside(root, f"stage1/candidates/{asset_id}_rev{revision:02d}.json"), asdict(report))
            if report.candidates:
                self.manager.transition(asset_id, "candidate_found")
            decision = AssetRouter().choose(task, report)
            self.manager.transition(asset_id, "route_selected", decision.reason)
            recipe = {"route": decision.route, "score": decision.score, "reason": decision.reason,
                      "searched_providers": list(report.providers), "seed": revision,
                      "style_bible_sha256": sha256(inside(root, manifest["style_bible"]))}
            source_model = None
            if decision.candidate:
                candidate = decision.candidate
                source_model = self.providers[candidate["provider"]].acquire(
                    candidate["candidate_id"], inside(root, f"stage1/sources/{asset_id}/rev{revision:02d}"))
                source_model = validate_model(source_model)
                expected = inside(root, f"stage1/sources/{asset_id}/rev{revision:02d}")
                if not source_model.resolve().is_relative_to(expected):
                    raise BoundaryError("Provider wrote outside its source directory")
                source = candidate["source"]
                recipe.update(source_sha256=sha256(source_model), source_scale_m=candidate["scale_m"])
            output_dir = inside(root, f"stage1/outputs/{asset_id}/rev{revision:02d}")
            if decision.route == "library_direct":
                output_dir.mkdir(parents=True, exist_ok=True)
                model = output_dir / f"asset{source_model.suffix}"
                if model.exists():
                    raise BoundaryError("Existing output will not be overwritten")
                shutil.copy2(source_model, model)
            else:
                if not self.hy3d:
                    raise BoundaryError("HY3D gateway is not configured; no generation was performed")
                if decision.route == "hy3d_generate":
                    source = self.hy3d.config.get("output_source")
                    if not source or not AssetRouter().legal({"source": source}, modification=True):
                        raise BoundaryError("Configure verified output rights for the selected HY3D backend")
                    # Validate provenance before any paid or expensive request.
                    source = copy.deepcopy(source)
                    validate_contract("stage1_result", {"asset_id": asset_id, "revision": revision,
                                      "route": decision.route, "source": source,
                                      "files": {"model": "stage1/outputs/prospective.glb"},
                                      "sha256": "0" * 64, "status": "review_required", "recipe": {}})
                prompt = task["hy3d"]["prompt"] or task["target"]["description"]
                for event in reversed(manifest["history"]):
                    if event["asset_id"] == asset_id and event["action"] == "review" and event["detail"]:
                        prompt += "\nRevision instruction: " + event["detail"]
                        break
                kwargs = {"prompt": prompt,
                          "reference_images": [inside(root, p) for p in task["hy3d"]["reference_images"]],
                          "output_dir": output_dir, "style_bible": style, "seed": revision}
                recipe.update(prompt=prompt, backend_type=self.hy3d.kind,
                              reference_sha256=[sha256(p) for p in kwargs["reference_images"]])
                self.manager.transition(asset_id, "generating")
                if decision.route == "library_hy3d_refine":
                    recipe["operation"] = "retexture_mesh"
                    model = self.hy3d.retexture_mesh(mesh=source_model, **kwargs)
                elif task["hy3d"]["mode"] == "shape":
                    recipe["operation"] = "generate_shape"
                    model = self.hy3d.generate_shape(**kwargs)
                else:
                    recipe["operation"] = "generate_textured_asset"
                    model = self.hy3d.generate_textured_asset(**kwargs)
            validate_model(model)
            result = {"asset_id": asset_id, "revision": revision, "route": decision.route,
                      "source": source, "files": {"model": model.relative_to(root).as_posix()},
                      "sha256": sha256(model), "status": "review_required", "recipe": recipe}
            atomic_write(inside(root, f"stage1/results/{asset_id}_rev{revision:02d}.json"), result)
            self.manager.submit_result(result)
            if manifest["auto_approve"]:
                self.manager.review({"asset_id": asset_id, "revision": revision, "decision": "approved",
                                     "issues": [], "instruction": "", "reviewer": "automatic"})
            return result
        except (WorkflowError, OSError, ValueError) as exc:
            current = self.manager.read()["assets"][asset_id]["status"]
            if current in ("searching", "candidate_found", "route_selected", "generating"):
                self.manager.transition(asset_id, "failed", str(exc))
            raise
