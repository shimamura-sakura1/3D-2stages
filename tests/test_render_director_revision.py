"""PNG/receipt fixtures exercise the production gates, not artistic judgement."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from runtime.errors import WorkflowError
from runtime.io import load_data, sha256
from runtime.visual_planning import current_documents
from tests.test_render_director import inputs
from tests.test_v02_critic import review_for, snapshot
from tests.test_v02_preview import png


def rendered(tmp_path):
    manager,plans,scene,context,d = inputs(tmp_path)
    manager.submit_scene_plans(plans,render_direction=d,scene_context=scene,expected_version=manager.read()['version'])
    from runtime.scene_production import prepare_scene,complete_setup
    setup=prepare_scene(manager);packet=load_data(setup['packet'])
    out=Path(packet['outputs']['setup']);out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(Path(__file__).resolve().parents[1]/'styles/industrial_acg_v1/calibration/calibration.blend',out)
    Path(packet['outputs']['receipt']).write_text(json.dumps({'status':'setup_complete','build_id':packet['build_id'],
        'inputs_digest':packet['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(out)}))
    complete_setup(manager,setup['packet'],setup['sha256'])
    from runtime.preview_renderer import PreviewRenderer
    renderer=PreviewRenderer(manager);job=renderer.prepare();packet=load_data(job['packet'])
    image=Path(packet['outputs']['preview']);image.parent.mkdir(parents=True,exist_ok=True)
    dimensions=packet['plans']['render_plan']['preview'];image.write_bytes(png(dimensions['width'],dimensions['height']))
    Path(job['receipt']).write_text(json.dumps({'intent_sha256':job['intent_sha256'],'packet_sha256':job['sha256'],
        'build_id':job['build_id'],'pass_id':job['pass_id'],'inputs_digest':packet['inputs_digest'],
        'render_success':True,'error':None,'image_sha256':sha256(image),'timestamp':'2026-09-18T00:00:00+00:00','geometry_digest':'1'*64}))
    metadata=renderer.complete(job['job'])
    review={'schema_version':'1.0','render_id':metadata['document_id'],'project_id':d['project_id'],'scene_version':1,
            'direction_id':d['direction_id'],'direction_revision':0,'render_sha256':metadata['image']['sha256'],
            'findings':[{'id':'f1','category':'camera','severity':'medium','observation':'Fixture observation',
                         'evidence':'Fixture PNG','confidence':'medium'}],
            'recommended_changes':{'camera':{'azimuth_delta_deg':5}},'preserve':['approved_geometry'],
            'limitations':['Synthetic image; no visual evaluation']}
    production_review=review_for(manager,metadata)
    production_review['recommended_actions']=[{'action':'camera_framing','scope':'camera','magnitude':'small','reason':'Fixture framing'}]
    revision={'schema_version':'0.2','project_id':d['project_id'],'scene_version':1,'document_id':'rev_01',
              'revision':0,'based_on_review_id':production_review['document_id'],'render_metadata_id':metadata['document_id'],
              'pass_index':1,'max_preview_passes':3,
              'actions':[{'action':'camera_framing','scope':'camera','direction':'increase','amount':'small'}]}
    return manager,scene,d,review,production_review,revision


def test_review_refine_provenance_and_preserved_geometry(tmp_path):
    m,scene,d,review,production_review,revision=rendered(tmp_path)
    from runtime.render_context_builder import project_context
    context=project_context(m,scene,review=True)
    assert context['previous']['render']['render_id']==review['render_id']
    state=m.read();m.submit_render_review(production_review,director_review=review,expected_version=state['version'])
    new=copy.deepcopy(d);new['revision']=1;new['camera']['azimuth_deg']+=5;new['changed_fields']=['camera.azimuth_deg']
    files=snapshot(m)
    result=m.apply_visual_revision(revision,render_direction=new,expected_version=m.read()['version'])
    assert result['state']=='render_pending' and result['render_direction']['revision']==1
    assert result['geometry_assets']==state['geometry_assets'] and result['approvals']==state['approvals']
    assert len(result['render_direction']['history'])==1
    for path,value in files.items():
        if path!='manifest.yaml':assert (m.root/path).read_bytes()==value
    from runtime.scene_production import prepare_scene
    packet=load_data(prepare_scene(m)['packet'])
    assert packet['plans']['render_plan']['render_direction']['revision']==1
    from runtime.visual_delivery import formal_files
    assert any(x['path'].startswith('.render_direction/history/') for x in formal_files(m,result))
    previous=project_context(m,scene)['previous']
    assert previous['direction']==new and previous['review'] is None


@pytest.mark.parametrize('problem',['preserve','unreviewed','revision','geometry','png','review_only','plan_only','bounds','provenance','budget'])
def test_refinement_rejection_is_atomic(tmp_path,problem):
    m,scene,d,review,production_review,revision=rendered(tmp_path)
    if problem=='preserve':review['preserve'].append('camera')
    m.submit_render_review(production_review,director_review=review,expected_version=m.read()['version'])
    new=copy.deepcopy(d);new['revision']=1;new['camera']['azimuth_deg']+=5;new['changed_fields']=['camera.azimuth_deg']
    if problem=='preserve':new['preserve'].append('camera')
    if problem=='unreviewed':new['lighting']['fill']['ratio_to_key']=.8;new['changed_fields'].append('lighting.fill.ratio_to_key')
    if problem=='revision':new['revision']=3
    if problem=='geometry':new['geometry']={'scale':[2,2,2]}
    if problem=='png':
        metadata=current_documents(m,m.read(),('render_metadata',))['render_metadata']
        (m.root/metadata['image']['path']).write_bytes(b'changed')
    if problem=='review_only':new=review
    if problem=='plan_only':m.configure_visual('plan_only',expected_version=m.read()['version'])
    if problem=='bounds':new['camera']['azimuth_deg']+=40
    if problem=='provenance':(m.root/m.read()['render_direction']['artifact_path']).write_text('{}')
    if problem=='budget':revision['max_preview_passes']=1
    before=snapshot(m)
    with pytest.raises(WorkflowError):m.apply_visual_revision(revision,render_direction=new,expected_version=m.read()['version'])
    assert snapshot(m)==before


def test_review_wrong_png_or_direction_cannot_mutate(tmp_path):
    m,scene,d,review,production_review,revision=rendered(tmp_path)
    before=snapshot(m)
    for field,value in [('render_sha256','0'*64),('direction_revision',7)]:
        bad=copy.deepcopy(review);bad[field]=value
        with pytest.raises(WorkflowError):m.submit_render_review(production_review,director_review=bad,expected_version=m.read()['version'])
        assert snapshot(m)==before
