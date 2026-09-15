"""Execute the public overview's actual entry; prose semantics need human review."""
import json
import shlex
import subprocess
import sys
from pathlib import Path

from runtime.io import load_data
from runtime.visual_contracts import document_hash

ROOT = Path(__file__).resolve().parents[1]


def sequence():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    marker = '<!-- executable: readme-visual-start -->'
    assert marker in text, 'README lacks an executable entry for the current visual workflow'
    block = text.split(marker, 1)[1].split('```text\n', 1)[1].split('```', 1)[0]
    return [shlex.split(line) for line in block.strip().splitlines()]


def execute(argv, root):
    assert argv[:3] == ['python', '-m', 'runtime.cli']
    args = [str(root) if a == 'projects/v02_demo' else a for a in argv[1:]]
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=30)


def test_readme_entry_creates_reviewable_visual_documents_without_execution(tmp_path):
    commands = sequence()
    assert [a[3] for a in commands] == ['init-v02', 'reference-add-v02', 'stage0-submit', 'status']
    project = tmp_path / 'overview'
    for argv in commands:
        result = execute(argv, project)
        assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert (state['schema_version'], state['version'], state['state'], state['mode']) == ('0.2', 1, 'visual_review_required', 'plan_only')
    assert state['approvals'] == [] and state['auto_approve'] is False
    expected = load_data(ROOT / 'templates/v02_stage0.yaml')
    for kind, document in expected.items():
        entry = state['artifacts'][kind][-1]
        assert load_data(project / entry['path']) == document
        assert entry['sha256'] == document_hash(document)
    ref = expected['reference_board']['references'][0]
    assert (project / ref['path']).read_bytes() == (ROOT / 'examples/v02/reference.svg').read_bytes()
    assert not (project / 'stage1').exists() and not (project / 'stage2').exists()


def test_readme_entry_rejects_stale_submission_without_approval_or_mutation(tmp_path):
    commands = sequence()
    project = tmp_path / 'overview'
    for argv in commands[:2]:
        result = execute(argv, project)
        assert result.returncode == 0, result.stderr
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    stale = list(commands[2])
    stale[stale.index('--expected-version') + 1] = '1'
    result = execute(stale, project)
    assert result.returncode == 2 and 'version' in json.loads(result.stderr)['error'].lower()
    assert before == {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    state = load_data(project / 'manifest.yaml')
    assert state['version'] == 0 and state['approvals'] == [] and state['mode'] == 'plan_only'
