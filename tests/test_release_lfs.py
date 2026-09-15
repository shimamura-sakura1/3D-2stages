"""Large accepted records survive a cross-machine Git LFS checkout."""

import hashlib
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_change_record_is_lfs_pointer_in_git_and_original_on_disk(tmp_path):
    attributes = (ROOT / ".gitattributes").read_bytes()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".gitattributes").write_bytes(attributes)
    record = checkout / "changes" / "change-999.json"
    record.parent.mkdir()
    original = b'{"accepted":"unaltered evidence"}\n'
    record.write_bytes(original)

    git = shutil.which("git")
    assert git and shutil.which("git-lfs"), "Git and Git LFS are required for development checkout"
    subprocess.run([git, "init", "-q"], cwd=checkout, check=True)
    subprocess.run([git, "lfs", "install", "--local"], cwd=checkout, check=True,
                   capture_output=True)
    subprocess.run([git, "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        [git, "-c", "user.name=Release Test", "-c", "user.email=release-test@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=checkout,
        check=True,
    )
    stored = subprocess.check_output([git, "show", "HEAD:changes/change-999.json"], cwd=checkout)
    assert stored.startswith(b"version https://git-lfs.github.com/spec/v1\n")
    assert b"oid sha256:" + hashlib.sha256(original).hexdigest().encode() in stored
    assert record.read_bytes() == original
