from tests.visual_task_helpers import setup

def test_inputs_are_separate_and_style_sources_anchored(tmp_path):
    from runtime.visual_tasks import prepare,read_task
    m,spec=setup(tmp_path);task=prepare(m,spec,expected_version=m.read()['version'])
    _,_,context,values=read_task(m,task['task_id'])
    assert 'Production facts:' not in values['scene_context']['scene_summary']
    assert values['style_context']['style_id']=='industrial_acg_v1'
    assert context['style_hashes'] and any(p.startswith('semantic/') for p in context['style_hashes'])
    assert values['visual_brief']['avoid']==['uniform_gloss']

def test_new_measured_scene_supports_unclassified_scene_type(tmp_path):
    from runtime.render_context_builder import build_scene_context
    from runtime.visual_planning import current_documents
    m,spec=setup(tmp_path);docs=current_documents(m,m.read())
    boxes={x['object_id']:x['bounds'] for x in [spec['scene_context']['scene']['primary_subject'],*spec['scene_context']['scene']['secondary_subjects']]}
    result=build_scene_context(m.read(),docs['scene_spec'],boxes,blockout_plan=spec['plans']['blockout_plan'],ground_z=0,
        environment_summary='Forest',scene_type='forest',visual_task=True)
    assert result['scene']['scene_type']=='forest'
