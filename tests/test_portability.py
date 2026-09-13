"""Portable behavior is exercised with OS layouts, not an actual Windows host."""
import json
import runpy
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.cli import main
from runtime.errors import BoundaryError
from runtime.io import inside

ROOT = Path(__file__).resolve().parents[1]


def test_positive_windows_separators_work_in_public_preflight(approved, capsys):
    assert main(["stage2", str(approved.root), "--plan", r"stage2\blender_plan.yaml", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preflight_passed"


@pytest.mark.parametrize("path", [r"D:\outside.glb", "D:/outside.glb", "D:outside.glb",
                                  r"\\server\share\asset.glb", r"\outside.glb",
                                  r"stage1\..\outside.glb", r"stage1/..\outside.glb",
                                  "/outside.glb", "../outside.glb"])
def test_rejection_foreign_paths_at_public_cli(approved, capsys, path):
    assert main(["stage2", str(approved.root), "--plan", path, "--dry-run"]) == 2
    assert "project-relative path" in json.loads(capsys.readouterr().err)["error"]


def test_default_posix_paths_and_mode_are_unchanged(approved, capsys):
    before = approved.path.read_bytes()
    assert main(["stage2", str(approved.root), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preflight_passed"
    assert approved.path.read_bytes() == before
    assert inside(approved.root, "stage1/outputs") == approved.root / "stage1/outputs"


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture executable")
    path.chmod(0o755)
    return str(path)


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_positive_blender_standard_install_discovery(tmp_path, monkeypatch, platform):
    from runtime.platform_support import find_blender
    monkeypatch.setattr("shutil.which", lambda name: None)
    if platform == "darwin":
        expected = executable(tmp_path / "Applications/Blender.app/Contents/MacOS/Blender")
        env = {}
    else:
        base = tmp_path / "Program Files"
        executable(base / "Blender Foundation/Blender 4.9/blender.exe")
        expected = executable(base / "Blender Foundation/Blender 4.10/blender.exe")
        env = {"ProgramFiles": str(base)}
    assert find_blender(platform=platform, environ=env, home=tmp_path,
                        applications=tmp_path / "Applications") == expected


def test_positive_explicit_blender_overrides_environment(tmp_path, monkeypatch):
    from runtime.platform_support import find_blender
    explicit = executable(tmp_path / "explicit Blender")
    configured = executable(tmp_path / "configured Blender")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert find_blender(explicit, environ={"BLENDER_EXECUTABLE": configured}) == explicit
    assert find_blender(environ={"BLENDER_EXECUTABLE": configured}) == configured


def test_default_blender_path_and_mcp_are_preserved(approved, monkeypatch):
    from runtime.platform_support import find_blender
    from runtime.stage2_executor import Stage2Executor
    monkeypatch.setattr("shutil.which", lambda name: "/path/from/PATH/blender")
    assert find_blender(environ={}) == "/path/from/PATH/blender"
    monkeypatch.setattr("runtime.stage2_executor.find_blender", lambda *a, **k: pytest.fail("MCP must not discover batch Blender"))
    packet = Stage2Executor(approved).run()
    assert packet["status"] == "mcp_execution_required"
    assert approved.read()["stage2"]["status"] == "not_started"


def test_rejection_invalid_explicit_blender_does_not_fallback(tmp_path, monkeypatch):
    from runtime.platform_support import find_blender
    monkeypatch.setattr("shutil.which", lambda name: None)
    installed = executable(tmp_path / "Applications/Blender.app/Contents/MacOS/Blender")
    for explicit, env in [(str(tmp_path / "missing"), {}),
                          (None, {"BLENDER_EXECUTABLE": str(tmp_path / "missing")})]:
        with pytest.raises(BoundaryError, match="Configured Blender"):
            find_blender(explicit, environ=env, platform="darwin", home=tmp_path,
                         applications=tmp_path / "Applications")
    assert Path(installed).is_file()


def test_positive_doctor_reports_current_environment_without_services(monkeypatch, capsys):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Doctor must not start processes"))
    assert main(["doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["python"]["executable"] == sys.executable
    assert report["platform"] == sys.platform
    assert report["blender"]["minimum_version"] == [4, 2, 0]
    assert report["blender"]["version_verified"] is False
    assert report["mcp"]["status"] == "requires_session_check"


def test_rejection_old_blender_before_any_scene_mutation(monkeypatch):
    fake = SimpleNamespace(app=SimpleNamespace(version=(4, 1, 9)))
    monkeypatch.setitem(sys.modules, "bpy", fake)
    monkeypatch.setitem(sys.modules, "mathutils", SimpleNamespace(Vector=object))
    worker = runpy.run_path(str(ROOT / "runtime/blender_worker.py"))
    with pytest.raises(RuntimeError, match="Blender 4.2"):
        worker["build"]({})


def test_positive_supported_blender_passes_version_gate(monkeypatch):
    fake = SimpleNamespace(app=SimpleNamespace(version=(4, 5, 13)))
    monkeypatch.setitem(sys.modules, "bpy", fake)
    monkeypatch.setitem(sys.modules, "mathutils", SimpleNamespace(Vector=object))
    worker = runpy.run_path(str(ROOT / "runtime/blender_worker.py"))
    worker["check_blender_version"]()


def test_positive_framework_resolution_and_memory_projection(tmp_path, monkeypatch):
    from runtime.platform_support import find_framework
    repo = tmp_path / "project"
    sibling = tmp_path / "contract-govern-skil"
    override = tmp_path / "custom-framework"
    for path in (sibling, override):
        (path / "skillctl").mkdir(parents=True)
        (path / "skillctl/__main__.py").write_text("")
        (path / "spec").mkdir()
        (path / "spec/SPEC.md").write_text("fixture")
    assert find_framework(repo, environ={}) == sibling
    assert find_framework(repo, environ={"CONTRACT_GOVERN_HOME": str(override)}) == override
    assert find_framework(repo, str(sibling), environ={"CONTRACT_GOVERN_HOME": str(override)}) == sibling
    repo.mkdir()
    (repo / "AGENTS.md").write_text("Project maintenance instructions")
    govern = runpy.run_path(str(ROOT / "scripts/govern.py"))
    assert "AGENTS.md" in govern["snapshot"](repo)


def test_rejection_missing_framework_is_explicit(tmp_path):
    from runtime.platform_support import find_framework
    with pytest.raises(BoundaryError, match="CONTRACT_GOVERN_HOME"):
        find_framework(tmp_path, environ={})


def test_positive_documented_doctor_example(capsys):
    guide = (ROOT / "docs/platforms.md").read_text()
    examples = json.loads(guide.split("```json\n", 1)[1].split("```", 1)[0])
    for example in examples:
        assert main(example["argv"]) == example["exit"]
        value = json.loads(capsys.readouterr().out)
        for component in example["field"].split("."):
            value = value[component]
        assert value == example["equals"]


def test_positive_governance_uses_current_python_and_preserves_memory(tmp_path):
    framework = tmp_path / "contract-govern-skil"
    (framework / "skillctl").mkdir(parents=True)
    (framework / "skillctl/__init__.py").write_text("")
    (framework / "skillctl/__main__.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "print(json.dumps({'status': 'pass', 'python': sys.executable, "
        "'memory_in_projection': (Path(sys.argv[2]) / 'AGENTS.md').is_file()}))\n")
    (framework / "spec").mkdir()
    (framework / "spec/SPEC.md").write_text("Fixture for launcher argument behavior only")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/govern.py"), "validate"],
                            cwd=ROOT, env=dict(os.environ, CONTRACT_GOVERN_HOME=str(framework)),
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["python"] == sys.executable
    assert report["memory_in_projection"] is True
