"""Run the shipped guide as CLI arguments and verify its real offline artifacts."""
import copy
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from runtime.io import load_data
from runtime.migrations.v01_to_v02 import plan_migration
from runtime.visual_contracts import document_hash

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("visual_brief", "reference_board", "scene_spec", "style_assignment")


def commands(marker):
    guide = ROOT / "docs/v02/quickstart.md"
    assert guide.is_file(), "Missing executable v0.2 quickstart"
    block = guide.read_text(encoding="utf-8").split(f"<!-- executable: {marker} -->", 1)[1]
    block = block.split("```text\n", 1)[1].split("```", 1)[0]
    result = [shlex.split(line) for line in block.strip().splitlines()]
    assert all(argv[:3] == ["python", "-m", "runtime.cli"] for argv in result)
    return result


def run(argv, replacements=None):
    argv = [(replacements or {}).get(arg, arg) for arg in argv]
    result = subprocess.run([sys.executable, *map(str, argv[1:])], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    return result.returncode, json.loads(result.stdout if result.returncode == 0 else result.stderr)


def cli(*args):
    return run(["python", "-m", "runtime.cli", *args])


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def initialize(root):
    sequence = commands("v02-stage0")
    assert [argv[3] for argv in sequence] == ["init-v02", "reference-add-v02", "stage0-submit", "status"]
    for argv in sequence[:2]:
        code, output = run(argv, {"projects/v02_demo": root})
        assert code == 0, output
    return sequence


def test_quickstart_runs_twice_with_real_reference_and_no_approval(tmp_path):
    bundle = [ROOT / "templates/v02_stage0.yaml", ROOT / "examples/v02/reference.svg",
              ROOT / "examples/v02/reference_source.yaml", ROOT / "examples/v02/LICENSE.md"]
    assert all(path.is_file() for path in bundle), "Missing distributable Stage 0 template/reference bundle"
    before = {str(path): path.read_bytes() for path in bundle}
    expected = load_data(bundle[0])
    assert set(expected) == set(KINDS)
    assert expected["style_assignment"]["profile_version"] == "1.1.0"
    digests = []
    for name in ("first", "second"):
        project = tmp_path / name
        sequence = initialize(project)
        for argv in sequence[2:]:
            code, manifest = run(argv, {"projects/v02_demo": project})
            assert code == 0, manifest
        assert (manifest["schema_version"], manifest["project_id"], manifest["version"], manifest["scene_version"]) == ("0.2", "v02_demo", 1, 1)
        assert manifest["state"] == "visual_review_required"
        assert manifest["mode"] == "plan_only" and manifest["auto_approve"] is False
        assert manifest["approvals"] == [] and manifest["assets"] == {}
        assert not (project / "stage1").exists() and not (project / "stage2").exists()
        hashes = {}
        for kind in KINDS:
            record = manifest["artifacts"][kind][-1]
            actual = load_data(project / record["path"])
            assert actual == expected[kind]
            assert actual["revision"] == 0 and actual["project_id"] == "v02_demo"
            assert record["sha256"] == document_hash(actual)
            hashes[kind] = record["sha256"]
        reference = expected["reference_board"]["references"][0]
        assert reference["source"] == load_data(bundle[2])
        assert reference["source"]["kind"] == "library"
        assert reference["roles"] == ["material_language"]
        assert reference["source"]["license"] == "cc0" and reference["source"]["license_verified"] is True
        assert "examples/v02/LICENSE.md" in reference["source"]["attribution"]
        assert (project / reference["path"]).read_bytes() == before[str(bundle[1])]
        assert Path(reference["path"]).stem == "ref_material-" + hashlib.sha256(before[str(bundle[1])]).hexdigest()
        digests.append(hashes)
    assert digests[0] == digests[1]
    assert before == {str(path): path.read_bytes() for path in bundle}


@pytest.mark.parametrize("problem,message", [("reference", "hash mismatch"), ("identity", "identity mismatch"), ("version", "version")])
def test_quickstart_rejects_tampering_and_stale_version_atomically(tmp_path, problem, message):
    project = tmp_path / "project"
    initialize(project)
    docs = load_data(ROOT / "templates/v02_stage0.yaml")
    expected_version = 0
    if problem == "reference":
        (project / docs["reference_board"]["references"][0]["path"]).write_text("tampered")
    elif problem == "identity":
        docs["scene_spec"]["project_id"] = "another_project"
    else:
        expected_version = 1
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps(docs))
    before = snapshot(project)
    code, output = cli("stage0-submit", project, "--proposal", proposal, "--expected-version", expected_version)
    assert code == 2 and message in output["error"].lower(), output
    assert snapshot(project) == before
    assert not (project / "stage0").exists()


@pytest.mark.parametrize("args", [("run",), ("approve-plan",), ("stage1", "--asset-id", "bench"),
                                  ("stage2",), ("deliver",)])
def test_compatibility_commands_reject_new_visual_project(tmp_path, args):
    project = tmp_path / "project"
    initialize(project)
    before = snapshot(project)
    code, output = cli(args[0], project, *args[1:])
    assert code == 2 and "unavailable for schema 0.2" in output["error"]
    assert before == snapshot(project)


def test_documented_migration_preserves_real_legacy_files_and_deep_copies(approved, tmp_path):
    from runtime.delivery_executor import DeliveryExecutor
    approved.set_delivery_target("asset")
    DeliveryExecutor(approved).run()
    original = approved.read()
    saved = copy.deepcopy(original)
    before = snapshot(approved.root)
    workspace_before = snapshot(tmp_path)
    sequence = commands("v02-migration")
    assert len(sequence) == 1 and sequence[0][3] == "migrate-v02"
    code, report = run(sequence[0], {"LEGACY_PROJECT": approved.root})
    assert code == 0, report
    assert report == plan_migration(original)
    assert report["status"] == "migration_required_input" and report["source_modified"] is False
    assert set(report["required_inputs"]) == set(KINDS)
    candidate = report["candidate_manifest"]
    assert candidate["legacy_manifest"] == original
    assert candidate["assets"] == original["assets"] and candidate["supplied_assets"] == original["supplied_assets"]
    assert candidate["state"] == "initialized" and candidate["mode"] == "plan_only"
    assert candidate["approvals"] == [] and candidate["auto_approve"] is False
    direct = plan_migration(original)["candidate_manifest"]
    direct["assets"]["bench"]["result"]["source"]["creator"] = "changed candidate"
    direct["legacy_manifest"]["user_brief"]["raw"] = "changed legacy copy"
    direct["user_brief"]["raw"] = "changed brief"
    assert original == saved and snapshot(approved.root) == before
    assert snapshot(tmp_path) == workspace_before
