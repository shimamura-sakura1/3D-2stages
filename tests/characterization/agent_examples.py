"""Execute documented command examples; do not claim natural-language understanding."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
guide = (root / "docs/workflow.md").read_text(encoding="utf-8")
block = guide.split("```json\n", 1)[1].split("```", 1)[0]
examples = json.loads(block)
with tempfile.TemporaryDirectory(prefix="documented-workflow-") as temporary:
    for example in examples:
        args = [str(Path(temporary) / "project") if arg == "PROJECT" else arg for arg in example["argv"]]
        result = subprocess.run([sys.executable, "runtime/cli.py", *args], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", timeout=30,
                                env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"))
        assert result.returncode == example["exit"], result.stderr
        output = json.loads(result.stdout if result.returncode == 0 else result.stderr)
        value = output[example["field"]]
        if "equals" in example:
            assert value == example["equals"]
        if "contains" in example:
            assert example["contains"] in value
print(json.dumps({"documented_examples_executed": len(examples), "scope": "command behavior only"}))
