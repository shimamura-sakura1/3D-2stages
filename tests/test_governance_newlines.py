"""Restore only newline transport changes authenticated by accepted SHA256s."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import govern


def digest(value):
    return hashlib.sha256(value).hexdigest()


def package(tmp_path, converted=True):
    root = tmp_path / "projection"
    (root / "changes").mkdir(parents=True)
    (root / "tests").mkdir()
    fixture = b'{\r\n  "valid": true\r\n}\r\n'
    first = json.dumps({"previous_record_sha256": None, "snapshot": {}}, indent=2).encode().replace(b"\n", b"\r\n")
    previous = root / "changes/change-001.json"
    previous.write_bytes(first.replace(b"\r\n", b"\n") if converted else first)
    latest = root / "changes/change-002.json"
    latest.write_text(json.dumps({"previous_record_sha256": digest(first),
                                 "snapshot": {"tests/fixture.json": digest(fixture)}}))
    support = root / "tests/fixture.json"
    support.write_bytes(fixture.replace(b"\r\n", b"\n") if converted else fixture)
    return root, previous, first, support, fixture


def test_positive_restores_exact_historical_bytes_only_in_projection(tmp_path):
    root, previous, first, support, fixture = package(tmp_path)
    original = tmp_path / "original-test.json"
    original.write_bytes(support.read_bytes())
    latest = (root / "changes/change-002.json").read_bytes()
    guide = (Path(__file__).resolve().parents[1] / "docs/platforms.md").read_text()
    example = json.loads(guide.rsplit("```json\n", 1)[1].split("```", 1)[0])
    restored = getattr(govern, example["projection_action"])(root)
    assert sorted(restored) == ["changes/change-001.json", "tests/fixture.json"]
    assert previous.read_bytes() == first
    assert support.read_bytes() == fixture
    assert original.read_bytes() == fixture.replace(b"\r\n", b"\n")
    assert (root / "changes/change-002.json").read_bytes() == latest


def test_default_matching_history_remains_byte_identical(tmp_path):
    root, previous, first, support, fixture = package(tmp_path, converted=False)
    assert govern.restore_recorded_newlines(root) == []
    assert previous.read_bytes() == first and support.read_bytes() == fixture


@pytest.mark.parametrize("target", ["history", "support"])
def test_rejection_semantic_changes_are_never_repaired(tmp_path, target):
    root, previous, first, support, fixture = package(tmp_path, converted=False)
    path = previous if target == "history" else support
    changed = path.read_bytes() + b"changed"
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="newline"):
        govern.restore_recorded_newlines(root)
    assert path.read_bytes() == changed


def test_rejection_recorded_paths_cannot_escape_projection(tmp_path):
    root, previous, first, support, fixture = package(tmp_path, converted=False)
    latest = root / "changes/change-002.json"
    data = json.loads(latest.read_text())
    data["snapshot"] = {"tests/../../outside": "0" * 64}
    latest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="projection"):
        govern.restore_recorded_newlines(root)
