import pytest
from runtime.errors import WorkflowError

def test_missing_optional_executor_selects_main():
    from runtime.visual_task_adapter import select_executor
    assert select_executor({'mode':'auto'})['executor']=='main'

def test_explicit_missing_executor_rejects():
    from runtime.visual_task_adapter import select_executor
    with pytest.raises(WorkflowError):select_executor({'mode':'external','home':'missing-for-test'})

def test_explicit_main_never_uses_configured_external():
    from runtime.visual_task_adapter import select_executor
    assert select_executor({'mode':'main','home':'missing-for-test'})['executor']=='main'


@pytest.mark.parametrize('external',[False,True])
@pytest.mark.parametrize('knowledge',[False,True])
def test_prepare_routes_all_four_combinations(tmp_path,monkeypatch,external,knowledge):
    from runtime.visual_tasks import prepare,read_task
    from tests.visual_task_helpers import setup
    from tests.test_visual_task_adapter import implementation
    from tests.test_visual_task_knowledge import make_kb
    m,spec=setup(tmp_path);config={'mode':'auto'}
    if external:config['home']=str(implementation(tmp_path,monkeypatch))
    if knowledge:config['knowledge_home']=str(make_kb(tmp_path))
    spec.update(execution_config=config,knowledge={'item_ids':['camera.test']})
    task=prepare(m,spec,expected_version=m.read()['version'])
    _,_,_,values=read_task(m,task['task_id'])
    assert task['executor']==('external' if external else 'main')
    assert ('knowledge_context' in values)==knowledge


def test_prepare_explicit_unavailable_does_not_write_or_fallback(tmp_path):
    from runtime.visual_tasks import prepare
    from tests.visual_task_helpers import setup
    m,spec=setup(tmp_path);spec['execution_config']={'mode':'external','home':str(tmp_path/'absent')}
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):prepare(m,spec,expected_version=m.read()['version'])
    assert m.path.read_bytes()==before and not (m.root/'stage2/visual_tasks').exists()
