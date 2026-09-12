"""Frozen migration scenario: actual CLI processes; no Blender/GPU calls."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def characterize():
    with tempfile.TemporaryDirectory(prefix="two-stage-characterization-") as temporary:
        project = Path(temporary) / "scene"
        def call(*args, expected=0):
            result = subprocess.run([sys.executable, "-m", "runtime.cli", *map(str, args)], cwd=ROOT,
                                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                                    env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"))
            assert result.returncode == expected, (args, result.stdout, result.stderr)
            return json.loads(result.stdout if expected == 0 else result.stderr)
        call("init", project, "--id", "characterization", "--brief", "A quiet station", "--asset", "bench")
        before = (project / "manifest.yaml").read_bytes()
        assert call("run", project)["status"] == "plan_only"
        assert before == (project / "manifest.yaml").read_bytes()
        call("configure", project, "--mode", "full_pipeline")
        call("approve-plan", project)
        result = call("stage1", project, "--asset-id", "bench", "--catalog", ROOT / "examples/library/catalog.yaml")
        assert result["route"] == "library_direct" and result["status"] == "review_required"
        (project / "stage2/blender_plan.yaml").write_bytes((ROOT / "templates/blender_plan.yaml").read_bytes())
        assert "not approved" in call("stage2", project, "--dry-run", expected=2)["error"]
        call("review", project, "bench", "--decision", "approved")
        assert call("stage2", project, "--dry-run")["status"] == "preflight_passed"
        packet = call("stage2", project)
        assert packet["status"] == "mcp_execution_required"
        assert "incomplete" in call("stage2-complete", project, "--build-id", packet["build_id"], expected=2)["error"]
        call("configure", project, "--target", "asset")
        delivered = call("deliver", project)
        assert (project / delivered["files"][0]).is_file()
        assert delivered["attribution"][0]["asset_id"] == "demo_bench"
        return {"plan_only_unchanged": True, "route": result["route"], "asset_review_required": True,
                "unapproved_stage2_blocked": True, "approved_preflight": True,
                "mcp_preparation_is_not_build": True, "incomplete_outputs_blocked": True,
                "asset_delivery_with_provenance": True}


if __name__ == "__main__":
    actual = characterize()
    expected = json.loads((ROOT / "tests/fixtures/governance/legacy_expected.json").read_text(encoding="utf-8"))
    assert actual == expected
    print(json.dumps(actual, sort_keys=True))
