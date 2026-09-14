import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from runtime.errors import BoundaryError, WorkflowError
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.validators import stage2_preflight, validate_model, require_legacy_manifest
from runtime.platform_support import find_blender


def input_digest(root, manifest, plan):
    paths = stage2_preflight(root, manifest, plan)
    value = {"plan": plan, "assets": {k: sha256(p) for k, p in paths.items()},
             "style": sha256(inside(root, manifest["style_bible"]))}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Stage2Executor:
    def __init__(self, manager, blender=None, runner=None, backend="mcp"):
        self.manager = manager
        self.blender = blender
        self.runner = runner or subprocess.run
        if backend not in ("mcp", "batch"):
            raise BoundaryError("Blender backend must be mcp or batch")
        self.backend = backend

    def run(self, plan_path="stage2/blender_plan.yaml", dry_run=False):
        manifest = self.manager.read()
        require_legacy_manifest(manifest)
        root = self.manager.root
        plan = load_data(inside(root, plan_path))
        resolved = stage2_preflight(root, manifest, plan)
        digest = input_digest(root, manifest, plan)
        if dry_run:
            return {"status": "preflight_passed", "assets": resolved, "input_digest": digest,
                    "note": "No Blender execution and no scene output created"}
        if self.backend == "mcp":
            from runtime.blender_mcp import McpBlenderExecutor
            return McpBlenderExecutor(self.manager).prepare(plan_path)
        executable = find_blender(self.blender)
        build_dir = inside(root, f"stage2/scene/build-{uuid.uuid4().hex[:12]}")
        build_dir.mkdir(parents=True)
        request = {"plan": plan, "assets": resolved, "style": load_data(inside(root, manifest["style_bible"])),
                   "output_dir": str(build_dir)}
        request_path = build_dir / "request.json"
        atomic_write(request_path, request)
        script = Path(__file__).with_name("blender_worker.py")
        command = [executable, "--background", "--factory-startup", "--disable-autoexec",
                   "--python-exit-code", "1", "--python", str(script), "--", str(request_path)]
        try:
            with (build_dir / "blender.log").open("w", encoding="utf-8") as log:
                result = self.runner(command, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=False)
            if result.returncode:
                raise WorkflowError(f"Blender failed; inspect {build_dir / 'blender.log'}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkflowError(f"Blender execution failed: {type(exc).__name__}") from exc
        outputs = [build_dir / "scene.blend", build_dir / "scene.glb", build_dir / "preview.png"]
        if any(not p.is_file() or not p.stat().st_size for p in outputs):
            raise WorkflowError("Blender did not produce all expected outputs")
        validate_model(build_dir / "scene.glb")
        if input_digest(root, self.manager.read(), load_data(inside(root, plan_path))) != digest:
            raise BoundaryError("Build inputs changed during execution; outputs cannot be approved")
        atomic_write(build_dir / "checksums.json", {p.name: sha256(p) for p in outputs})
        return self.manager.record_stage2(plan_path, [p.relative_to(root).as_posix() for p in outputs],
                                          digest, manifest["version"])
