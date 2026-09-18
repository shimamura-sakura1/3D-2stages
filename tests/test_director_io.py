"""Real subprocess I/O for compilation, with no render or approval claims."""
import json
import subprocess
import sys
from pathlib import Path
from runtime.validators import validate_contract

ROOT=Path(__file__).resolve().parents[1]


def test_valid_compiler_io(tmp_path):
    payload=(ROOT/'tests/fixtures/render_director/compile.json').read_text(encoding='utf-8')
    output=tmp_path/'audit'
    result=subprocess.run([sys.executable,str(ROOT/'runtime/render_direction_adapter.py'),'--audit-dir',str(output)],
        input=payload,capture_output=True,text=True,cwd=ROOT,timeout=60)
    assert result.returncode==0,result.stderr
    compiled=json.loads(result.stdout);validate_contract('directed_plans',compiled)
    for name,schema in [('context','render_context'),('direction','render_direction'),('review','render_review'),('scene_context','scene_context')]:
        value=json.loads((output/(name+'.json')).read_text());validate_contract(schema,value)
        assert value==json.loads(payload)[name]


def test_invalid_compiler_io_rejects_before_output(tmp_path):
    output=tmp_path/'audit'
    result=subprocess.run([sys.executable,str(ROOT/'runtime/render_direction_adapter.py'),'--audit-dir',str(output)],
        input='{}',capture_output=True,text=True,cwd=ROOT,timeout=60)
    assert result.returncode==2 and not output.exists() and not result.stdout
    validate_contract('error',json.loads(result.stderr))
