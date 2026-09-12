from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from runtime.blender_mcp import McpBlenderExecutor
from runtime.cli import main
from runtime.errors import BoundaryError
from runtime.stage2_executor import Stage2Executor


def test_mcp_is_default_and_preparation_is_not_execution(approved, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("MCP preparation must not launch a local Blender process")
    monkeypatch.setattr("runtime.stage2_executor.shutil.which", unexpected)
    packet = Stage2Executor(approved).run()
    assert packet["status"] == "mcp_execution_required"
    assert approved.read()["stage2"]["status"] == "not_started"
    assert not list((approved.root / "stage2/scene").rglob("*.blend"))
    for step in packet["steps"]:
        compile(step["code"], step["name"], "exec")
    compile(packet["status_code"], "status", "exec")


def test_mcp_rejects_unapproved_inputs_before_preparing(acquired):
    with pytest.raises(BoundaryError, match="not approved"):
        McpBlenderExecutor(acquired).prepare()
    assert not list((acquired.root / "stage2/scene").iterdir())


def test_mcp_complete_requires_real_files(approved):
    executor = McpBlenderExecutor(approved)
    packet = executor.prepare()
    with pytest.raises(BoundaryError, match="incomplete"):
        executor.complete(packet["build_id"])
    assert approved.read()["stage2"]["status"] == "not_started"


def test_mcp_complete_records_build_without_autoapproval(approved, glb_bytes):
    executor = McpBlenderExecutor(approved)
    packet = executor.prepare()
    directory = approved.root / "stage2/scene" / packet["build_id"]
    # Format-identifiable test doubles; this does not exercise Blender rendering.
    (directory / "scene.blend").write_bytes(b"BLENDER-v402fixture")
    (directory / "scene.glb").write_bytes(glb_bytes)
    (directory / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    result = executor.complete(packet["build_id"])
    assert result["stage2"]["status"] == "built"
    assert result["state"] == "review_required"
    with pytest.raises(BoundaryError, match="stale"):
        executor.complete(packet["build_id"])


def test_mcp_complete_rejects_changed_manifest(approved):
    executor = McpBlenderExecutor(approved)
    packet = executor.prepare()
    approved.configure(allow_partial=True)
    with pytest.raises(BoundaryError, match="stale"):
        executor.complete(packet["build_id"])


def test_mcp_complete_rejects_changed_style(approved):
    executor = McpBlenderExecutor(approved)
    packet = executor.prepare()
    with (approved.root / "style_bible.yaml").open("a") as stream:
        stream.write("\n# changed\n")
    with pytest.raises(BoundaryError, match="inputs changed"):
        executor.complete(packet["build_id"])


@pytest.mark.parametrize("build_id", ["../outside", "batch-123", "mcp-xyz"])
def test_mcp_job_path_boundary(approved, build_id):
    with pytest.raises(BoundaryError, match="build ID"):
        McpBlenderExecutor(approved).complete(build_id)


def test_emitted_mcp_steps_guard_inputs_and_preserve_execution_order(approved, monkeypatch):
    calls = []
    timers = []
    fake_bpy = SimpleNamespace(app=SimpleNamespace(driver_namespace={},
                               timers=SimpleNamespace(register=lambda callback, **kw: timers.append(callback))))
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    fake_module = {"build": lambda request, export: calls.append("build") or "new_scene",
                   "export_scene": lambda request, scene: calls.append("export"),
                   "render_scene": lambda request, scene: calls.append("render")}
    monkeypatch.setattr("runpy.run_path", lambda path: fake_module)
    packet = McpBlenderExecutor(approved).prepare()
    namespace = {}
    for step in packet["steps"]:
        exec(step["code"], namespace)
    assert calls == ["build", "export"]
    assert len(timers) == 1
    timers[0]()
    assert calls == ["build", "export", "render"]
    job = next(iter(fake_bpy.app.driver_namespace.values()))
    assert job["state"] == "complete"
    with pytest.raises(AssertionError):
        exec(packet["steps"][1]["code"], namespace)


def test_mcp_load_stops_after_asset_approval_revoked(approved, monkeypatch):
    from conftest import review
    monkeypatch.setitem(sys.modules, "bpy", SimpleNamespace(app=SimpleNamespace(driver_namespace={})))
    packet = McpBlenderExecutor(approved).prepare()
    review(approved, "revision_requested", "Change proportions")
    with pytest.raises(AssertionError, match="Build input changed"):
        exec(packet["steps"][0]["code"], {})


def test_cli_defaults_to_mcp(approved, capsys):
    assert main(["stage2", str(approved.root)]) == 0
    assert '"backend": "codex_mcp"' in capsys.readouterr().out
