import runpy
from pathlib import Path

import pytest


TOOLS = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/govern.py"))


def test_source_projection_excludes_assets_and_dependency_caches(tmp_path):
    for relative in ("SKILL.md", "runtime/cli.py", "tests/test_example.py", "projects/private/asset.glb",
                     ".deps/library.py", ".skillctl/report.json", "runtime/__pycache__/compiled.pyc"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    assert set(TOOLS["snapshot"](tmp_path)) == {"SKILL.md", "runtime/cli.py", "tests/test_example.py"}


def test_source_hash_changes_when_implementation_changes(tmp_path):
    (tmp_path / "runtime").mkdir()
    path = tmp_path / "runtime/cli.py"
    path.write_text("old")
    before = TOOLS["snapshot"](tmp_path)
    path.write_text("new")
    assert before != TOOLS["snapshot"](tmp_path)


def test_history_hash_detects_changed_accepted_record(tmp_path):
    (tmp_path / "changes").mkdir()
    path = tmp_path / "changes/change-001.json"
    path.write_text('{"version":"S0"}')
    before = TOOLS["history_snapshot"](tmp_path)
    path.write_text('{"version":"forged"}')
    assert before != TOOLS["history_snapshot"](tmp_path)


def test_unknown_contract_returns_workflow_error():
    from runtime.errors import ValidationError
    from runtime.validators import validate_contract
    with pytest.raises(ValidationError, match="Unknown contract"):
        validate_contract("not_registered", {})
