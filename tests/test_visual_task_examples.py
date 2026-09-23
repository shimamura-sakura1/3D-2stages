import json
from tests.visual_task_helpers import setup
from tests.test_v02_planning import cli

def test_documented_prepare_and_status_entrypoints(tmp_path):
    m,spec=setup(tmp_path);path=tmp_path/'task.json';path.write_text(json.dumps(spec),encoding='utf-8')
    r=cli('visual-task-prepare',m.root,'--request',path,'--expected-version',m.read()['version'])
    assert r.returncode==0,r.stderr
    task=json.loads(r.stdout);before=m.path.read_bytes()
    r=cli('visual-task-status',m.root,'--task-id',task['task_id'])
    assert r.returncode==0 and json.loads(r.stdout)['status']=='prepared'
    assert m.path.read_bytes()==before
