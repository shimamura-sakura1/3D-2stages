"""Retain portable runtime assertions while moving maintainer discovery out of it."""
import json
from pathlib import Path
import pytest
from tests import test_portability as history
from tests import test_governance_newlines as newlines

globals().update({name:value for name,value in vars(history).items()
    if name.startswith('test_') and name not in ('test_positive_framework_resolution_and_memory_projection',
       'test_rejection_missing_framework_is_explicit','test_positive_documented_doctor_example')})
globals().update({name:value for name,value in vars(newlines).items()
    if name.startswith('test_') and name!='test_positive_restores_exact_historical_bytes_only_in_projection'})


def test_framework_resolution_stays_in_maintenance(tmp_path):
    from scripts.framework_support import find_framework
    from scripts.govern import snapshot
    from runtime.errors import BoundaryError
    repo=tmp_path/'project';sibling=tmp_path/'contract-govern-skil';override=tmp_path/'custom'
    for path in (sibling,override):
        (path/'skillctl').mkdir(parents=True);(path/'skillctl/__main__.py').write_text('')
        (path/'spec').mkdir();(path/'spec/SPEC.md').write_text('fixture')
    assert find_framework(repo,environ={})==sibling
    assert find_framework(repo,environ={'CONTRACT_GOVERN_HOME':str(override)})==override
    assert find_framework(repo,str(sibling),environ={'CONTRACT_GOVERN_HOME':str(override)})==sibling
    with pytest.raises(BoundaryError):find_framework(tmp_path/'missing/repo',environ={})
    repo.mkdir();(repo/'AGENTS.md').write_text('Project maintenance instructions')
    assert 'AGENTS.md' in snapshot(repo)


def test_doctor_only_reports_runtime(capsys):
    from runtime.cli import main
    assert main(['doctor'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['mcp']['status']=='requires_session_check' and 'governance' not in result


def test_history_transport_recovery_is_unchanged(tmp_path):
    from scripts import govern
    root,previous,first,support,fixture=newlines.package(tmp_path)
    original=tmp_path/'original.json';original.write_bytes(support.read_bytes())
    latest=(root/'changes/change-002.json').read_bytes()
    restored=govern.restore_recorded_newlines(root)
    assert sorted(restored)==['changes/change-001.json','tests/fixture.json']
    assert previous.read_bytes()==first and support.read_bytes()==fixture
    assert original.read_bytes()==fixture.replace(b'\r\n',b'\n')
    assert (root/'changes/change-002.json').read_bytes()==latest
