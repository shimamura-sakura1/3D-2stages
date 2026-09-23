import copy
import pytest
from runtime.errors import WorkflowError
from runtime.io import load_data
from tests.visual_task_helpers import setup, direction, execution


def test_prepare_and_submit_are_not_production_acceptance(tmp_path):
    from runtime.visual_tasks import prepare, start, submit, status
    m,spec=setup(tmp_path); before=m.read()
    task=prepare(m,spec,expected_version=before['version'])
    request=load_data(m.root/task['request_path'])
    assert request['operation']=='create_direction'
    assert set(request['inputs']) >= {'visual_brief','scene_context','style_context'}
    assert m.read()['state']==before['state'] and m.read()['approvals']==before['approvals']
    start(m,task['task_id'],expected_version=m.read()['version'])
    submit(m,task['task_id'],direction(),execution=execution(),expected_version=m.read()['version'])
    assert status(m,task['task_id'])['status']=='result_available'
    assert 'visual_direction' not in m.read()


@pytest.mark.parametrize('problem',['identity','coverage','stale','tamper','parent'])
def test_rejection_does_not_change_official_state(tmp_path,problem):
    from runtime.visual_tasks import prepare,start,submit
    m,spec=setup(tmp_path);task=prepare(m,spec,expected_version=m.read()['version'])
    start(m,task['task_id'],expected_version=m.read()['version'])
    d=direction(); version=m.read()['version']
    if problem=='identity':d['camera']['subject_ref']='other'
    if problem=='coverage':d['camera']['subject_coverage']=0
    if problem=='parent':d['parent_direction_id']='unknown'
    if problem=='stale':version-=1
    if problem=='tamper':(m.root/task['request_path']).write_text('{}')
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):submit(m,task['task_id'],d,execution=execution(),expected_version=version)
    assert m.path.read_bytes()==before


def test_plan_only_cannot_prepare_execution_task(tmp_path):
    from runtime.visual_tasks import prepare
    m,spec=setup(tmp_path);m.configure_visual('plan_only',expected_version=m.read()['version'])
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):prepare(m,spec,expected_version=m.read()['version'])
    assert m.path.read_bytes()==before


@pytest.mark.parametrize('operation',['create_direction','review_render','refine_direction'])
def test_three_operation_contract_fixtures(operation):
    from pathlib import Path
    from runtime.validators import validate_contract
    fixture=load_data(Path(__file__).parent/'fixtures/visual_tasks'/f'{operation}.json')
    validate_contract('visual_task_request',fixture['valid_request'])
    with pytest.raises(WorkflowError):validate_contract('visual_task_request',fixture['invalid_request'])
    validate_contract('visual_task_review' if operation=='review_render' else 'visual_task_direction',fixture['expected_result'])


def test_request_path_cannot_escape_task_directory_even_with_matching_digest(tmp_path):
    import hashlib,json,copy
    from runtime.visual_tasks import prepare,read_task
    m,spec=setup(tmp_path);task=prepare(m,spec,expected_version=m.read()['version'])
    path=m.root/task['request_path'];request=load_data(path)
    request['inputs']['visual_brief']='../foreign.json'
    raw=json.dumps(request).encode();path.write_bytes(raw)
    state=copy.deepcopy(m.read());state['visual_tasks'][task['task_id']]['files'][task['request_path']]=hashlib.sha256(raw).hexdigest()
    with pytest.raises(WorkflowError):read_task(m,task['task_id'],state)
