"""A source checkout keeps evidence; a consumer archive omits it."""

import shutil
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_git_archive_keeps_runtime_and_omits_maintenance_files(tmp_path):
    attributes = (ROOT / ".gitattributes").read_bytes()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".gitattributes").write_bytes(attributes)
    sample_files = {
        "SKILL.md": "runtime entry",
        "runtime/cli.py": "runtime",
        "prompts/parent.md": "prompt",
        "templates/asset_task.yaml": "template",
        "docs/platforms.md": "platform guide",
        "tests/test_example.py": "maintenance test",
        "tests/manifest.json": "{}",
        "changes/change-001.json": "{}",
        "docs/governance/EVOLVE.md": "maintenance guide",
        "AGENTS.md": "maintainer instructions",
        "requirements.json": "{}",
        "requirements-tested.txt": "pytest",
        "scripts/govern.py": "maintenance tool",
        "scripts/govern.ps1": "maintenance tool",
        "scripts/test.ps1": "maintenance tool",
    }
    for relative, content in sample_files.items():
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    git = shutil.which("git")
    assert git, "Git is required to create the release archive"
    subprocess.run([git, "init", "-q"], cwd=checkout, check=True)
    subprocess.run([git, "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        [git, "-c", "user.name=Release Test", "-c", "user.email=release-test@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=checkout,
        check=True,
    )
    source_files = subprocess.check_output([git, "ls-files"], cwd=checkout, text=True).splitlines()
    assert "tests/test_example.py" in source_files
    assert "tests/manifest.json" in source_files

    archive = tmp_path / "skill.zip"
    subprocess.run([git, "archive", "--format=zip", f"--output={archive}", "HEAD"],
                   cwd=checkout, check=True)
    with zipfile.ZipFile(archive) as package:
        published = set(package.namelist())
    assert {"SKILL.md", "runtime/cli.py", "prompts/parent.md",
            "templates/asset_task.yaml", "docs/platforms.md"} <= published
    assert not any(path.startswith("tests/") for path in published)
    assert not any(path.startswith("changes/") for path in published)
    assert "docs/governance/EVOLVE.md" not in published
    assert "AGENTS.md" not in published
    assert "requirements.json" not in published
    assert "requirements-tested.txt" not in published
    assert "scripts/govern.py" not in published
    assert "scripts/govern.ps1" not in published
    assert "scripts/test.ps1" not in published
