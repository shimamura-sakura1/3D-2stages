"""Check declared routes and execute documented commands, not prose semantics."""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_v02_geometry import ready, request

ROOT = Path(__file__).resolve().parents[1]


def steps():
    router = (ROOT / 'SKILL.md').read_text().split('## Execution Router', 1)[1].split('\n## ', 1)[0]
    return {part.split(' — ', 1)[0]: part for part in re.split(r'\n### Step ', router)[1:]}


def edges():
    # Markdown's declared graph only. This deliberately does not interpret Action prose.
    return {key: set(re.findall(r'^- (?:Go to )?Step ([\w-]+)\s*$', body, re.M))
            for key, body in steps().items()}


def documented(step, replacements):
    body = steps()[step]
    blocks = re.findall(r'```text\n(.*?)```', body, re.S)
    assert len(blocks) == 1, f'Step {step} needs one executable CLI entry example'
    argv = shlex.split(blocks[0].strip())
    assert argv[:3] == ['python', '-m', 'runtime.cli']
    return [sys.executable, *[str(replacements.get(arg, arg)) for arg in argv[1:]]]


def execute(step, replacements):
    return subprocess.run(documented(step, replacements), cwd=ROOT, capture_output=True, text=True, timeout=30)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_visual_dispatch_cannot_reach_legacy_execution():
    graph = edges()
    reached, pending = set(), ['2']
    while pending:
        node = pending.pop()
        if node in reached:
            continue
        reached.add(node)
        pending.extend(graph[node] - reached)
    assert not reached.intersection({'3', '4', '5', 'L'}), f'Visual dispatch reaches legacy: {reached}'
    assert {'1G', '5V', '6V', '7V', '8V', '6'} <= reached
    for source, target in [('1', '0V'), ('1', 'L'), ('0V', '2'), ('1G', '5V'),
                           ('5V', '6V'), ('6V', '7V'), ('7V', '6'), ('6', '7V'),
                           ('7V', '8V'), ('8V', '6V'), ('L', '3'), ('4', '6')]:
        assert target in graph[source], f'Missing {source} -> {target}'


def test_documented_default_creates_unapproved_visual_project(tmp_path):
    project = tmp_path / 'new-scene'
    result = execute('0V', {'PROJECT': project, 'PROJECT_ID': 'station', 'BRIEF': 'Quiet station'})
    assert result.returncode == 0, result.stderr
    from runtime.manifest_manager import ManifestManager
    state = ManifestManager(project).read()
    assert (state['schema_version'], state['state'], state['mode']) == ('0.2', 'initialized', 'plan_only')
    assert state['approvals'] == [] and state['auto_approve'] is False
    assert not state['assets'] and not state.get('geometry_assets') and not state['artifacts']


@pytest.mark.parametrize('authorized', [True, False])
def test_documented_geometry_execution_and_authorization_gate(tmp_path, authorized):
    manager = ready(tmp_path)
    if not authorized:
        manager.configure_visual('plan_only', expected_version=manager.read()['version'])
    payload = request('platform', None, 'A')
    payload['task']['hy3d']['enabled'] = False
    req = tmp_path / 'request.json'
    req.write_text(json.dumps(payload))
    before = snapshot(manager.root)
    result = execute('1G', {'PROJECT': manager.root, 'REQUEST': req,
                            'CATALOG': ROOT / 'examples/library/catalog.yaml'})
    if not authorized:
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stderr)['error'] == 'Geometry acquisition prohibited in this mode'
        assert snapshot(manager.root) == before
        return
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['route'] == 'A' and output['recipe']['searched_providers'] == ['local_library']
    assert (manager.root / output['geometry']['model']).is_file()
    assert output['provenance']['license_verified'] is True
    state = manager.read()
    assert state['geometry_assets']['platform']['status'] == 'review_required'
    assert not any(a.get('scope') == 'geometry' and a.get('decision') == 'approved' for a in state['approvals'])


def test_documented_legacy_asset_entry_remains_isolated(tmp_path):
    from runtime.planning import create_project
    from runtime.manifest_manager import ManifestManager
    from runtime.io import load_data
    project = tmp_path / 'legacy'
    create_project(project, 'legacy', 'bench', mode='full_pipeline',
                   tasks=[load_data(ROOT / 'templates/asset_task.yaml')])
    manager = ManifestManager(project)
    manager.approve_plan()
    result = execute('3', {'PROJECT': project, 'ASSET_ID': 'bench',
                           'CATALOG': ROOT / 'examples/library/catalog.yaml'})
    assert result.returncode == 0, result.stderr
    state = manager.read()
    assert state['schema_version'] == '0.1' and state['assets']['bench']['status'] == 'review_required'
    assert state['stage2']['status'] == 'not_started'
