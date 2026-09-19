"""Developer setup must stay local, preserve settings, and report real readiness."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper():
    spec = importlib.util.spec_from_file_location('setup_dev', ROOT / 'scripts/setup_dev.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_preserves_secrets_and_unrelated_settings(tmp_path):
    module = helper()
    (tmp_path / '.env').write_text('HY3D_API_TOKEN=private-test-value\nOTHER=keep\nBLENDER_EXECUTABLE=old\n')
    module.save_local(tmp_path, {'blender': '/installed/blender', 'framework': '/dev/framework'})
    data = (tmp_path / '.env').read_text()
    assert 'HY3D_API_TOKEN=private-test-value\nOTHER=keep\n' in data
    assert "BLENDER_EXECUTABLE='/installed/blender'" in data
    assert data.count('BLENDER_EXECUTABLE=') == 1
    assert module.load_local(tmp_path)['framework'] == '/dev/framework'
    module.save_local(tmp_path, {'render_director': '/dev/director'})
    assert module.load_local(tmp_path)['blender'] == '/installed/blender'


def test_default_check_does_not_write_or_claim_mcp_connected(tmp_path, monkeypatch):
    module = helper()
    monkeypatch.setattr(module, 'inspect_blender', lambda p: {'status': 'missing'})
    report = module.inspect_host(tmp_path, {})
    assert report['mcp']['status'] == 'not_checked'
    assert report['ready_for_development'] is False
    assert list(tmp_path.iterdir()) == []


def test_invalid_explicit_installation_rejects_before_writes(tmp_path):
    module = helper()
    with pytest.raises(ValueError, match='Blender'):
        module.configure(tmp_path, {'blender': str(tmp_path/'missing')}, write=True)
    assert list(tmp_path.iterdir()) == []


def test_blender_version_is_verified_and_old_version_rejects(tmp_path, monkeypatch):
    module = helper()
    executable = tmp_path / 'blender.exe'
    executable.touch()
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, 'Blender 5.2.1 LTS\n', ''))
    assert module.inspect_blender(str(executable))['version'] == [5, 2, 1]
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, 'Blender 4.1.0\n', ''))
    assert module.inspect_blender(str(executable))['status'] == 'unsupported'


def test_cli_invalid_path_returns_json_error():
    result = subprocess.run([sys.executable, str(ROOT/'scripts/setup_dev.py'), '--blender', 'missing-installation-for-test', '--write-local'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)['status'] == 'error'


def test_release_excludes_development_docs_and_setup(tmp_path):
    from scripts.export_production import export_production
    out = export_production(ROOT, tmp_path/'release')
    assert (ROOT/'docs/development.md').is_file()
    assert not (out/'docs/development.md').exists()
    assert not (out/'scripts/setup_dev.py').exists()
    assert not (out/'scripts/prepare_release.py').exists()
    assert (out/'SKILL.md').is_file()


def test_director_requires_matching_public_schemas(tmp_path, monkeypatch):
    module = helper()
    monkeypatch.setattr(module, 'inspect_blender', lambda p: {'status': 'ready'})
    director=tmp_path/'director'
    (director/'contracts').mkdir(parents=True)
    (director/'SKILL.md').write_text('director')
    (tmp_path/'contracts').mkdir()
    for name in ('render_context','render_direction','render_review'):
        relative=f'contracts/{name}.schema.json'
        (tmp_path/relative).write_text('{"type":"object"}')
        (director/relative).write_text('{ "type": "object" }')
    settings={'render_director':str(director)}
    assert module.inspect_host(tmp_path,settings)['render_director']['status']=='ready'
    (director/'contracts/render_direction.schema.json').write_text('{"type":"array"}')
    assert module.inspect_host(tmp_path,settings)['render_director']['status']=='incompatible'
    with pytest.raises(ValueError,match='incompatible'):
        module.configure(tmp_path,settings,write=True)
    assert not (tmp_path/'.deps').exists()
