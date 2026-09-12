import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, review
from providers.local_library import LocalLibraryProvider
from runtime.cli import main
from runtime.delivery_executor import DeliveryExecutor
from runtime.errors import BoundaryError, WorkflowError
from runtime.hy3d_client import Hy3DClient
from runtime.io import atomic_write, inside, load_data, sha256
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, new_task
from runtime.stage1_executor import Stage1Executor
from runtime.stage2_executor import Stage2Executor
from runtime.validators import validate_model


def test_library_direct_to_review_preserves_original(acquired):
    task = acquired.read()["assets"]["bench"]
    assert task["status"] == "review_required"
    assert task["result"]["route"] == "library_direct"
    assert (acquired.root / "stage1/sources/bench/rev00/original.obj").is_file()
    assert task["result"]["sha256"] == sha256(REPO / "examples/library/bench.obj")


def test_repair_only_changes_selected_asset(tmp_path, provider):
    create_project(tmp_path, "repair", "Two benches", "full_pipeline", [new_task("bench"), new_task("bench2", "bench")])
    manager = ManifestManager(tmp_path)
    manager.approve_plan()
    executor = Stage1Executor(manager, {provider.name: provider})
    executor.run("bench")
    executor.run("bench2")
    review(manager)
    review(manager, asset_id="bench2")
    other_before = copy.deepcopy(manager.read()["assets"]["bench2"])
    original = (tmp_path / "stage1/outputs/bench/rev00/asset.obj").read_bytes()
    manager.configure(mode="repair")
    review(manager, "revision_requested", "Acquire a clean copy of the source")
    executor.run("bench")
    assert manager.read()["assets"]["bench"]["revision"] == 1
    assert manager.read()["assets"]["bench2"] == other_before
    assert (tmp_path / "stage1/outputs/bench/rev00/asset.obj").read_bytes() == original
    assert (tmp_path / "stage1/outputs/bench/rev01/asset.obj").is_file()


def test_revision_limit_does_not_reset(approved, provider):
    executor = Stage1Executor(approved, {provider.name: provider})
    for _ in range(3):
        review(approved, "revision_requested", "New source copy")
        executor.run("bench")
        review(approved)
    review(approved, "revision_requested", "One more")
    with pytest.raises(BoundaryError, match="Revision limit"):
        executor.run("bench")


def test_route_b_keeps_original_and_derivative(tmp_path, candidate, glb_bytes):
    candidate["scores"]["style_fit"] = 0.2
    library = tmp_path / "library"
    library.mkdir()
    (library / "bench.obj").write_bytes((REPO / "examples/library/bench.obj").read_bytes())
    atomic_write(library / "catalog.yaml", {"assets": [candidate]})
    provider = LocalLibraryProvider(library / "catalog.yaml")
    calls = []
    def transport(method, path, body):
        calls.append((path, body))
        return ({"status": "ok", "capabilities": ["retexture_mesh"]} if path == "/health"
                else {"model_base64": base64.b64encode(glb_bytes).decode()})
    hy3d = Hy3DClient({"type": "local", "endpoint": "http://localhost:8080"}, transport)
    root = tmp_path / "project"
    create_project(root, "refine", "bench", "stage1_only", [new_task("bench")])
    manager = ManifestManager(root)
    manager.approve_plan()
    result = Stage1Executor(manager, {provider.name: provider}, hy3d).run("bench")
    assert result["route"] == "library_hy3d_refine"
    assert calls[-1][1]["mesh"]["name"] == "original.obj"
    assert (root / "stage1/sources/bench/rev00/original.obj").read_bytes() == (library / "bench.obj").read_bytes()
    assert inside(root, result["files"]["model"]).read_bytes() == glb_bytes


def test_route_c_after_empty_search(project, tmp_path, candidate, glb_bytes):
    catalog = tmp_path / "empty.yaml"
    atomic_write(catalog, {"assets": []})
    source = {**candidate["source"], "provider": "hy3d", "asset_id": "test-generation"}
    client = Hy3DClient({"type": "local", "endpoint": "http://localhost:8080", "output_source": source},
                        lambda method, path, body: {"status": "ok", "capabilities": ["generate_textured_asset"]}
                        if path == "/health" else {"model_base64": base64.b64encode(glb_bytes).decode()})
    result = Stage1Executor(project, {"local_library": LocalLibraryProvider(catalog)}, client).run("bench")
    assert result["route"] == "hy3d_generate"
    assert result["recipe"]["searched_providers"] == ["local_library"]
    assert project.read()["assets"]["bench"]["status"] == "review_required"


def test_explicit_autoapproval(project, provider):
    project.configure(auto_approve=True)
    Stage1Executor(project, {provider.name: provider}).run("bench")
    assert project.read()["assets"]["bench"]["status"] == "approved"


def test_asset_delivery_carries_provenance(approved):
    approved.set_delivery_target("asset")
    report = DeliveryExecutor(approved).run()
    assert inside(approved.root, report["files"][0]).is_file()
    assert report["attribution"][0]["asset_id"] == "demo_bench"
    assert approved.read()["state"] == "complete"


def test_scene_delivery_needs_final_approval(approved):
    with pytest.raises(BoundaryError, match="final user approval"):
        DeliveryExecutor(approved).run()


def fake_blender(glb_bytes, success=True):
    def run(command, **kwargs):
        if not success:
            return SimpleNamespace(returncode=1)
        request = load_data(command[-1])
        output = Path(request["output_dir"])
        (output / "scene.glb").write_bytes(glb_bytes)
        (output / "scene.blend").write_bytes(b"test-double-blend")
        (output / "preview.png").write_bytes(b"test-double-preview")
        return SimpleNamespace(returncode=0)
    return run


def test_scene_build_review_delivery_and_stale_inputs(approved, glb_bytes, monkeypatch):
    monkeypatch.setattr("runtime.stage2_executor.shutil.which", lambda _: "blender")
    Stage2Executor(approved, runner=fake_blender(glb_bytes), backend="batch").run()
    approved.approve_final()
    report = DeliveryExecutor(approved).run()
    assert len(report["files"]) == 3
    with (approved.root / "style_bible.yaml").open("a") as stream:
        stream.write("\n# changed\n")
    with pytest.raises(BoundaryError, match="inputs changed"):
        DeliveryExecutor(approved).run()


def test_blender_failure_does_not_record_success(approved, glb_bytes, monkeypatch):
    monkeypatch.setattr("runtime.stage2_executor.shutil.which", lambda _: "blender")
    with pytest.raises(WorkflowError, match="Blender failed"):
        Stage2Executor(approved, runner=fake_blender(glb_bytes, success=False), backend="batch").run()
    assert approved.read()["stage2"]["status"] == "not_started"


def test_cli_plan_only_is_side_effect_free_after_init(tmp_path, capsys):
    assert main(["init", str(tmp_path), "--id", "cli", "--brief", "A station", "--asset", "bench"]) == 0
    before = (tmp_path / "manifest.yaml").read_bytes()
    assert main(["run", str(tmp_path), "--catalog", "missing-catalog.yaml"]) == 0
    assert (tmp_path / "manifest.yaml").read_bytes() == before
    assert not list((tmp_path / "stage1/outputs").iterdir())


def test_model_validation(glb_bytes, tmp_path):
    path = tmp_path / "triangle.glb"
    path.write_bytes(glb_bytes)
    assert validate_model(path) == path
    path.write_bytes(glb_bytes[:-8])
    with pytest.raises(WorkflowError):
        validate_model(path)
