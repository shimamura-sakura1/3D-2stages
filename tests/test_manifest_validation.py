import copy

import pytest

from conftest import review
from runtime.errors import BoundaryError, ValidationError
from runtime.io import atomic_write, inside, load_data
from runtime.manifest_manager import ManifestManager
from runtime.validators import validate_manifest


def test_worker_cannot_write_manifest(project):
    before = project.path.read_bytes()
    with pytest.raises(BoundaryError, match="Workers"):
        ManifestManager(project.root, role="worker").approve_plan()
    assert project.path.read_bytes() == before


def test_invalid_schema_rejected(project):
    manifest = project.read()
    manifest["mode"] = "anything"
    with pytest.raises(ValidationError):
        validate_manifest(manifest)


def test_asset_key_mismatch_rejected(project):
    manifest = project.read()
    manifest["assets"]["bench"]["asset_id"] = "other"
    with pytest.raises(ValidationError):
        validate_manifest(manifest)


def test_invalid_transition_is_atomic(project):
    before = project.path.read_bytes()
    with pytest.raises(BoundaryError):
        project.transition("bench", "generating")
    assert project.path.read_bytes() == before


def test_approval_must_use_review_entrypoint(acquired):
    with pytest.raises(BoundaryError):
        acquired.transition("bench", "approved")


def test_unrequested_auto_approval_blocked(acquired):
    with pytest.raises(BoundaryError, match="Automatic"):
        review(acquired, reviewer="automatic")


def test_stale_review_rejected(acquired):
    with pytest.raises(BoundaryError, match="old revision"):
        acquired.review({"asset_id": "bench", "revision": 99, "decision": "approved",
                         "issues": [], "instruction": "", "reviewer": "user"})


def test_checksum_change_prevents_approval(acquired):
    task = acquired.read()["assets"]["bench"]
    with inside(acquired.root, task["result"]["files"]["model"]).open("a") as stream:
        stream.write("\n# changed\n")
    with pytest.raises(ValidationError, match="checksum"):
        review(acquired)


@pytest.mark.parametrize("path", ["../outside.glb", "D:/outside.glb", "/outside.glb", "stage1/../../outside.glb"])
def test_project_path_boundary(project, path):
    with pytest.raises(BoundaryError):
        inside(project.root, path)


def test_stale_manifest_version_rejected(project):
    with pytest.raises(BoundaryError, match="Stale project"):
        project.record_stage2("stage2/blender_plan.yaml", [], "digest", expected_version=-1)


def test_exclusive_manifest_lock(project):
    (project.root / ".manifest.lock").write_text("busy")
    with pytest.raises(BoundaryError, match="busy"):
        project.approve_plan()


def test_result_cannot_escape_assigned_asset(acquired):
    from runtime.validators import validate_result
    result = copy.deepcopy(acquired.read()["assets"]["bench"]["result"])
    result["files"]["model"] = "stage1/outputs/other/rev00/asset.obj"
    with pytest.raises(BoundaryError, match="revision output"):
        validate_result(acquired.root, result)
