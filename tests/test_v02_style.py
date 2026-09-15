"""Phase 2 behavior; Blender application is separately checked on the real host."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ['painted_metal', 'bare_metal', 'concrete', 'rubber', 'glass', 'emissive']

def cli(*args):
    return subprocess.run([sys.executable, str(ROOT/'runtime/cli.py'), *args], capture_output=True, text=True)

@pytest.mark.parametrize('condition', ['clean', 'lightly_weathered', 'weathered'])
def test_six_materials(condition):
    values = []
    for kind in CLASSES:
        r = cli('style-resolve', '--material', kind, '--condition', condition)
        assert r.returncode == 0, r.stderr
        x = json.loads(r.stdout)
        assert x['material_class'] == kind and x['condition'] == condition
        assert x['profile_version'] == '1.0.0'
        assert Path(x['library']).read_bytes()[:7] == b'BLENDER'
        assert x['resource'] == 'industrial_acg_v1.' + kind
        assert 0 <= x['parameters']['roughness'] <= 1
        assert x['lighting']['profile'] == 'overcast'
        values.append(x['parameters'])
    assert len({x['roughness'] for x in values}) >= 5
    assert values[1]['metallic'] == 1 and values[2]['metallic'] == 0
    assert values[4]['transmission'] == 1 and values[5]['emission_strength'] > 1
    assert values[2]['bump_distance'] > values[4]['bump_distance']

@pytest.mark.parametrize('args', [('--profile','unknown'),('--material','plastic'),('--condition','unknown')])
def test_unknown_rejects(args):
    r=cli('style-resolve','--material','concrete','--condition','clean',*args)
    assert r.returncode == 2
    assert 'Unknown' in json.loads(r.stderr)['error']

def test_missing_or_bad_resources(tmp_path):
    from runtime.style_registry import StyleRegistry
    from runtime.errors import WorkflowError
    import shutil
    shutil.copytree(ROOT/'styles',tmp_path/'styles')
    root=tmp_path/'styles'
    definitions=root/'industrial_acg_v1/materials/definitions.yaml'
    original=definitions.read_text()
    definitions.write_text(original.replace('roughness: 0.82','roughness: 2.0'))
    with pytest.raises(WorkflowError,match='Invalid'):
        StyleRegistry(root).load('industrial_acg_v1')
    definitions.write_text(original)
    (root/'industrial_acg_v1/materials/library.blend').unlink()
    with pytest.raises(WorkflowError,match='Missing'):
        StyleRegistry(root).load('industrial_acg_v1')

def test_default_and_projection(tmp_path):
    from scripts.govern import source_files
    r=cli('init',str(tmp_path/'p'),'--id','p','--brief','test')
    assert r.returncode == 0
    assert json.loads(r.stdout)['mode']=='plan_only'
    files={p.relative_to(ROOT).as_posix() for p in source_files(ROOT)}
    assert 'styles/industrial_acg_v1/materials/library.blend' in files
    assert 'styles/industrial_acg_v1/calibration/calibration.blend' in files
