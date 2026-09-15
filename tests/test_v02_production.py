import copy,json
from pathlib import Path
import pytest
from runtime.errors import WorkflowError
from runtime.io import load_data
from tests.test_v02_geometry import ready,executor,request,ROOT
from tests.test_v02_planning import cli

KINDS=('blockout_plan','semantic_material_map','lookdev_plan','render_plan')

def scene_ready(tmp_path):
    m=ready(tmp_path);ex=executor(m)
    for name in ('platform','wall','machine'):ex.run(request(name,None,'A'))
    m.review_geometry('approved',expected_version=m.read()['version'])
    original=json.loads((ROOT/'tests/fixtures/v02/industrial_station.json').read_text())['documents']
    plans={k:copy.deepcopy(original[k]) for k in KINDS}
    for p in plans['blockout_plan']['objects']:p.update(geometry_source='library',asset_id=p['object_id'])
    for p in plans['semantic_material_map']['mappings']:p.update(slot='body',surface_source=None)
    return m,plans

def test_split_prepare_default_and_visual_revision(tmp_path):
    m,plans=scene_ready(tmp_path);p=tmp_path/'plans.json';p.write_text(json.dumps(plans))
    r=cli('scene-plans-submit',m.root,'--plans',p,'--expected-version',m.read()['version']);assert r.returncode==0,r.stderr
    state=json.loads(r.stdout);assert state['state']=='blockout_pending'
    r=cli('scene-prepare',m.root);assert r.returncode==0,r.stderr
    packet=json.loads(r.stdout);assert packet['status']=='prepared' and packet['backend']=='mcp'
    from runtime.scene_production import verify_packet
    data=verify_packet(packet['packet'],packet['sha256'])
    assert data['operations']==['asset.import','asset.place','material.assign_semantic','lighting.apply_profile','atmosphere.apply_profile','camera.apply_profile','render.preview']
    assert m.read()==state
    for k in KINDS:
        if k!='blockout_plan':plans[k]['revision']+=1
    plans['lookdev_plan']['lighting']['intensity']='high'
    plans['render_plan']['camera']['location'][0]+=2
    plans['semantic_material_map']['mappings'][0]['material_class']='bare_metal'
    m.submit_scene_plans(plans,expected_version=state['version'])
    from runtime.scene_production import prepare_scene
    second=prepare_scene(m)
    assert second['build_id']==packet['build_id'] and second['sha256']!=packet['sha256']
    assert len(m.read()['artifacts']['blockout_plan'])==1
    assert len(m.read()['artifacts']['lookdev_plan'])==2
    with pytest.raises(WorkflowError,match='changed'):verify_packet(packet['packet'],packet['sha256'])

@pytest.mark.parametrize('problem',['parent','coverage','material','slot','surface','camera','style','source','scale'])
def test_invalid_plans_atomic(tmp_path,problem):
    m,plans=scene_ready(tmp_path)
    if problem=='parent':plans['blockout_plan']['objects'][0]['parent']='platform'
    if problem=='coverage':plans['blockout_plan']['objects'].pop()
    if problem=='material':plans['semantic_material_map']['mappings'][0]['object_id']='absent'
    if problem=='slot':plans['semantic_material_map']['mappings'][0]['slot']='unknown'
    if problem=='surface':plans['semantic_material_map']['mappings'][0]['surface_source']='absent.png'
    if problem=='camera':plans['render_plan']['camera']['location']=plans['render_plan']['camera']['target']
    if problem=='style':plans['lookdev_plan']['lighting']['profile']='unknown'
    if problem=='source':plans['blockout_plan']['objects'][0]['geometry_source']='generated'
    if problem=='scale':plans['blockout_plan']['objects'][0]['transform']['scale']=[0,1,1]
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):m.submit_scene_plans(plans,expected_version=m.read()['version'])
    assert m.path.read_bytes()==before and not (m.root/'stage2').exists()

def test_unapproved_tampered_and_unknown_operation(tmp_path):
    m,plans=scene_ready(tmp_path)
    path=m.root/m.read()['geometry_assets']['platform']['versions'][-1]['geometry']['model'];path.write_text('changed')
    with pytest.raises(WorkflowError):m.submit_scene_plans(plans,expected_version=m.read()['version'])
    from runtime.blender_operations import run
    with pytest.raises(ValueError,match='Unknown'):run('missing.json','0'*64,'arbitrary.bpy')

def test_receipt_missing_cannot_complete(tmp_path):
    m,plans=scene_ready(tmp_path);m.submit_scene_plans(plans,expected_version=m.read()['version'])
    from runtime.scene_production import prepare_scene,complete_setup
    p=prepare_scene(m);before=m.path.read_bytes()
    with pytest.raises(WorkflowError,match='receipt'):complete_setup(m,p['packet'],p['sha256'])
    assert m.path.read_bytes()==before
