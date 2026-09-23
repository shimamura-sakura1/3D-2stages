from tests.visual_task_helpers import reviewed

def test_fixture_approval_delivers_new_task_evidence(tmp_path):
    """Approval and rendered pixels are explicit test fixtures, not live art evidence."""
    from runtime.visual_delivery import final_review_context
    m,_,task,_=reviewed(tmp_path,False)
    context=final_review_context(m)
    assert context
    m.final_review_v02('approved',expected_version=m.read()['version'])
    result=m.deliver_v02(expected_version=m.read()['version'])
    assert m.read()['state']=='delivered'



def test_refinement_resume_second_render_and_delivery_remain_one_history(tmp_path):
    import copy,pytest
    from runtime.errors import WorkflowError
    from runtime.visual_tasks import prepare,start,interrupt,submit,read_task
    from tests.visual_task_helpers import direction,execution,render_fixture
    from tests.test_v02_critic import review_for
    m,_,original,revision=reviewed(tmp_path)
    task=prepare(m,{'operation':'refine_direction'},expected_version=m.read()['version']);identity=task['task_id']
    start(m,identity,expected_version=m.read()['version'])
    interrupt(m,identity,'Fixture caller ended before authoring.',expected_version=m.read()['version'])
    start(m,identity,expected_version=m.read()['version'])
    d=direction();d.update(direction_id='child-direction',parent_direction_id=d['direction_id'],revision=1)
    d['camera']['azimuth_deg']+=5
    submit(m,identity,d,execution=execution(),expected_version=m.read()['version'])
    m.apply_visual_revision(revision,visual_task=identity,expected_version=m.read()['version'])
    metadata=render_fixture(m)
    review_task=prepare(m,{'operation':'review_render'},expected_version=m.read()['version'])
    start(m,review_task['task_id'],expected_version=m.read()['version'])
    report={'schema_version':'1.0','review_id':'fixture-final-review','direction_id':d['direction_id'],'direction_revision':1,
        'render_path':'inputs/render/preview.png','findings':[],'successful_decisions':[{'category':'camera','observation':'Synthetic second-pass framing fixture'}],
        'recommended_changes':{'camera':{},'composition':{},'lighting':{},'atmosphere':{}},'preserve':['approved_geometry']}
    submit(m,review_task['task_id'],report,expected_version=m.read()['version'])
    production=review_for(m,metadata,'final_review_required');production.update(document_id='review_pass_01',revision=1,recommended_actions=[])
    m.submit_render_review(production,visual_task=review_task['task_id'],expected_version=m.read()['version'])
    with pytest.raises(WorkflowError):m.deliver_v02(expected_version=m.read()['version'])
    assert len(m.read()['completion_evidence'])==2
    assert read_task(m,identity)[0]['attempt']==2
    # This approval is a fixture only, not a user's artistic acceptance.
    m.final_review_v02('approved',expected_version=m.read()['version'])
    result=m.deliver_v02(expected_version=m.read()['version'])
    assert result and m.read()['state']=='delivered'
    assert len(m.read()['visual_tasks'])==4
    assert all(t['status']=='accepted' for t in m.read()['visual_tasks'].values())
