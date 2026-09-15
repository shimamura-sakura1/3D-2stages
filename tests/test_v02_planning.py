import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest
from runtime.planning import create_visual_project
from runtime.manifest_manager import ManifestManager
from runtime.errors import WorkflowError
from runtime.io import load_data

ROOT=Path(__file__).resolve().parents[1]
KINDS=('visual_brief','reference_board','scene_spec','style_assignment')

def cli(*args):
    return subprocess.run([sys.executable,str(ROOT/'runtime/cli.py'),*map(str,args)],capture_output=True,text=True)

def proposal(tmp_path):
    root=tmp_path/'project';create_visual_project(root,'industrial_station','Quiet industrial station')
    from runtime.reference_manager import import_reference
    source=tmp_path/'reference.svg';source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="teal"/></svg>')
    metadata={'kind':'user','creator':'test fixture','license':'unknown','license_verified':False,'attribution':'unverified fixture, planning only'}
    ref=import_reference(ManifestManager(root),source,'ref_material',['material_language'],metadata)
    original=json.loads((ROOT/'tests/fixtures/v02/industrial_station.json').read_text())['documents']
    docs={k:copy.deepcopy(original[k]) for k in KINDS}
    docs['reference_board']['references']=[ref]
    docs['style_assignment']['profile_version']='1.0.0'
    return root,docs

def test_submit_review_revision(tmp_path):
    root,docs=proposal(tmp_path);path=tmp_path/'proposal.json';path.write_text(json.dumps(docs))
    r=cli('stage0-submit',root,'--proposal',path,'--expected-version',0)
    assert r.returncode==0,r.stderr
    m=json.loads(r.stdout);assert m['state']=='visual_review_required' and m['approvals']==[] and m['mode']=='plan_only'
    old={k: (root/m['artifacts'][k][-1]['path']).read_bytes() for k in KINDS}
    r=cli('visual-review-v02',root,'--decision','rejected','--expected-version',m['version'])
    assert r.returncode==0,r.stderr
    m=json.loads(r.stdout);assert m['state']=='visual_planning'
    for d in docs.values():d['revision']=1
    docs['visual_brief']['mood']['primary']=['quiet','humid'];path.write_text(json.dumps(docs))
    r=cli('stage0-submit',root,'--proposal',path,'--expected-version',m['version']);assert r.returncode==0,r.stderr
    m=json.loads(r.stdout)
    for k in KINDS:
        assert len(m['artifacts'][k])==2
        assert (root/m['artifacts'][k][0]['path']).read_bytes()==old[k]
    r=cli('visual-review-v02',root,'--decision','approved','--expected-version',m['version']);assert r.returncode==0,r.stderr
    m=json.loads(r.stdout);assert m['state']=='visual_approved' and len(m['approvals'])==2
    assert len(m['approvals'][-1]['artifact_hashes'])==4
    assert not (root/'stage1').exists() and not (root/'stage2').exists()

@pytest.mark.parametrize('problem',['role','style_role','identity','focal','profile','reference','version','worker'])
def test_rejections_are_atomic(tmp_path,problem):
    root,docs=proposal(tmp_path);manager=ManifestManager(root);before=manager.path.read_bytes()
    expected=0
    if problem=='role':docs['reference_board']['references'][0]['roles']=['everything']
    if problem=='style_role':docs['style_assignment']['references'][0]['roles']=['lighting']
    if problem=='identity':docs['scene_spec']['scene_version']=9
    if problem=='focal':docs['scene_spec']['composition']['focal_subject']='absent'
    if problem=='profile':docs['style_assignment']['profile_version']='planned'
    if problem=='reference':(root/docs['reference_board']['references'][0]['path']).write_text('changed')
    if problem=='version':expected=1
    if problem=='worker':manager=ManifestManager(root,role='worker')
    with pytest.raises(WorkflowError):manager.submit_visual_plan(docs,expected_version=expected)
    assert manager.path.read_bytes()==before
    assert not (root/'stage0').exists()

def test_changed_document_cannot_be_approved(tmp_path):
    root,docs=proposal(tmp_path);manager=ManifestManager(root)
    m=manager.submit_visual_plan(docs,expected_version=0)
    path=root/m['artifacts']['scene_spec'][-1]['path'];x=load_data(path);x['scene_type']='altered';path.write_text(json.dumps(x))
    before=manager.path.read_bytes()
    with pytest.raises(WorkflowError,match='hash'):manager.review_visual('approved',expected_version=m['version'])
    assert manager.path.read_bytes()==before

def test_reference_bytes_roles_and_metadata_survive_import(tmp_path):
    root,docs=proposal(tmp_path)
    ref=docs['reference_board']['references'][0]
    assert (root/ref['path']).read_bytes()==(tmp_path/'reference.svg').read_bytes()
    assert ref['source']=={'kind':'user','creator':'test fixture','license':'unknown','license_verified':False,'attribution':'unverified fixture, planning only'}
    assert ref['roles']==['material_language']
    m=ManifestManager(root).submit_visual_plan(docs,expected_version=0)
    recorded=load_data(root/m['artifacts']['reference_board'][-1]['path'])
    assert recorded['references']==[ref]
