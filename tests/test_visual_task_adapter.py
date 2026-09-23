import json
import shutil
from pathlib import Path

def implementation(tmp_path,monkeypatch):
    # Dependency availability is a test double; schemas and selection run normally.
    monkeypatch.setattr('runtime.visual_task_adapter._runtime_ready',lambda _:True)
    from runtime.visual_task_adapter import select_executor,SCHEMA_NAMES
    root=Path(__file__).resolve().parents[1];home=tmp_path/'module';(home/'contracts').mkdir(parents=True);(home/'runtime').mkdir()
    (home/'SKILL.md').write_text('A caller-selected visual task.')
    for name in ('load_task','publish_result'):(home/'runtime'/f'{name}.py').write_text('')
    reverse={f'visual_task_{b}.schema.json':f'{a}.schema.json' for a,b in SCHEMA_NAMES.items()}
    for external,local in SCHEMA_NAMES.items():
        text=(root/'contracts'/f'visual_task_{local}.schema.json').read_text(encoding='utf-8')
        for a,b in reverse.items():text=text.replace(a,b)
        (home/'contracts'/f'{external}.schema.json').write_text(text,encoding='utf-8')
    return home


def test_real_file_protocol_is_selected_only_after_compatibility_check(tmp_path,monkeypatch):
    from runtime.visual_task_adapter import select_executor
    home=implementation(tmp_path,monkeypatch)
    selected=select_executor({'mode':'auto','home':str(home)})
    assert selected['executor']=='external' and selected['transport']=='agent_file_task'
    (home/'contracts/render_review.schema.json').write_text('{}')
    assert select_executor({'mode':'auto','home':str(home)})['executor']=='main'


def test_published_result_is_collected_before_any_retry(tmp_path,monkeypatch):
    import pytest
    from runtime.errors import WorkflowError
    from runtime.visual_tasks import prepare,start,status,interrupt
    from runtime.visual_task_adapter import collect
    from tests.visual_task_helpers import setup,direction,execution
    home=implementation(tmp_path,monkeypatch)
    m,spec=setup(tmp_path);spec['execution_config']={'home':str(home)}
    task=prepare(m,spec,expected_version=m.read()['version']);identity=task['task_id']
    start(m,identity,expected_version=m.read()['version'])
    folder=m.root/Path(task['request_path']).parent/'outputs';folder.mkdir()
    (folder/'result.json').write_text(json.dumps(direction()),encoding='utf-8')
    assert status(m,identity)['recovery']['next_action']=='collect_result'
    interrupt(m,identity,'Caller ended after publishing.',expected_version=m.read()['version'])
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):start(m,identity,expected_version=m.read()['version'])
    assert m.path.read_bytes()==before
    result=collect(m,identity,execution=execution(),expected_version=m.read()['version'])
    assert result['status']=='result_available' and result['attempt']==1
