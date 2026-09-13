"""S3 regression evidence: scoped continuation, asset delivery, and init binding."""
import contextlib
import io
import json

import pytest
from jsonschema import Draft202012Validator

from conftest import REPO, review
from runtime.cli import main
from runtime.io import inside
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, new_task
from runtime.stage1_executor import Stage1Executor
from runtime.validators import validate_manifest


def call(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([str(arg) for arg in args])
    return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()


def setup_pair(tmp_path, provider):
    create_project(tmp_path, "scoped_repair", "Two benches", "repair",
                   [new_task("bench"), new_task("other", "bench")])
    manager = ManifestManager(tmp_path)
    manager.approve_plan()
    Stage1Executor(manager, {provider.name: provider}).run("bench")
    review(manager, "revision_requested", "Acquire a fresh source copy")
    return manager


def binding():
    interface = json.loads((REPO / "interface.json").read_text(encoding="utf-8"))
    runtime = next(a for a in interface["artifacts"] if a["id"] == "workflow-cli")["runtime_binding"]
    schema = json.loads((REPO / runtime["input"]["schema"]).read_text(encoding="utf-8"))
    return runtime, Draft202012Validator(schema)


@pytest.mark.parametrize("auto_approve", [False, True])
def test_positive_selected_rework_preserves_other_tasks_and_old_output(tmp_path, provider, auto_approve):
    manager = setup_pair(tmp_path, provider)
    manager.configure(auto_approve=auto_approve)
    before = manager.read()
    original = inside(tmp_path, "stage1/outputs/bench/rev00/asset.obj").read_bytes()
    code, result, error = call("run", tmp_path, "--asset-id", "bench", "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 0, error
    after = manager.read()
    assert after["assets"]["bench"]["revision"] == 1
    assert after["assets"]["bench"]["status"] == ("approved" if auto_approve else "review_required")
    assert after["assets"]["other"] == before["assets"]["other"]
    assert inside(tmp_path, "stage1/outputs/bench/rev00/asset.obj").read_bytes() == original
    assert inside(tmp_path, after["assets"]["bench"]["result"]["files"]["model"]).is_file()
    assert result["status"] == "stage1_checkpoint"
    assert after["stage2"]["status"] == "not_started"


def test_positive_unscoped_run_resumes_requested_revision(acquired):
    review(acquired, "revision_requested", "Acquire a fresh source copy")
    code, result, error = call("run", acquired.root, "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 0, error
    assert acquired.read()["assets"]["bench"]["revision"] == 1
    assert acquired.read()["assets"]["bench"]["status"] == "review_required"
    assert result["status"] == "stage1_checkpoint"


def test_positive_explicit_failed_retry(acquired):
    review(acquired, "failed")
    code, result, error = call("run", acquired.root, "--asset-id", "bench", "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 0, error
    assert acquired.read()["assets"]["bench"]["revision"] == 1
    assert result["status"] == "stage1_checkpoint"


def test_positive_router_asset_delivery_bypasses_blender(approved):
    # This asserts an explicit Router edge, then executes the corresponding real I/O.
    router = (REPO / "SKILL.md").read_text(encoding="utf-8").split("## Execution Router", 1)[1]
    step4 = router.split("### Step 4 ", 1)[1].split("### Step 5 ", 1)[0]
    edges = step4.split("\nNext:\n", 1)[1].strip().splitlines()
    assert "- Step 6" in edges
    approved.configure(mode="stage1_only")
    assert call("configure", approved.root, "--target", "asset")[0] == 0
    code, report, error = call("deliver", approved.root)
    assert code == 0, error
    assert report["target"] == "asset"
    assert inside(approved.root, report["files"][0]).is_file()
    assert report["attribution"][0]["asset_id"] == "demo_bench"
    assert approved.read()["stage2"]["status"] == "not_started"


def test_positive_init_binding_checks_real_manifest(tmp_path):
    runtime, validator = binding()
    args = ["init", str(tmp_path / "new"), "--id", "init_scope", "--brief", "A bench"]
    validator.validate(args)
    code, output, error = call(*args)
    assert code == 0, error
    assert runtime["outputs"][0]["schema"] == "contracts/project_manifest.schema.json"
    validate_manifest(output)
    assert output["mode"] == "plan_only"


def test_default_plan_only_does_not_resume_or_load_providers(project):
    project.configure(mode="plan_only")
    before = project.path.read_bytes()
    code, output, error = call("run", project.root, "--asset-id", "bench", "--catalog", "missing.yaml")
    assert code == 0, error
    assert output["status"] == "plan_only"
    assert project.path.read_bytes() == before


def test_default_unscoped_run_acquires_all_planned_assets(tmp_path):
    create_project(tmp_path, "default_flow", "Two benches", "stage1_only",
                   [new_task("bench"), new_task("other", "bench")])
    manager = ManifestManager(tmp_path)
    manager.approve_plan()
    code, output, error = call("run", tmp_path, "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 0, error
    assert output["status"] == "stage1_checkpoint"
    assert all(t["status"] == "review_required" for t in manager.read()["assets"].values())


def test_default_failed_asset_is_not_automatically_retried(acquired):
    review(acquired, "failed")
    before = acquired.path.read_bytes()
    code, output, error = call("run", acquired.root, "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 0, error
    assert output["pending_assets"] == ["bench"]
    assert acquired.path.read_bytes() == before


def test_default_scene_preflight_still_requires_approved_inputs(approved):
    code, output, error = call("stage2", approved.root, "--dry-run")
    assert code == 0, error
    assert output["status"] == "preflight_passed"
    assert approved.read()["stage2"]["status"] == "not_started"


def test_rejection_unknown_selector_precedes_provider_loading(project):
    before = project.path.read_bytes()
    code, output, error = call("run", project.root, "--asset-id", "missing", "--catalog", "missing.yaml")
    assert code == 2
    assert "Unknown asset ID" in json.loads(error)["error"]
    assert output is None
    assert project.path.read_bytes() == before


def test_rejection_selector_in_stage2_only(project):
    project.configure(mode="stage2_only")
    before = project.path.read_bytes()
    code, output, error = call("run", project.root, "--asset-id", "bench")
    assert code == 2
    assert "Stage 1 prohibited" in json.loads(error)["error"]
    assert output is None
    assert project.path.read_bytes() == before


def test_rejection_revision_limit_is_preserved(approved, provider):
    for _ in range(3):
        review(approved, "revision_requested", "Acquire a fresh source copy")
        Stage1Executor(approved, {provider.name: provider}).run("bench")
        review(approved)
    review(approved, "revision_requested", "One more")
    before = approved.path.read_bytes()
    code, output, error = call("run", approved.root, "--asset-id", "bench", "--catalog", REPO / "examples/library/catalog.yaml")
    assert code == 2
    assert "Revision limit" in json.loads(error)["error"]
    assert output is None
    assert approved.path.read_bytes() == before


def test_rejection_asset_delivery_requires_review(acquired):
    acquired.configure(mode="stage1_only")
    call("configure", acquired.root, "--target", "asset")
    before = acquired.path.read_bytes()
    code, output, error = call("deliver", acquired.root)
    assert code == 2
    assert "must be approved" in json.loads(error)["error"]
    assert output is None
    assert acquired.path.read_bytes() == before
    assert not list((acquired.root / "delivery/outputs").iterdir())


@pytest.mark.parametrize("command", ["run", "status", "stage1", "stage2", "deliver", "approve-final"])
def test_rejection_init_binding_excludes_other_subcommands(command):
    _, validator = binding()
    assert not validator.is_valid([command, "project"])


def test_rejection_empty_init_arguments():
    _, validator = binding()
    assert not validator.is_valid([])
