"""Exercise the shipped Stage 0 reference across Git newline checkout modes."""

import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
import subprocess
from pathlib import Path

from runtime import cli as workflow_cli
from runtime.io import load_data


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path("examples/v02/reference.svg")
TEMPLATE = ROOT / "templates/v02_stage0.yaml"


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *map(str, args)], cwd=cwd)


def checkout(tmp_path, autocrlf):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    reference = source / REFERENCE
    reference.parent.mkdir(parents=True)
    source_bytes = (ROOT / REFERENCE).read_bytes()
    if (ROOT / ".git").exists():
        assert source_bytes == git("show", f"HEAD:{REFERENCE.as_posix()}")
    reference.write_bytes(source_bytes)
    git("init", "-q", "-b", "main", cwd=source)
    git("-c", "core.autocrlf=false", "add", ".gitattributes", REFERENCE, cwd=source)
    git("-c", "user.name=Checkout Test", "-c", "user.email=checkout@example.invalid",
        "commit", "-qm", "fixture", cwd=source)
    target = tmp_path / "checkout"
    git("-c", f"core.autocrlf={'true' if autocrlf else 'false'}", "clone", "-q",
        source, target, cwd=tmp_path)
    return target / REFERENCE


def expected_reference():
    document = load_data(TEMPLATE)
    return document["reference_board"]["references"][0]["path"]


def cli(*args):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = workflow_cli.main([*map(str, args)])
    return code, json.loads(stdout.getvalue() if code == 0 else stderr.getvalue())


def initialize(tmp_path, reference):
    project = tmp_path / "project"
    code, result = cli("init-v02", project, "--id", "v02_demo", "--brief",
                       "Quiet industrial station with matte teal equipment and warm concrete")
    assert code == 0, result
    code, result = cli("reference-add-v02", project, reference, "--id", "ref_material",
                       "--role", "material_language", "--source",
                       ROOT / "examples/v02/reference_source.yaml")
    assert code == 0, result
    return project


def assert_public_stage0(tmp_path, autocrlf):
    reference = checkout(tmp_path, autocrlf)
    expected = expected_reference()
    assert reference.is_file()
    assert "ref_material-" + hashlib.sha256(reference.read_bytes()).hexdigest() + ".svg" == Path(expected).name
    project = initialize(tmp_path, reference)
    code, result = cli("stage0-submit", project, "--proposal", TEMPLATE,
                       "--expected-version", "0")
    assert code == 0, result
    code, state = cli("status", project)
    assert code == 0, state
    assert (state["schema_version"], state["state"], state["mode"]) == (
        "0.2", "visual_review_required", "plan_only")
    assert state["approvals"] == [] and state["assets"] == {}
    assert (project / expected).read_bytes() == reference.read_bytes()


def test_windows_autocrlf_checkout_runs_public_stage0(tmp_path):
    assert_public_stage0(tmp_path, autocrlf=True)


def test_macos_default_checkout_runs_public_stage0(tmp_path):
    assert_public_stage0(tmp_path, autocrlf=False)


def test_changed_imported_reference_still_rejects_atomically(tmp_path):
    reference = checkout(tmp_path, autocrlf=True)
    assert "ref_material-" + hashlib.sha256(reference.read_bytes()).hexdigest() + ".svg" == Path(expected_reference()).name
    project = initialize(tmp_path, reference)
    stored = project / expected_reference()
    stored.write_bytes(stored.read_bytes() + b"tampered")
    before = {path.relative_to(project): path.read_bytes()
              for path in project.rglob("*") if path.is_file()}
    code, result = cli("stage0-submit", project, "--proposal", TEMPLATE,
                       "--expected-version", "0")
    assert code == 2 and "hash mismatch" in result["error"].lower(), result
    assert before == {path.relative_to(project): path.read_bytes()
                      for path in project.rglob("*") if path.is_file()}
    assert not (project / "stage0").exists()
