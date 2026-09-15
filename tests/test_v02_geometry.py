import copy
import json
from pathlib import Path
import pytest
from runtime.manifest_manager import ManifestManager
from runtime.planning import new_task
from runtime.errors import WorkflowError
from providers.local_library import LocalLibraryProvider
from runtime.style_resolver import resolve_material
from tests.test_v02_planning import proposal,cli,ROOT


def ready(tmp_path,approve=True):
    root,docs=proposal(tmp_path);m=ManifestManager(root);v=m.submit_visual_plan(docs,expected_version=0)
    if approve:v=m.review_visual('approved',expected_version=v['version'])
    m.configure_visual('full_pipeline',expected_version=v['version'])
    return m

def request(asset='platform',primitive='platform',preferred='auto'):
    task=new_task(asset);task['search']['keywords']=['bench'];task['hy3d']['enabled']=True
    return {'task':task,'primitive':primitive,'preferred_route':preferred,'modification':None,'material_class':'painted_metal','condition':'lightly_weathered','reference_ids':[]}

class GeneratedDouble:
    kind='generated_test_double'
    config={'output_source':{'provider':'generated_test_double','asset_id':'machine','original_url':'local:fixture','creator':'test author','license':'cc0','license_verified':True,'attribution_required':False,'modification_allowed':True}}
    calls=0
    def generate_shape(self,**kwargs):
        self.calls+=1
        p=Path(kwargs['output_dir'])/'asset.obj';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 4 2\nf 2 4 3\nf 3 4 1\n')
        return p

def executor(m,gateway=None):
    from runtime.geometry_acquisition import GeometryAcquisition
    return GeometryAcquisition(m,{'local_library':LocalLibraryProvider(ROOT/'examples/library/catalog.yaml')},gateway)

@pytest.mark.parametrize('primitive',['floor','wall','platform','column','rail','pipe'])
def test_procedural_priority(tmp_path,primitive):
    m=ready(tmp_path);r=executor(m).run(request(primitive=primitive))
    assert r['route']=='D' and r['geometry']['primitive']==primitive
    assert r['recipe']['searched_providers']==['local_library']
    assert r['geometry']['model'] is None and r['surface_semantics']['material_class']=='painted_metal'
    assert m.read()['state']=='geometry_pending'
    assert m.read()['geometry_assets']['platform']['status']=='review_required'

def test_library_modified_generated_share_material(tmp_path):
    m=ready(tmp_path);ex=executor(m,GeneratedDouble())
    a=ex.run(request('platform',None,'A'))
    bq=request('wall',None,'B');bq['modification']={'scale':[1,2,1]};b=ex.run(bq)
    cq=request('machine',None,'C');cq['task']['search']['keywords']=['unique machine'];c=ex.run(cq)
    assert [a['route'],b['route'],c['route']]==['A','B','C']
    assert b['recipe']['modification']=={'scale':[1,2,1]}
    assert c['provenance']['provider']=='generated_test_double'
    assert all((m.root/r['geometry']['model']).is_file() for r in (a,b,c))
    assert len({json.dumps(resolve_material('industrial_acg_v1',**r['surface_semantics'])['parameters'],sort_keys=True) for r in (a,b,c)})==1
    state=m.read();assert state['state']=='geometry_review_required'
    r=cli('geometry-review-v02',m.root,'--decision','approved','--expected-version',state['version'])
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)['state']=='geometry_approved'

@pytest.mark.parametrize('problem',['unapproved','plan_only','provider','primitive','modification','reference_rights','output_rights'])
def test_rejects_before_generation(tmp_path,problem):
    m=ready(tmp_path,approve=problem!='unapproved');gateway=GeneratedDouble();gateway.config=copy.deepcopy(gateway.config)
    ex=executor(m,gateway);q=request('machine',None,'C');q['task']['search']['keywords']=['machine']
    if problem=='plan_only':m.configure_visual('plan_only',expected_version=m.read()['version'])
    if problem=='provider':ex.providers={}
    if problem=='primitive':q['primitive']='roof'
    if problem=='modification':q.update(preferred_route='B',modification={'scale':[0,1,1]})
    if problem=='reference_rights':q['reference_ids']=['ref_material']
    if problem=='output_rights':gateway.config['output_source']['license_verified']=False
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):ex.run(q)
    assert gateway.calls==0 and m.path.read_bytes()==before

def test_rework_preserves_and_tamper_blocks_review(tmp_path):
    m=ready(tmp_path);ex=executor(m,GeneratedDouble())
    for name in ('platform','wall','machine'):ex.run(request(name,None,'A'))
    first=m.read()['geometry_assets']['platform']['versions'][0];raw=(m.root/first['geometry']['model']).read_bytes()
    state=m.review_geometry('rejected',expected_version=m.read()['version'])
    ex.run(request('platform',None,'A'))
    versions=m.read()['geometry_assets']['platform']['versions'];assert len(versions)==2
    assert (m.root/versions[0]['geometry']['model']).read_bytes()==raw
    (m.root/versions[-1]['geometry']['model']).write_text('tampered')
    before=m.path.read_bytes()
    with pytest.raises(WorkflowError):m.review_geometry('approved',expected_version=m.read()['version'])
    assert m.path.read_bytes()==before
