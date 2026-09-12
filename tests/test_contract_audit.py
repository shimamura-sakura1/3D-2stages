import json
import os
import subprocess
import sys
from pathlib import Path

from runtime.io import load_data


ROOT = Path(__file__).resolve().parents[1]


def test_audit_requires_complete_structural_bundle(tmp_path):
    process = subprocess.run([sys.executable, str(ROOT / "scripts/check_contracts.py"), "--output", str(tmp_path)],
                             input='{"documents": {}}', text=True, encoding="utf-8", capture_output=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONUTF8="1"))
    assert process.returncode == 2
    assert "error" in json.loads(process.stderr)
    assert not list(tmp_path.iterdir())


def test_audit_uses_existing_contracts_and_emits_each_document(tmp_path):
    fixture = ROOT / "tests/fixtures/governance/contract_bundle.json"
    process = subprocess.run([sys.executable, str(ROOT / "scripts/check_contracts.py"), "--output", str(tmp_path)],
                             input=fixture.read_text(encoding="utf-8"), text=True, encoding="utf-8", capture_output=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONUTF8="1"))
    assert process.returncode == 0, process.stderr
    documents = json.loads(fixture.read_text(encoding="utf-8"))["documents"]
    assert {p.stem for p in tmp_path.glob("*.json")} == set(documents)
    for name, original in documents.items():
        assert load_data(tmp_path / (name + ".json")) == original
