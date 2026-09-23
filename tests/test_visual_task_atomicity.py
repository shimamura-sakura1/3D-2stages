import pytest
from runtime.errors import WorkflowError
from tests.visual_task_helpers import setup,candidate

def test_rejected_plan_adoption_leaves_candidate_and_manifest_unchanged(tmp_path):
    m,spec=setup(tmp_path);t=candidate(m,spec);before=m.path.read_bytes()
    spec['plans']['blockout_plan']['objects'][0]['transform']['location'][0]+=1
    with pytest.raises(WorkflowError):m.submit_scene_plans(spec['plans'],visual_task=t['task_id'],expected_version=m.read()['version'])
    assert m.path.read_bytes()==before

def test_task_progress_does_not_invalidate_same_input_baseline(tmp_path):
    from runtime.visual_tasks import prepare,start,submit
    from tests.visual_task_helpers import direction,execution
    m,spec=setup(tmp_path);t=prepare(m,spec,expected_version=m.read()['version'])
    start(m,t['task_id'],expected_version=m.read()['version'])
    submit(m,t['task_id'],direction(),execution=execution(),expected_version=m.read()['version'])
    m.submit_scene_plans(spec['plans'],visual_task=t['task_id'],expected_version=m.read()['version'])
    assert m.read()['visual_tasks'][t['task_id']]['status']=='accepted'
def test_accepted_executor_and_source_metadata_are_immutable(tmp_path):
    import copy
    import pytest
    from runtime.errors import WorkflowError
    from runtime.visual_tasks import read_task
    from tests.visual_task_helpers import adopted
    m,_,task=adopted(tmp_path);state=copy.deepcopy(m.read())
    state['visual_tasks'][task['task_id']]['selection']['reason']='Changed after acceptance'
    with pytest.raises(WorkflowError):read_task(m,task['task_id'],state)
