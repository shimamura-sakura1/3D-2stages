"""Consumer tree integrity, private paths, startup, and data-only sanitization."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_export_keeps_runtime_and_resolves_links(tmp_path):
    from scripts.export_production import export_production
    destination=tmp_path/'consumer';export_production(ROOT,destination)
    paths={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    assert {'SKILL.md','README.md','runtime/cli.py','runtime/render_direction_adapter.py',
            'contracts/render_direction.schema.json','styles/industrial_acg_v1/materials/library.blend'} <= paths
    assert not any(p.startswith(('tests/','changes/','docs/governance/','projects/','.deps/')) for p in paths)
    assert not any(p in paths for p in ('AGENTS.md','requirements.json','scripts/govern.py','scripts/export_production.py'))
    for name in paths:
        raw=(destination/name).read_bytes()
        assert not re.search(rb'(?i)contract[-_ ]govern|CONTRACT_GOVERN_HOME',raw),name
        assert not re.search(rb'/Users/[^/\s]+|[A-Z]:[\\/]Users[\\/]',raw),name
        if name.endswith('.md'):
            for target in re.findall(r'\]\(([^)]+)\)',raw.decode('utf-8')):
                if '://' in target or target.startswith('#'):continue
                assert ((destination/name).parent/target.split('#')[0]).resolve().exists(),(name,target)
    interface=json.loads((destination/'interface.json').read_text())
    for artifact in interface['artifacts']:assert (destination/artifact['path']).is_file()
    result=subprocess.run([sys.executable,'-m','runtime.cli','doctor'],cwd=destination,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert 'governance' not in json.loads(result.stdout)


def test_binary_redaction_only_changes_scene_png_field():
    import struct
    from scripts.sanitize_blend_paths import sanitize
    payload=b'\0/Users/private-owner/work/render.png\0UNCHANGED'
    header=struct.Struct('<4siQii')
    before=b'BLENDER-v405'+header.pack(b'SC\0\0',len(payload),123,1,1)+payload+header.pack(b'ENDB',0,0,0,0)
    after,count=sanitize(before)
    assert count==1 and len(after)==len(before)
    assert after[:36]==before[:36] and after.endswith(b'UNCHANGED'+header.pack(b'ENDB',0,0,0,0))
    assert b'//preview.png\0' in after and b'private-owner' not in after
    assert sanitize(after)==(after,0)


def test_execution_defaults_and_priors_are_separate(tmp_path):
    import shutil,yaml
    from runtime.style_registry import StyleRegistry
    source=ROOT/'styles/industrial_acg_v1'
    target=tmp_path/'styles/industrial_acg_v1';shutil.copytree(source,target)
    camera=target/'camera/environment.yaml';data=yaml.safe_load(camera.read_text())
    data['direction_prior']={'focal_length':{'preferred':[999,1000]}}
    data['execution_default']['focal_length_mm']=42
    camera.write_text(yaml.safe_dump(data))
    style=StyleRegistry(tmp_path/'styles').load('industrial_acg_v1')
    assert style['camera']['focal_length_mm']==style['execution_default']['camera']['focal_length_mm']==42
    assert style['direction_prior']['camera']['focal_length']['preferred']==[999,1000]


def test_maintenance_discovery_is_separate(tmp_path):
    from scripts.framework_support import find_framework
    from runtime.platform_support import environment_report
    from runtime.errors import BoundaryError
    with pytest.raises(BoundaryError):find_framework(tmp_path,environ={})
    assert 'governance' not in environment_report(tmp_path)
