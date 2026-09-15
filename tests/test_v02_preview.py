"""Metadata/gate tests use labeled worker receipts; real MCP rendering is separate evidence."""
import json,shutil,struct,zlib
from pathlib import Path
import pytest
from runtime.io import load_data,sha256
from runtime.errors import WorkflowError
from runtime.visual_contracts import document_hash
from tests.test_v02_production import scene_ready,ROOT
from tests.test_v02_planning import cli


def prepared_project(tmp_path):
    m,plans=scene_ready(tmp_path)
    plans['render_plan']['preview']={'width':16,'height':16,'samples':1}
    m.submit_scene_plans(plans,expected_version=m.read()['version'])
    from runtime.scene_production import prepare_scene,complete_setup
    setup=prepare_scene(m);p=load_data(setup['packet']);out=Path(p['outputs']['setup']);out.parent.mkdir(parents=True,exist_ok=True)
    # Explicit Blender receipt double, using a real blend container as fixture bytes.
    shutil.copy2(ROOT/'styles/industrial_acg_v1/calibration/calibration.blend',out)
    Path(p['outputs']['receipt']).write_text(json.dumps({'status':'setup_complete','build_id':p['build_id'],'inputs_digest':p['inputs_digest'],'geometry_before':'1'*64,'geometry_after':'1'*64,'blend_sha256':sha256(out)}))
    complete_setup(m,setup['packet'],setup['sha256'])
    return m

def png(width=16,height=16):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    raw=b''.join(b'\0'+b'\x40\x80\xa0\xff'*width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')

def receipt(job,success=True):
    intent=load_data(job['intent']);packet=load_data(job['packet'])
    image=Path(packet['outputs']['preview']);image.parent.mkdir(parents=True,exist_ok=True)
    if success:image.write_bytes(png())
    value={'intent_sha256':job['intent_sha256'],'packet_sha256':job['sha256'],'build_id':job['build_id'],'pass_id':job['pass_id'],'inputs_digest':packet['inputs_digest'],'render_success':success,'error':None if success else 'Simulated renderer failure','image_sha256':sha256(image) if success else None,'timestamp':'2026-09-14T00:00:00+00:00','geometry_digest':'1'*64}
    Path(job['receipt']).write_text(json.dumps(value));return value

def test_preview_success_repetition_and_no_approval(tmp_path):
    m=prepared_project(tmp_path)
    r=cli('preview-prepare',m.root);assert r.returncode==0,r.stderr
    job=json.loads(r.stdout);assert job['status']=='prepared' and job['backend']=='mcp' and job['pass_id']=='pass_00'
    packet=load_data(job['packet']);assert not Path(packet['outputs']['preview']).exists()
    before=m.read()['approvals'];receipt(job)
    r=cli('preview-complete',m.root,'--job',job['job']);assert r.returncode==0,r.stderr
    metadata=json.loads(r.stdout);assert metadata['render_success'] is True and 'visual_approved' not in metadata
    assert metadata['scene_version']==m.read()['scene_version'] and metadata['render_plan_hash']==document_hash(packet['plans']['render_plan'])
    assert m.read()['state']=='render_review_required' and m.read()['approvals']==before
    oldmeta=(m.root/'stage2/previews/pass_00/render_metadata.json').read_bytes();oldimage=Path(packet['outputs']['preview']).read_bytes()
    from runtime.preview_renderer import PreviewRenderer
    second=PreviewRenderer(m).prepare();assert second['pass_id']=='pass_01' and second['build_id']==job['build_id']
    receipt(second);PreviewRenderer(m).complete(second['job'])
    assert (m.root/'stage2/previews/pass_00/render_metadata.json').read_bytes()==oldmeta
    assert Path(packet['outputs']['preview']).read_bytes()==oldimage
    assert len(m.read()['artifacts']['render_metadata'])==2

@pytest.mark.parametrize('problem',['missing','corrupt','size','changed','receipt','packet','intent'])
def test_invalid_completion_is_atomic(tmp_path,problem):
    m=prepared_project(tmp_path)
    from runtime.preview_renderer import PreviewRenderer
    renderer=PreviewRenderer(m);job=renderer.prepare();r=receipt(job);p=load_data(job['packet']);image=Path(p['outputs']['preview'])
    if problem=='missing':image.unlink()
    if problem=='corrupt':image.write_bytes(b'\x89PNG\r\n\x1a\nbroken');r['image_sha256']=sha256(image)
    if problem=='size':image.write_bytes(png(32,16));r['image_sha256']=sha256(image)
    if problem=='changed':image.write_bytes(png(17,16))
    if problem=='receipt':r['pass_id']='pass_99'
    if problem=='packet':Path(job['packet']).write_text('{}')
    if problem=='intent':Path(job['intent']).write_text('{}')
    Path(job['receipt']).write_text(json.dumps(r));before=m.path.read_bytes()
    with pytest.raises(WorkflowError):renderer.complete(job['job'])
    assert m.path.read_bytes()==before and not (m.root/'stage2/previews/pass_00/render_metadata.json').exists()

def test_failed_render_is_recorded_without_image(tmp_path):
    m=prepared_project(tmp_path)
    from runtime.preview_renderer import PreviewRenderer
    renderer=PreviewRenderer(m);job=renderer.prepare();receipt(job,False);metadata=renderer.complete(job['job'])
    assert metadata['render_success'] is False and metadata['image'] is None and metadata['error']=='Simulated renderer failure'
    assert m.read()['state']=='render_pending' and all(a['scope']!='final' for a in m.read()['approvals'])
    assert renderer.prepare()['pass_id']=='pass_01'

def test_geometry_fingerprint_survives_signed_zero_serialization():
    from runtime.blender_operations import geometry_digest
    a=[{'matrix':[[1.0,-0.0,0.0]],'vertices':[[0.0,-0.0,2.0]]}]
    b=[{'matrix':[[1.0,0.0,0.0]],'vertices':[[0.0,0.0,2.0]]}]
    assert geometry_digest(a)==geometry_digest(b)
    b[0]['vertices'][0][2]=2.01
    assert geometry_digest(a)!=geometry_digest(b)

@pytest.mark.parametrize('target',['job','receipt'])
def test_nonobject_job_or_receipt_rejects_cleanly(tmp_path,target):
    m=prepared_project(tmp_path)
    from runtime.preview_renderer import PreviewRenderer
    renderer=PreviewRenderer(m);job=renderer.prepare();receipt(job)
    Path(job[target]).write_text('[]')
    with pytest.raises(WorkflowError):renderer.complete(job['job'])
