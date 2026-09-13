"""Run the README offline example and verify actual assets and the review gate."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
readme = (ROOT / "README.md").read_text(encoding="utf-8")
example = readme.split("<!-- executable: offline-asset -->", 1)[1].split("```powershell\n", 1)[1].split("```", 1)[0]
with tempfile.TemporaryDirectory(prefix="readme-flow-") as temporary:
    project = Path(temporary) / "project"
    outputs = []
    for line in example.strip().splitlines():
        argv = shlex.split(line)
        assert argv[:3] == ["python", "-m", "runtime.cli"]
        argv = [str(project) if arg == "projects/readme_demo" else arg for arg in argv[1:]]
        result = subprocess.run([sys.executable, *argv], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", timeout=30,
                                env=dict(os.environ, PYTHONUTF8="1"))
        assert result.returncode == 0, result.stderr
        outputs.append(json.loads(result.stdout))
    assert outputs[-1]["assets"]["bench"]["status"] == "review_required"
    result = json.loads((project / "stage1/results/bench_rev00.json").read_text(encoding="utf-8"))
    assert result["route"] == "library_direct"
    assert result["source"]["asset_id"] == "demo_bench"
    assert any(p.read_bytes() == (ROOT / "examples/library/bench.obj").read_bytes()
               for p in (project / "stage1/outputs").rglob("*.obj"))
print(json.dumps({"readme_offline_asset": "pass", "review_required": True}))
