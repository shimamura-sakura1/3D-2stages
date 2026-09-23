import pytest
from runtime.errors import WorkflowError
from tests.visual_task_helpers import setup,direction,execution,candidate

def test_prepare_reuses_identical_pending_task_without_writes(tmp_path):
    from runtime.visual_tasks import prepare
    m,spec=setup(tmp_path);first=prepare(m,spec,expected_version=m.read()['version']);before=m.path.read_bytes()
    second=prepare(m,spec,expected_version=m.read()['version'])
    assert second['task_id']==first['task_id'] and m.path.read_bytes()==before

def test_interrupted_task_can_resume_but_running_or_completed_cannot_restart(tmp_path):
    from runtime.visual_tasks import prepare,start,interrupt,submit
    m,spec=setup(tmp_path);t=prepare(m,spec,expected_version=m.read()['version']);identity=t['task_id']
    start(m,identity,expected_version=m.read()['version'])
    with pytest.raises(WorkflowError):start(m,identity,expected_version=m.read()['version'])
    interrupt(m,identity,'Caller confirmed previous attempt ended.',expected_version=m.read()['version'])
    r=start(m,identity,expected_version=m.read()['version']);assert r['attempt']==2
    submit(m,identity,direction(),execution=execution(),expected_version=m.read()['version'])
    with pytest.raises(WorkflowError):start(m,identity,expected_version=m.read()['version'])

def test_started_attempts_are_bounded(tmp_path):
    from runtime.visual_tasks import prepare,start,interrupt
    m,spec=setup(tmp_path);t=prepare(m,spec,expected_version=m.read()['version'])
    for _ in range(3):
        start(m,t['task_id'],expected_version=m.read()['version'])
        interrupt(m,t['task_id'],'Confirmed ended',expected_version=m.read()['version'])
    with pytest.raises(WorkflowError):start(m,t['task_id'],expected_version=m.read()['version'])
