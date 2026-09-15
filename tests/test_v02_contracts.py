"""Phase 1: actual contracts, pure state checks, and legacy isolation."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys

import pytest

from runtime.errors import BoundaryError, ValidationError
from runtime.io import load_data
from runtime.manifest_manager import ManifestManager
from runtime.validators import validate_contract, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
KINDS = ["visual_brief", "reference_board", "scene_spec", "style_assignment",
         "blockout_plan", "lookdev_plan", "render_plan", "semantic_material_map",
         "visual_review", "revision_plan", "render_metadata", "project_manifest_v02"]
STATES = ["initialized", "visual_planning", "visual_review_required", "visual_approved",
          "geometry_pending", "geometry_review_required", "geometry_approved",
          "blockout_pending", "lookdev_pending", "render_pending", "render_review_required",
          "visual_revision", "final_review_required", "approved", "delivered"]
EDGES = set(zip(STATES[:11], STATES[1:11])) | {
    ("render_review_required", "visual_revision"), ("visual_revision", "render_pending"),
    ("visual_revision", "lookdev_pending"), ("render_review_required", "final_review_required"),
    ("final_review_required", "approved"), ("approved", "delivered"),
    ("visual_review_required", "visual_planning"), ("geometry_review_required", "geometry_pending"),
    ("final_review_required", "visual_revision"),
}


def fixture():
    return json.loads((ROOT / "tests/fixtures/v02/industrial_station.json").read_text())


def cli(*args):
    result = subprocess.run([sys.executable, "runtime/cli.py", *map(str, args)],
                            cwd=ROOT, text=True, capture_output=True, timeout=30)
    return result.returncode, json.loads(result.stdout if result.returncode == 0 else result.stderr)


@pytest.mark.parametrize("kind", KINDS)
def test_new_schema_valid_and_versioned(kind):
    document = fixture()["documents"][kind]
    assert validate_contract(kind, document) == document
    for bad in ({}, dict(document, schema_version="0.1"), dict(document, unrecognized=True)):
        with pytest.raises(ValidationError):
            validate_contract(kind, bad)


@pytest.mark.parametrize("kind,field,bad", [
    ("reference_board", "references.0.roles", ["everything"]),
    ("reference_board", "references.0.path", "../outside.png"),
    ("reference_board", "references.0.path", "C:\\outside.png"),
    ("reference_board", "references.0.weight", 2),
    ("render_plan", "preview.samples", 0),
    ("visual_review", "categories.plasticity.score", 1.1),
    ("revision_plan", "actions.0.action", "execute_python"),
    ("revision_plan", "max_preview_passes", 4),
    ("render_metadata", "visual_approved", True),
    ("render_metadata", "timestamp", "2026-09-14T000000+00:00"),
    ("render_metadata", "timestamp", "2026-02-30T00:00:00Z"),
    ("render_metadata", "timestamp", "2026-09-14T00:00:00"),
    ("semantic_material_map", "mappings.0.material_class", "whatever"),
])
def test_schema_rejects_bad_semantics(kind, field, bad):
    document = fixture()["documents"][kind]
    validate_contract(kind, document)
    target = document
    keys = field.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    target[keys[-1]] = bad
    with pytest.raises(ValidationError):
        validate_contract(kind, document)


def audit(bundle, output):
    return subprocess.run([sys.executable, "scripts/check_visual_contracts.py", "--output", str(output)],
                          input=json.dumps(bundle), cwd=ROOT, text=True, capture_output=True, timeout=30)


def test_complete_bundle_real_io(tmp_path):
    bundle = fixture()
    result = audit(bundle, tmp_path / "audit")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["approval_granted"] is False
    for kind, original in bundle["documents"].items():
        assert load_data(tmp_path / "audit" / f"{kind}.json") == original
    # An existing audit is never silently overwritten.
    before = {p.name: p.read_bytes() for p in (tmp_path / "audit").iterdir()}
    assert audit(bundle, tmp_path / "audit").returncode == 2
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "audit").iterdir()}


@pytest.mark.parametrize("case", ["missing", "project", "version", "reference", "object",
                                 "material", "render_hash", "review", "revision", "transition"])
def test_cross_document_rejection_is_atomic(tmp_path, case):
    bundle = fixture(); docs = bundle["documents"]
    if case == "missing": del docs["render_plan"]
    elif case == "project": docs["visual_review"]["project_id"] = "another"
    elif case == "version": docs["render_metadata"]["scene_version"] = 2
    elif case == "reference": docs["style_assignment"]["references"][0]["reference_id"] = "missing"
    elif case == "object": docs["blockout_plan"]["objects"][0]["object_id"] = "missing"
    elif case == "material": docs["lookdev_plan"]["material_map_id"] = "missing"
    elif case == "render_hash": docs["render_metadata"]["render_plan_hash"] = "f" * 64
    elif case == "review": docs["visual_review"]["render_metadata_id"] = "missing"
    elif case == "revision": docs["revision_plan"]["based_on_review_id"] = "missing"
    else: bundle["transitions"] = [{"current": "initialized", "target": "approved"}]
    output = tmp_path / "output"
    result = audit(bundle, output)
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stderr)["error"]
    assert not output.exists()


def test_all_scene_edges_and_asset_isolation():
    from runtime.state_machine import check_scene_transition, check_transition
    for current, target in itertools.product(STATES, repeat=2):
        if (current, target) in EDGES:
            check_scene_transition(current, target)
        else:
            with pytest.raises(BoundaryError, match="Illegal scene transition"):
                check_scene_transition(current, target)
    for current, target in [("unknown", "initialized"), ("initialized", "unknown")]:
        with pytest.raises(BoundaryError): check_scene_transition(current, target)
    check_transition("review_required", "approved")
    with pytest.raises(BoundaryError): check_transition("visual_review_required", "visual_approved")
    code, result = cli("scene-transition-check", "render_review_required", "visual_revision")
    assert code == 0 and result["execution"] == "not_performed"
    assert cli("scene-transition-check", "initialized", "approved")[0] == 2


def test_new_manifest_dispatch_and_legacy_default(tmp_path):
    code, result = cli("init-v02", tmp_path / "visual", "--id", "station", "--brief", "Industrial station")
    assert code == 0, result
    assert result["schema_version"] == "0.2" and result["state"] == "initialized"
    assert result["mode"] == "plan_only" and not result["auto_approve"]
    assert result["approvals"] == [] and result["artifacts"] == {}
    assert cli("status", tmp_path / "visual") == (0, result)
    validate_manifest(result)
    code, legacy = cli("init", tmp_path / "old", "--id", "legacy", "--brief", "Legacy station")
    assert code == 0 and legacy["schema_version"] == "0.1"
    validate_manifest(legacy)
    with pytest.raises(ValidationError): validate_manifest(dict(legacy, schema_version="0.2"))
    with pytest.raises(ValidationError): validate_manifest(dict(result, schema_version="0.1"))
    with pytest.raises(ValidationError, match="Unsupported manifest schema_version"):
        validate_manifest(dict(result, schema_version="99"))
    with pytest.raises(ValidationError): validate_manifest(dict(result, state="approved"))


@pytest.mark.parametrize("args", [
    ["run"], ["approve-plan"], ["approve-final"], ["deliver"],
    ["configure", "--mode", "full_pipeline", "--auto-approve"],
    ["stage1", "--asset-id", "bench"], ["stage2"],
    ["stage2-complete", "--build-id", "mcp-000000000000"],
    ["review", "bench", "--decision", "approved"],
])
def test_legacy_commands_cannot_mutate_visual_project(tmp_path, args):
    project = tmp_path / "visual"
    assert cli("init-v02", project, "--id", "station", "--brief", "Station")[0] == 0
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    code, result = cli(args[0], project, *args[1:])
    assert code == 2 and "unavailable for schema 0.2" in result["error"]
    assert before == {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    with pytest.raises(BoundaryError, match="unavailable for schema 0.2"):
        ManifestManager(project).approve_plan()


def test_read_only_migration_preserves_legacy_and_reports_missing_input(approved):
    from runtime.migrations.v01_to_v02 import plan_migration
    from runtime.delivery_executor import DeliveryExecutor
    approved.set_delivery_target("asset")
    DeliveryExecutor(approved).run()
    original = approved.read(); saved = copy.deepcopy(original)
    before = {p.relative_to(approved.root): p.read_bytes() for p in approved.root.rglob('*') if p.is_file()}
    report = plan_migration(original)
    assert report["status"] == "migration_required_input"
    assert set(report["required_inputs"]) == {"visual_brief", "reference_board", "scene_spec", "style_assignment"}
    draft = report["candidate_manifest"]
    validate_manifest(draft)
    assert draft["legacy_manifest"] == original
    assert draft["assets"] == original["assets"]
    assert draft["supplied_assets"] == original["supplied_assets"]
    assert draft["state"] == "initialized" and draft["approvals"] == []
    assert draft["mode"] == "plan_only" and draft["auto_approve"] is False
    code, actual = cli("migrate-v02", approved.root)
    assert code == 0 and actual == report
    draft["assets"]["bench"]["result"]["source"]["creator"] = "mutated draft"
    assert original == saved
    assert before == {p.relative_to(approved.root): p.read_bytes() for p in approved.root.rglob('*') if p.is_file()}
    with pytest.raises(ValidationError): plan_migration(dict(original, schema_version="0.2"))


def test_direct_executors_and_manager_cannot_bypass_version_gate(tmp_path):
    from runtime.blender_mcp import McpBlenderExecutor
    from runtime.delivery_executor import DeliveryExecutor
    from runtime.stage1_executor import Stage1Executor
    from runtime.stage2_executor import Stage2Executor
    project = tmp_path / "visual"
    assert cli("init-v02", project, "--id", "station", "--brief", "Station")[0] == 0
    manager = ManifestManager(project)
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    operations = [lambda: Stage1Executor(manager, {}).run("bench"),
                  lambda: Stage2Executor(manager, backend="batch").run(),
                  lambda: McpBlenderExecutor(manager).prepare(),
                  lambda: McpBlenderExecutor(manager).complete("mcp-000000000000"),
                  lambda: DeliveryExecutor(manager).run()]
    for operation in operations:
        with pytest.raises(BoundaryError, match="unavailable for schema 0.2"):
            operation()
    assert before == {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    with pytest.raises(BoundaryError, match="Workers"):
        ManifestManager(tmp_path / "worker", role="worker").create(manager.read())
    assert cli("init-v02", project, "--id", "station", "--brief", "Overwrite attempt")[0] == 2
    assert before == {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}


def test_visual_approval_requires_current_scoped_hashes():
    manifest = fixture()["documents"]["project_manifest_v02"]
    for i, kind in enumerate(["visual_brief", "reference_board", "scene_spec", "style_assignment"], 1):
        manifest["artifacts"][kind] = [{"document_id": kind + "_01", "revision": 0,
            "scene_version": 1, "path": f"stage0/{kind}_rev00.json", "sha256": str(i) * 64}]
    manifest["state"] = "visual_approved"
    manifest["approvals"] = [{"scope": "visual", "scene_version": 1, "reviewer": "user",
                              "decision": "approved", "artifact_hashes": [str(i) * 64 for i in range(1, 5)]}]
    validate_manifest(manifest)
    stale = copy.deepcopy(manifest)
    stale["scene_version"] = 2
    with pytest.raises(ValidationError): validate_manifest(stale)
    stale = copy.deepcopy(manifest)
    stale["approvals"][0]["artifact_hashes"] = ["f" * 64]
    with pytest.raises(ValidationError): validate_manifest(stale)
    stale = copy.deepcopy(manifest)
    stale["approvals"].append(dict(stale["approvals"][0], decision="rejected"))
    with pytest.raises(ValidationError): validate_manifest(stale)


@pytest.mark.parametrize("case", ["duplicate", "parent_cycle", "role_expansion", "index_hash", "pass_limit", "timestamp"])
def test_additional_bundle_integrity(tmp_path, case):
    bundle = fixture(); docs = bundle["documents"]
    if case == "duplicate": docs["reference_board"]["references"] *= 2
    elif case == "parent_cycle": docs["blockout_plan"]["objects"][0]["parent"] = "platform"
    elif case == "role_expansion": docs["style_assignment"]["references"][0]["roles"] = ["lighting"]
    elif case == "index_hash":
        docs["project_manifest_v02"]["artifacts"]["visual_brief"] = [{"document_id":"visual_brief_01",
            "revision":0,"scene_version":1,"path":"stage0/brief.json","sha256":"f"*64}]
    elif case == "pass_limit": docs["revision_plan"]["max_preview_passes"] = 1
    else: docs["render_metadata"]["timestamp"] = "not-a-timestamp"
    result = audit(bundle, tmp_path / "out")
    assert result.returncode == 2, result.stdout
    assert json.loads(result.stderr)["error"]
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("raw", ['{"documents":{},"documents":{},"transitions":[]}', '{"documents":NaN}', '{"documents":Infinity}'])
def test_audit_rejects_ambiguous_json(tmp_path, raw):
    result = subprocess.run([sys.executable, "scripts/check_visual_contracts.py", "--output", str(tmp_path / "out")],
                            input=raw, text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]
    assert not (tmp_path / "out").exists()
