import shutil
import uuid

from runtime.errors import BoundaryError
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.stage2_executor import input_digest
from runtime.validators import validate_contract, validate_result


def verify_current_build(manager, manifest):
    stage2 = manifest["stage2"]
    if stage2["status"] not in ("built", "approved"):
        raise BoundaryError("Build is missing or stale")
    plan = load_data(inside(manager.root, stage2["plan"]))
    if input_digest(manager.root, manifest, plan) != stage2["input_digest"]:
        raise BoundaryError("Build inputs changed; rebuild before final review or delivery")
    if not stage2["outputs"]:
        raise BoundaryError("Build has no outputs")
    checksums = load_data(inside(manager.root, stage2["outputs"][0]).parent / "checksums.json")
    for relative in stage2["outputs"]:
        path = inside(manager.root, relative)
        if not path.is_file() or checksums.get(path.name) != sha256(path):
            raise BoundaryError("Build outputs changed or are missing")


class DeliveryExecutor:
    def __init__(self, manager):
        self.manager = manager

    def run(self):
        manifest = self.manager.read()
        if manifest["mode"] == "plan_only":
            raise BoundaryError("Delivery prohibited in plan_only mode")
        target = manifest["delivery"]["target"]
        if target == "web" or manifest["delivery"]["web_deploy"]:
            raise BoundaryError("Web delivery/deployment is deferred beyond Phase 1")
        sources, attribution = [], []
        if target == "asset":
            required = [t for t in manifest["assets"].values() if t["required"]]
            if not manifest["allow_partial"] and any(t["status"] != "approved" for t in required):
                raise BoundaryError("Required assets must be approved before asset delivery")
            for task in manifest["assets"].values():
                if task["status"] == "approved":
                    path = validate_result(self.manager.root, task["result"])
                    sources.append((path, task["asset_id"] + path.suffix))
                    attribution.append(task["result"]["source"])
            if not sources:
                raise BoundaryError("No approved assets to deliver")
        else:
            if manifest["stage2"]["status"] != "approved":
                raise BoundaryError("Scene delivery requires final user approval")
            verify_current_build(self.manager, manifest)
            sources = [(inside(self.manager.root, p), inside(self.manager.root, p).name)
                       for p in manifest["stage2"]["outputs"]]
            plan = load_data(inside(self.manager.root, manifest["stage2"]["plan"]))
            for entry in plan["assets"]:
                asset_id = entry["asset_id"]
                if manifest["mode"] == "stage2_only" and asset_id in manifest["supplied_assets"]:
                    attribution.append(manifest["supplied_assets"][asset_id]["source"])
                else:
                    attribution.append(manifest["assets"][asset_id]["result"]["source"])
        output = inside(self.manager.root, f"delivery/outputs/package-{uuid.uuid4().hex[:12]}")
        output.mkdir(parents=True)
        delivered = []
        for source, name in sources:
            destination = output / name
            shutil.copy2(source, destination)
            delivered.append(destination.relative_to(self.manager.root).as_posix())
        report = {"target": target, "files": delivered, "attribution": attribution}
        validate_contract("delivery", report)
        atomic_write(output / "delivery.yaml", report)
        atomic_write(output / "manifest.snapshot.yaml", manifest)
        shutil.copy2(inside(self.manager.root, manifest["style_bible"]), output / "style_bible.yaml")
        atomic_write(output / "attribution.yaml", {"sources": attribution})
        atomic_write(output / "checksums.json", {name: sha256(output / name) for _, name in sources})
        self.manager.complete_delivery(manifest["version"])
        return report
