"""Prepare Codex MCP calls and validate their on-disk outputs before accepting a build.

The CLI cannot invoke tools owned by a Codex session. It emits concrete steps for
that session and never labels an emitted request as a completed Blender build.
"""
import json
import re
import uuid
from pathlib import Path

from runtime.errors import BoundaryError
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.stage2_executor import input_digest
from runtime.validators import stage2_preflight, validate_model


class McpBlenderExecutor:
    def __init__(self, manager):
        self.manager = manager

    def prepare(self, plan_path="stage2/blender_plan.yaml"):
        root = self.manager.root
        manifest = self.manager.read()
        plan = load_data(inside(root, plan_path))
        resolved = stage2_preflight(root, manifest, plan)
        digest = input_digest(root, manifest, plan)
        build_id = "mcp-" + uuid.uuid4().hex[:12]
        directory = inside(root, f"stage2/scene/{build_id}")
        directory.mkdir(parents=True)
        worker = Path(__file__).with_name("blender_worker.py").resolve()
        request = {"plan": plan, "assets": resolved,
                   "style": load_data(inside(root, manifest["style_bible"])), "output_dir": str(directory)}
        request_path = directory / "request.json"
        atomic_write(request_path, request)
        ticket = {"build_id": build_id, "plan": plan_path, "manifest_version": manifest["version"],
                  "input_digest": digest, "request_sha256": sha256(request_path), "worker_sha256": sha256(worker)}
        atomic_write(directory / "ticket.json", ticket)
        key = "two_stage_3d_" + build_id
        guarded_paths = [self.manager.path, inside(root, plan_path), inside(root, manifest["style_bible"]),
                         worker, request_path, *(Path(p) for p in resolved.values())]
        guard = {str(path): sha256(path) for path in guarded_paths}
        load_code = (
            "import bpy, json, hashlib, runpy\nfrom pathlib import Path\n"
            f"def _check_build_inputs(expected={guard!r}):\n"
            "    import hashlib\n    from pathlib import Path\n"
            "    for name, digest in expected.items():\n"
            "        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, 'Build input changed: ' + name\n"
            "_check_build_inputs()\n"
            f"_request_file = Path({str(request_path)!r})\n_worker_file = Path({str(worker)!r})\n"
            f"assert hashlib.sha256(_request_file.read_bytes()).hexdigest() == {ticket['request_sha256']!r}, 'Request changed'\n"
            f"assert hashlib.sha256(_worker_file.read_bytes()).hexdigest() == {ticket['worker_sha256']!r}, 'Worker changed'\n"
            f"assert {key!r} not in bpy.app.driver_namespace, 'Job already loaded; inspect its state before retrying'\n"
            "_request = json.loads(_request_file.read_text(encoding='utf-8'))\n"
            "assert all(Path(p).is_file() for p in _request['assets'].values()), 'Blender cannot access project files'\n"
            f"bpy.app.driver_namespace[{key!r}] = {{'module': runpy.run_path(str(_worker_file)), 'request': _request, 'guard': _check_build_inputs, 'state': 'loaded'}}\n"
            "print('two-stage-3d: request loaded; no scene changes yet')"
        )
        lookup = f"import bpy\n_job = bpy.app.driver_namespace[{key!r}]\n"
        prefix = lookup + "_job['guard']()\n"
        assemble = prefix + (
            "assert _job['state'] == 'loaded', 'Inspect job state before repeating assembly'\n"
            "_job['state'] = 'assembling'\n"
            "_job['scene'] = _job['module']['build'](_job['request'], export=False)\n"
            "_job['state'] = 'assembled'\nprint('two-stage-3d: scene assembled in a new scene')"
        )
        export = prefix + (
            "assert _job['state'] == 'assembled', 'Assembly is incomplete or export already attempted'\n"
            "_job['state'] = 'exporting'\n"
            "_job['module']['export_scene'](_job['request'], _job['scene'])\n"
            "_job['state'] = 'exported'\nprint('two-stage-3d: BLEND and GLB exported')"
        )
        render = prefix + (
            "assert _job['state'] == 'exported', 'Export is incomplete or render already queued'\n"
            "_job['state'] = 'render_queued'\n"
            "def _render_job(job=_job):\n"
            "    try:\n"
            "        job['guard']()\n"
            "        job['state'] = 'rendering'\n"
            "        job['module']['render_scene'](job['request'], job['scene'])\n"
            "        job['state'] = 'complete'\n"
            "    except Exception as exc:\n"
            "        job['state'] = 'failed'\n"
            "        job['error'] = str(exc)\n"
            "    return None\n"
            "bpy.app.timers.register(_render_job, first_interval=0.5)\n"
            "print('two-stage-3d: render queued; poll status, do not queue it again')"
        )
        status = lookup + "print({'state': _job['state'], 'error': _job.get('error')})"
        packet = {"status": "mcp_execution_required", "backend": "codex_mcp", "build_id": build_id,
                  "shared_filesystem_required": True, "tool": "mcp__blender__execute_blender_code",
                  "steps": [{"name": name, "code": code} for name, code in
                            (("load", load_code), ("assemble", assemble), ("export", export), ("render", render))],
                  "status_code": status,
                  "complete_command": ["stage2-complete", str(root), "--build-id", build_id],
                  "note": "Codex must call the MCP tool with the user's actual prompt. Preparing these steps does not execute Blender."}
        atomic_write(directory / "mcp_calls.json", packet)
        return packet

    def complete(self, build_id):
        if not re.fullmatch(r"mcp-[0-9a-f]{12}", build_id):
            raise BoundaryError("Invalid MCP build ID")
        root = self.manager.root
        directory = inside(root, f"stage2/scene/{build_id}")
        ticket = load_data(directory / "ticket.json")
        manifest = self.manager.read()
        if ticket["build_id"] != build_id or ticket["manifest_version"] != manifest["version"]:
            raise BoundaryError("MCP job refers to a stale project version; prepare a new job")
        plan = load_data(inside(root, ticket["plan"]))
        if input_digest(root, manifest, plan) != ticket["input_digest"]:
            raise BoundaryError("MCP build inputs changed; prepare a new job")
        if sha256(directory / "request.json") != ticket["request_sha256"]:
            raise BoundaryError("MCP request changed during execution")
        if sha256(Path(__file__).with_name("blender_worker.py")) != ticket["worker_sha256"]:
            raise BoundaryError("Blender worker changed during execution")
        outputs = [directory / name for name in ("scene.blend", "scene.glb", "preview.png")]
        if any(not p.is_file() or not p.stat().st_size for p in outputs):
            raise BoundaryError("MCP outputs are incomplete; no build success recorded")
        with outputs[0].open("rb") as stream:
            if stream.read(7) != b"BLENDER":
                raise BoundaryError("MCP output is not an uncompressed Blender file")
        with outputs[2].open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                raise BoundaryError("MCP preview is not a PNG")
        validate_model(outputs[1])
        atomic_write(directory / "checksums.json", {p.name: sha256(p) for p in outputs})
        return self.manager.record_stage2(ticket["plan"], [p.relative_to(root).as_posix() for p in outputs],
                                          ticket["input_digest"], ticket["manifest_version"])
