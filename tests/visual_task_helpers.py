"""New task fixtures; bounds and PNGs here are test doubles, not live evidence."""
import copy
from tests.test_render_director import inputs


def setup(tmp_path):
    manager, plans, scene, _, _ = inputs(tmp_path)
    return manager, {'operation': 'create_direction', 'scene_context': scene, 'plans': plans}


def direction():
    return {'schema_version':'1.0','direction_id':'camera / 任意 ID','revision':0,'parent_direction_id':None,
        'camera':{'subject_ref':'machine','shot_type':'three quarter','azimuth_deg':35,'elevation_deg':25,
            'focal_length_mm':40,'subject_coverage':.55,'target':{'mode':'subject_center','offset_normalized':[0,0,0]}},
        'composition':dict(hierarchy='primary machine',subject_placement='center',foreground='platform',
            midground='machine',background='wall',depth_layering='three layers',negative_space='above',
            silhouette='clear',scale_cues=['wall']),
        'lighting':{'key':{'reference_frame':'camera_subject','azimuth_deg':135,'elevation_deg':40,'softness':'broad soft key'},
            'fill':{'ratio_to_key':.25},'silhouette_separation':'clear','subject_background_separation':'clear','hierarchy':'key dominates'},
        'atmosphere':dict(depth='layered',fog='a little haze',contrast='readable',background_separation='subtle',emissive_role='none'),
        'preserve':['approved_geometry'],'avoid':['uniform_gloss']}


def execution():
    return {'softness':'large','fog_amount':'subtle','reason':'Broad soft source and subtle haze implement the authored direction.'}


def candidate(manager, spec):
    from runtime.visual_tasks import prepare, start, submit
    task=prepare(manager,spec,expected_version=manager.read()['version'])
    start(manager,task['task_id'],expected_version=manager.read()['version'])
    submit(manager,task['task_id'],direction(),execution=execution(),expected_version=manager.read()['version'])
    return task


def adopted(tmp_path):
    m,spec=setup(tmp_path);task=candidate(m,spec)
    m.submit_scene_plans(spec['plans'],visual_task=task['task_id'],expected_version=m.read()['version'])
    return m,spec,task


def render_fixture(m):
    """Synthetic worker receipts and PNG for production-boundary tests only."""
    import json,shutil
    from pathlib import Path
    from runtime.scene_production import prepare_scene,complete_setup
    from runtime.io import load_data,sha256
    if m.read()['state']=='blockout_pending':
        job=prepare_scene(m);packet=load_data(job['packet']);out=Path(packet['outputs']['setup']);out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(__file__).resolve().parents[1]/'styles/industrial_acg_v1/calibration/calibration.blend',out)
        Path(packet['outputs']['receipt']).write_text(json.dumps({'status':'setup_complete','build_id':packet['build_id'],
            'inputs_digest':packet['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(out)}))
        complete_setup(m,job['packet'],job['sha256'])
    from runtime.preview_renderer import PreviewRenderer
    from tests.test_v02_preview import png
    renderer=PreviewRenderer(m);job=renderer.prepare();packet=load_data(job['packet'])
    calibration=Path(__file__).resolve().parents[1]/'styles/industrial_acg_v1/calibration/calibration.blend'
    for key in ('blockout','setup'):
        out=Path(packet['outputs'][key]);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(calibration,out)
    Path(packet['outputs']['receipt']).write_text(json.dumps({'status':'setup_complete','build_id':packet['build_id'],
        'inputs_digest':packet['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(packet['outputs']['setup'])}))
    image=Path(packet['outputs']['preview']);image.parent.mkdir(parents=True,exist_ok=True);size=packet['plans']['render_plan']['preview']
    image.write_bytes(png(size['width'],size['height']))
    Path(job['receipt']).write_text(json.dumps({'intent_sha256':job['intent_sha256'],'packet_sha256':job['sha256'],
        'build_id':job['build_id'],'pass_id':job['pass_id'],'inputs_digest':packet['inputs_digest'],
        'render_success':True,'error':None,'image_sha256':sha256(image),'timestamp':'2026-09-19T00:00:00+00:00','geometry_digest':'1'*64}))
    return renderer.complete(job['job'])


def reviewed(tmp_path,change=True):
    from runtime.visual_tasks import prepare,start,submit
    from tests.test_v02_critic import review_for
    m,spec,task=adopted(tmp_path);metadata=render_fixture(m)
    t=prepare(m,{'operation':'review_render'},expected_version=m.read()['version'])
    start(m,t['task_id'],expected_version=m.read()['version'])
    report={'schema_version':'1.0','review_id':'review-0','direction_id':direction()['direction_id'],'direction_revision':0,
        'render_path':'inputs/render/preview.png','findings':[{'category':'camera','severity':'minor','observation':'Synthetic framing example'}] if change else [],
        'successful_decisions':[{'category':'lighting','observation':'Synthetic preserved light'}],
        'recommended_changes':{'camera':{'azimuth':'increase slightly'} if change else {},'composition':{},'lighting':{},'atmosphere':{}},'preserve':['approved_geometry']}
    submit(m,t['task_id'],report,expected_version=m.read()['version'])
    production=review_for(m,metadata,'revision_required' if change else 'final_review_required')
    production['recommended_actions']=[{'action':'camera_framing','scope':'camera','magnitude':'small','reason':'Synthetic framing'}] if change else []
    m.submit_render_review(production,visual_task=t['task_id'],expected_version=m.read()['version'])
    revision={'schema_version':'0.2','project_id':m.read()['project_id'],'scene_version':1,'document_id':'revision_0','revision':0,
        'based_on_review_id':production['document_id'],'render_metadata_id':metadata['document_id'],'pass_index':1,'max_preview_passes':3,
        'actions':[{'action':'camera_framing','scope':'camera','direction':'increase','amount':'small'}]}
    return m,spec,task,revision
