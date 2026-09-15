"""Execute the frozen baseline examples; prose/evidence scope needs human review."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from runtime.validators import validate_contract


ROOT = Path(__file__).resolve().parents[1]


def baseline_block(name):
    document = (ROOT / "docs/v02/baseline.md").read_text(encoding="utf-8")
    section = document.split(f"<!-- executable: {name} -->", 1)[1]
    return json.loads(section.split("```json\n", 1)[1].split("```", 1)[0])


def execute_examples(name, project):
    results = []
    for example in baseline_block(name):
        argv = [str(project) if arg == "PROJECT" else arg for arg in example["argv"]]
        process = subprocess.run(
            [sys.executable, "runtime/cli.py", *argv], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"),
        )
        assert process.returncode == example["exit"], process.stderr
        result = json.loads(process.stdout if process.returncode == 0 else process.stderr)
        for field, expected in example.get("equals", {}).items():
            value = result
            for key in field.split("."):
                value = value[key]
            assert value == expected
        if "error_contains" in example:
            assert example["error_contains"] in result["error"]
        results.append(result)
    return results


def test_baseline_default_example_preserves_official_state(tmp_path):
    project = tmp_path / "default"
    results = execute_examples("baseline-default", project)
    assert results[0] == results[-1] == load_data(project / "manifest.yaml")
    assert results[-1]["schema_version"] == "0.1"
    assert results[-1]["mode"] == "plan_only"
    assert results[-1]["auto_approve"] is False
    assert results[-1]["plan_approved"] is False
    assert results[-1]["version"] == 0
    assert results[-1]["history"] == []
    assert results[-1]["stage2"]["status"] == "not_started"
    assert not list((project / "stage1/outputs").rglob("*"))
    assert not list((project / "stage2/scene").rglob("*"))


def test_baseline_library_example_preserves_versions_and_provenance(tmp_path):
    project = tmp_path / "library"
    results = execute_examples("baseline-library", project)
    manifest = load_data(project / "manifest.yaml")
    assert manifest["state"] == "complete"
    assert manifest["auto_approve"] is False
    assert manifest["stage2"]["status"] == "not_started"
    assert manifest["assets"]["bench"]["status"] == "approved"
    assert manifest["assets"]["bench"]["revision"] == 1
    source_bytes = (ROOT / "examples/library/bench.obj").read_bytes()
    revisions = [load_data(project / f"stage1/results/bench_rev{revision:02d}.json")
                 for revision in (0, 1)]
    assert revisions[0]["files"]["model"] != revisions[1]["files"]["model"]
    for revision, result in enumerate(revisions):
        validate_contract("stage1_result", result)
        assert result["revision"] == revision
        assert result["route"] == "library_direct"
        assert result["status"] == "review_required"
        assert result["source"]["asset_id"] == "demo_bench"
        assert result["source"]["license_verified"] is True
        model = project / result["files"]["model"]
        assert model.read_bytes() == source_bytes
        assert sha256(model) == result["sha256"]
    delivery = results[-2]
    validate_contract("delivery", delivery)
    assert delivery["attribution"] == [revisions[-1]["source"]]
    assert len(delivery["files"]) == 1
    delivered = project / delivery["files"][0]
    assert delivered.read_bytes() == source_bytes
    checksums = load_data(delivered.parent / "checksums.json")
    assert checksums[delivered.name] == sha256(delivered)
    snapshot = load_data(delivered.parent / "manifest.snapshot.yaml")
    assert snapshot["assets"]["bench"]["revision"] == 1
    assert snapshot["assets"]["bench"]["status"] == "approved"
    assert snapshot["version"] < manifest["version"]


@pytest.mark.parametrize("name", ["manifest", "asset_task", "stage1_result",
                                 "blender_plan", "review", "delivery"])
def test_baseline_contract_inventory_accepts_samples_and_rejects_missing_fields(name):
    entry = baseline_block("baseline-contracts")[name]
    documents = load_data(ROOT / "tests/fixtures/governance/contract_bundle.json")["documents"]
    sample = documents[entry["validator"]]
    validate_contract(entry["validator"], sample)
    with pytest.raises(WorkflowError):
        validate_contract(entry["validator"], {})
