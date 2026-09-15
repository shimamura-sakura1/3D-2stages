"""Refinement behavior; temporary Blender headers are validation doubles only."""
import copy
import json
import shutil
from pathlib import Path
import pytest
import yaml
from runtime.errors import WorkflowError
from runtime.style_registry import StyleRegistry, CLASSES
from runtime.style_resolver import resolve_material
from runtime.scene_production import prepare_scene, verify_packet
from runtime.io import load_data
from runtime.manifest_manager import ManifestManager
from tests.test_v02_planning import proposal, cli, ROOT
from tests.test_v02_geometry import executor, request

VERSION = '1.1.0'
DIMENSIONS = {'geometry','surface','palette','roughness','weathering','lighting','fog','depth','composition','emissive','detail_density'}

@pytest.fixture
def registry(tmp_path, monkeypatch):
    folder=tmp_path/'styles'
    shutil.copytree(ROOT/'styles',folder)
    refined=folder/'industrial_acg_v1/versions/1.1.0'
    assert (refined/'profile.yaml').is_file(), 'Missing explicitly versioned refinement'
    # These bytes test deterministic resource checks, never Blender execution.
    for rel in ('materials/library.blend','calibration/calibration.blend'):
        p=refined/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'BLENDER validation double')
    class LocalRegistry(StyleRegistry):
        def __init__(self): super().__init__(folder)
    for module in ('runtime.style_resolver','runtime.visual_planning','runtime.scene_production','runtime.visual_review'):
        monkeypatch.setattr(module+'.StyleRegistry',LocalRegistry)
    return LocalRegistry()

def test_version_isolation_and_signature_consumption(registry):
    old=registry.load('industrial_acg_v1')
    new=registry.load('industrial_acg_v1',version=VERSION)
    assert old['version']=='1.0.0' and set(old['materials']['materials'])==CLASSES
    assert set(new['signature']['dimensions'])==DIMENSIONS
    assert set(new['materials']['materials'])==CLASSES|{'vegetation'}
    assert Path(old['root'])!=Path(new['root'])
    source=load_data(Path(new['root'])/'materials/definitions.yaml')['materials']
    sig=new['signature']['dimensions']
    resolved=resolve_material('industrial_acg_v1','painted_metal','clean',registry=registry,version=VERSION)
    assert resolved['profile_version']==VERSION
    assert resolved['parameters']['base_color']==sig['palette']['painted_metal']
    assert resolved['parameters']['bump_distance']==source['painted_metal']['bump_distance']*sig['surface']['bump_scale']
    assert resolved['parameters']['noise_scale']==source['painted_metal']['noise_scale']*sig['detail_density']['noise_scale']
    assert resolved['parameters']['roughness']==pytest.approx(source['painted_metal']['roughness']+sig['roughness']['offset'])
    raw=load_data(Path(new['root'])/'lighting/overcast.yaml')
    assert new['lighting']['key_energy']==raw['key_energy']*sig['lighting']['key_scale']
    assert new['lighting']['key_energy']/new['lighting']['fill_energy']>3
    assert new['atmosphere']['density']==load_data(Path(new['root'])/'atmosphere/default.yaml')['density']*sig['fog']['density_scale']
    assert new['signature']['reviewed_by']=='Codex'
    assert new['signature']['review_status']=='design_reviewed'

@pytest.mark.parametrize('version',['9.0.0','../1.0.0','/tmp/escape','C:\\escape','',True])
def test_unknown_and_escaping_versions_reject(version):
    with pytest.raises(WorkflowError):StyleRegistry().load('industrial_acg_v1',version=version,require_resources=False)

@pytest.mark.parametrize('problem',['missing_dimension','nan','boolean','range','palette','component_path','lighting','material','resource','condition_boolean','camera_nan','color_infinite','render_size'])
def test_malformed_refinement_rejects(registry,problem):
    root=Path(registry.load('industrial_acg_v1',version=VERSION)['root'])
    path=root/'style_signature.yaml';data=load_data(path)
    if problem=='missing_dimension':data['dimensions'].pop('fog')
    if problem=='nan':data['dimensions']['surface']['bump_scale']=float('nan')
    if problem=='boolean':data['dimensions']['roughness']['offset']=True
    if problem=='range':data['dimensions']['lighting']['key_scale']=100
    if problem=='palette':data['dimensions']['palette']['concrete']=[1,2,3]
    if problem=='component_path':
        path=root/'profile.yaml';data=load_data(path);data['components']['signature']='../profile.yaml'
    if problem=='lighting':
        path=root/'lighting/overcast.yaml';data=load_data(path);data['key_energy']=float('inf')
    if problem=='material':
        path=root/'materials/definitions.yaml';data=load_data(path);data['materials']['concrete']['roughness']=True
    if problem=='condition_boolean':
        path=root/'materials/definitions.yaml';data=load_data(path);data['conditions']['clean']['roughness_add']=False
    if problem=='camera_nan':
        path=root/'camera/environment.yaml';data=load_data(path);data['focal_length_mm']=float('nan')
    if problem=='color_infinite':
        path=root/'color/default.yaml';data=load_data(path);data['exposure']=float('inf')
    if problem=='render_size':
        path=root/'render/preview.yaml';data=load_data(path);data['width']=-1
    if problem=='resource':
        (root/'materials/library.blend').unlink()
    else:path.write_text(yaml.safe_dump(data))
    with pytest.raises(WorkflowError):registry.load('industrial_acg_v1',version=VERSION)

def refined_scene(tmp_path,registry,version=VERSION):
    root,docs=proposal(tmp_path);docs['style_assignment']['profile_version']=version
    m=ManifestManager(root);state=m.submit_visual_plan(docs,expected_version=0)
    state=m.review_visual('approved',expected_version=state['version'])
    m.configure_visual('full_pipeline',expected_version=state['version'])
    for name in ('platform','wall','machine'):
        q=request(name,None,'A')
        if name=='wall' and version==VERSION:q['material_class']='vegetation'
        executor(m).run(q)
    m.review_geometry('approved',expected_version=m.read()['version'])
    original=load_data(ROOT/'tests/fixtures/v02/industrial_station.json')['documents']
    plans={k:copy.deepcopy(original[k]) for k in ('blockout_plan','semantic_material_map','lookdev_plan','render_plan')}
    for p in plans['blockout_plan']['objects']:p.update(geometry_source='library',asset_id=p['object_id'])
    for p in plans['semantic_material_map']['mappings']:p.update(slot='body',surface_source=None)
    return m,plans

def test_prepared_packet_guards_signature_and_preserves_geometry(tmp_path,registry):
    m,plans=refined_scene(tmp_path,registry)
    m.submit_scene_plans(plans,expected_version=m.read()['version']);before=m.read()
    packet=prepare_scene(m);data=verify_packet(packet['packet'],packet['sha256'])
    assert m.read()==before and data['style']['version']==VERSION
    assert all(x['profile_version']==VERSION for x in data['materials'].values())
    assert data['geometry']=={k:v['versions'][-1] for k,v in before['geometry_assets'].items()}
    from runtime.visual_contracts import document_hash
    assert data['blockout_key']==document_hash({'geometry_fingerprint_format':2,'blockout':plans['blockout_plan'],'geometry':data['geometry']})
    signature=Path(data['style']['root'])/'style_signature.yaml'
    assert str(signature) in data['guard']
    signature.write_text(signature.read_text()+'\n# changed design\n')
    with pytest.raises(WorkflowError,match='changed'):verify_packet(packet['packet'],packet['sha256'])

def test_refined_camera_bounds_reject_atomically(tmp_path,registry):
    m,plans=refined_scene(tmp_path,registry);before=m.path.read_bytes()
    plans['render_plan']['camera']['focal_length_mm']=100
    with pytest.raises(WorkflowError,match='signature'):m.submit_scene_plans(plans,expected_version=m.read()['version'])
    assert m.path.read_bytes()==before

def test_legacy_packet_isolated_from_refined_resources(tmp_path,registry):
    m,plans=refined_scene(tmp_path,registry,version='1.0.0')
    m.submit_scene_plans(plans,expected_version=m.read()['version'])
    prepared=prepare_scene(m);packet=verify_packet(prepared['packet'],prepared['sha256'])
    selected=Path(packet['style']['root'])
    for relative in ('style_signature.yaml','materials/library.blend'):
        path=selected/'versions/1.1.0'/relative
        path.write_bytes(path.read_bytes()+b'\nchanged refined file\n')
    assert verify_packet(prepared['packet'],prepared['sha256'])==packet
    (selected/'materials/library.blend').write_bytes(b'BLENDER changed selected legacy resource')
    with pytest.raises(WorkflowError,match='changed'):verify_packet(prepared['packet'],prepared['sha256'])

def test_default_still_legacy_and_no_artistic_approval(tmp_path,registry):
    (ROOT/'docs/v02/style-refinement.md').read_text()
    legacy=resolve_material('industrial_acg_v1','concrete','clean',registry=registry)
    assert legacy['profile_version']=='1.0.0' and legacy['parameters']['roughness']==.82
    with pytest.raises(WorkflowError,match='Unknown material'):resolve_material('industrial_acg_v1','vegetation','clean',registry=registry)
    root,docs=proposal(tmp_path);docs['style_assignment']['profile_version']=VERSION
    result=cli('init',tmp_path/'legacy','--id','legacy','--brief','legacy')
    assert result.returncode==0 and json.loads(result.stdout)['mode']=='plan_only'
    m=ManifestManager(root).submit_visual_plan(docs,expected_version=0)
    assert m['state']=='visual_review_required' and m['approvals']==[]

def test_cli_selects_refined_version(registry):
    from runtime.cli import parser, execute
    args=parser().parse_args(['style-resolve','--version',VERSION,'--material','vegetation','--condition','clean'])
    value=execute(args)
    assert value['profile_version']==VERSION and value['material_class']=='vegetation'

def test_review_context_uses_selected_version_rubric(tmp_path,registry):
    from runtime.scene_production import complete_setup
    from runtime.preview_renderer import PreviewRenderer
    from runtime.visual_review import current_render_context
    from runtime.io import sha256
    from tests.test_v02_preview import receipt
    m,plans=refined_scene(tmp_path,registry)
    plans['render_plan']['preview']={'width':16,'height':16,'samples':1}
    m.submit_scene_plans(plans,expected_version=m.read()['version'])
    setup=prepare_scene(m);p=load_data(setup['packet']);out=Path(p['outputs']['setup'])
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b'BLENDER validation double')
    Path(p['outputs']['receipt']).write_text(json.dumps({'status':'setup_complete','build_id':p['build_id'],'inputs_digest':p['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(out)}))
    complete_setup(m,setup['packet'],setup['sha256'])
    renderer=PreviewRenderer(m);job=renderer.prepare();receipt(job);renderer.complete(job['job'])
    context=current_render_context(m)
    assert context['rubric']['profile_version']==VERSION
    assert 'vegetation' in context['rubric']['categories']['material_separation']
    assert m.read()['state']=='render_review_required'

@pytest.mark.parametrize('fail',[False,True])
def test_material_library_names_survive_live_collisions(monkeypatch,tmp_path,fail):
    """A bpy naming double exercises cleanup, never claims a real Blender write."""
    import runpy,sys,types
    names=[]
    class Material:
        def __init__(self,name):self._name='';names.append(self);self.name=name
        @property
        def name(self):return self._name
        @name.setter
        def name(self,name):
            used={m.name for m in names if m is not self};candidate=name;i=1
            while candidate in used:candidate=f'{name}.{i:03d}';i+=1
            self._name=candidate
    class Materials:
        def get(self,name):return next((m for m in names if m.name==name),None)
    original=Material('industrial_acg_v1.painted_metal')
    created=Material('industrial_acg_v1.painted_metal');created_name=created.name
    observed=[]
    def write(path,values,**kwargs):
        observed.extend(x.name for x in values)
        if fail:raise OSError('simulated library write failure')
    fake=types.ModuleType('bpy');fake.data=types.SimpleNamespace(materials=Materials(),libraries=types.SimpleNamespace(write=write))
    mathutils=types.ModuleType('mathutils');mathutils.Vector=object
    monkeypatch.setitem(sys.modules,'bpy',fake);monkeypatch.setitem(sys.modules,'mathutils',mathutils)
    worker=runpy.run_path(str(ROOT/'runtime/blender_style_worker.py'))
    assert callable(worker.get('write_material_library')), 'Missing collision-safe library writer'
    try:worker['write_material_library'](tmp_path/'library.blend',{'painted_metal':created},'industrial_acg_v1')
    except OSError:
        assert fail
    assert observed==['industrial_acg_v1.painted_metal']
    assert original.name=='industrial_acg_v1.painted_metal' and created.name==created_name
