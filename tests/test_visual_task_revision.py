import copy
import pytest
from runtime.errors import WorkflowError
from tests.visual_task_helpers import reviewed,direction,execution

@pytest.mark.parametrize('invalid',[False,True])
def test_revision_lineage_and_bounded_difference(tmp_path,invalid):
    from runtime.visual_tasks import prepare,start,submit
    m,_,old,revision=reviewed(tmp_path)
    t=prepare(m,{'operation':'refine_direction'},expected_version=m.read()['version'])
    start(m,t['task_id'],expected_version=m.read()['version'])
    new=direction();new.update(direction_id='next direction',parent_direction_id=new['direction_id'],revision=3)
    new['camera']['azimuth_deg']+=50 if invalid else 5
    submit(m,t['task_id'],new,execution=execution(),expected_version=m.read()['version'])
    before=m.path.read_bytes()
    if invalid:
        with pytest.raises(WorkflowError):m.apply_visual_revision(revision,visual_task=t['task_id'],expected_version=m.read()['version'])
        assert m.path.read_bytes()==before
    else:
        state=m.apply_visual_revision(revision,visual_task=t['task_id'],expected_version=m.read()['version'])
        assert state['state']=='render_pending' and state['visual_direction']==t['task_id']
        assert state['visual_tasks'][old['task_id']]['status']=='accepted'
