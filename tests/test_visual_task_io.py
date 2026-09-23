import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_runner_checks_real_valid_and_invalid_requests():
    for value,code in [({'command':'capabilities'},0),({'command':'unknown'},2)]:
        r=subprocess.run([sys.executable,str(ROOT/'runtime/visual_tasks.py')],input=json.dumps(value),
                         text=True,capture_output=True,cwd=ROOT)
        assert r.returncode==code,r.stderr
        data=json.loads(r.stdout if code==0 else r.stderr)
        if code==0:assert data['operations']==['create_direction','review_render','refine_direction']
        else:assert data['error_code']=='INVALID_TASK'
