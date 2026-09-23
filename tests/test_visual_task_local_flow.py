from tests.visual_task_helpers import adopted,reviewed
from runtime.visual_planning import current_documents

def test_local_direction_is_adopted_with_plans_and_packet_guards(tmp_path):
    from runtime.scene_production import prepare_scene
    from runtime.io import load_data
    m,_,task=adopted(tmp_path);state=m.read()
    assert state['visual_direction']==task['task_id'] and state['state']=='blockout_pending'
    packet=load_data(prepare_scene(m)['packet'])
    assert packet['plans']['render_plan']['visual_task']['task_id']==task['task_id']
    assert any('visual_tasks' in p for p in packet['guard'])

def test_empty_recommendation_groups_allow_final_review(tmp_path):
    m,_,_,_=reviewed(tmp_path,False)
    assert m.read()['state']=='final_review_required'
