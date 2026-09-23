from tests.visual_task_helpers import adopted,reviewed

def test_formal_inventory_has_accepted_inputs_and_no_unaccepted_task(tmp_path):
    from runtime.visual_delivery import formal_files
    from runtime.visual_tasks import prepare
    from tests.visual_task_helpers import render_fixture
    m,_,t=adopted(tmp_path);render_fixture(m)
    pending=prepare(m,{'operation':'review_render'},expected_version=m.read()['version'])
    paths={x['path'] for x in formal_files(m,m.read())}
    assert m.read()['visual_tasks'][t['task_id']]['result_path'] in paths
    assert not any(pending['task_id'] in p for p in paths)
