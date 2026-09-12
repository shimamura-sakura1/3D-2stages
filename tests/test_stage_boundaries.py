import pytest

from conftest import REPO, review
from runtime.errors import BoundaryError, ValidationError
from runtime.io import atomic_write, load_data
from runtime.planning import create_project
from runtime.manifest_manager import ManifestManager
from runtime.stage1_executor import Stage1Executor
from runtime.stage2_executor import Stage2Executor


def test_unapproved_asset_blocks_stage2(acquired):
    with pytest.raises(BoundaryError, match="not approved"):
        Stage2Executor(acquired).run(dry_run=True)


def test_approved_assets_allow_stage2(approved):
    assert Stage2Executor(approved).run(dry_run=True)["status"] == "preflight_passed"
    assert approved.read()["stage2"]["status"] == "not_started"
    assert not list((approved.root / "stage2/scene").iterdir())


def test_stage2_only_supplied_assets(tmp_path, candidate):
    create_project(tmp_path, "supplied", "Use my bench", "stage2_only")
    manager = ManifestManager(tmp_path)
    manager.supply_asset("bench", REPO / "examples/library/bench.obj", candidate["source"])
    manager.approve_plan()
    atomic_write(tmp_path / "stage2/blender_plan.yaml", load_data(REPO / "templates/blender_plan.yaml"))
    assert Stage2Executor(manager).run(dry_run=True)["status"] == "preflight_passed"
    with pytest.raises(BoundaryError):
        Stage1Executor(manager, {}).run("bench")


def test_plan_only_blocks_both_stages(project, provider):
    project.configure(mode="plan_only")
    with pytest.raises(BoundaryError):
        Stage1Executor(project, {provider.name: provider}).run("bench")
    with pytest.raises(BoundaryError):
        Stage2Executor(project).run(dry_run=True)


def test_stage1_only_blocks_stage2(approved):
    approved.configure(mode="stage1_only")
    with pytest.raises(BoundaryError):
        Stage2Executor(approved).run(dry_run=True)


def test_omitted_required_asset_blocks_stage2(approved):
    path = approved.root / "stage2/blender_plan.yaml"
    plan = load_data(path)
    plan["assets"] = []
    atomic_write(path, plan)
    with pytest.raises(BoundaryError, match="omits"):
        Stage2Executor(approved).run(dry_run=True)
    approved.configure(allow_partial=True)
    assert Stage2Executor(approved).run(dry_run=True)["status"] == "preflight_passed"


def test_partial_does_not_allow_listed_unapproved_asset(acquired):
    acquired.configure(allow_partial=True)
    with pytest.raises(BoundaryError, match="not approved"):
        Stage2Executor(acquired).run(dry_run=True)


def test_missing_blender_does_not_mark_build_complete(approved):
    with pytest.raises(BoundaryError, match="not found"):
        Stage2Executor(approved, "definitely-no-blender-executable", backend="batch").run()
    assert approved.read()["stage2"]["status"] == "not_started"


def test_stage1_requires_plan_approval(tmp_path, task, provider):
    create_project(tmp_path, "test", "bench", "full_pipeline", [task])
    with pytest.raises(BoundaryError, match="Approve"):
        Stage1Executor(ManifestManager(tmp_path), {provider.name: provider}).run("bench")


def test_missing_provider_marks_failure_without_generation(project):
    with pytest.raises(BoundaryError, match="incomplete"):
        Stage1Executor(project, {}).run("bench")
    assert project.read()["assets"]["bench"]["status"] == "failed"
