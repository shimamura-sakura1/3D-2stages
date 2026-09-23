import json
import subprocess
import sys
from pathlib import Path

def test_consumer_can_run_local_task_contract_without_optional_installations(tmp_path):
    from scripts.export_production import export_production
    root=Path(__file__).resolve().parents[1];out=export_production(root,tmp_path/'consumer')
    interface=json.loads((out/'interface.json').read_text())
    assert not interface.get('external_dependencies')
    assert (out/'prompts/visual_task_direction.md').is_file()
    assert not (out/'tests').exists() and not (out/'docs/governance').exists()
    result=subprocess.run([sys.executable,str(out/'runtime/visual_tasks.py')],input='{"command":"capabilities"}',capture_output=True,text=True,cwd=out)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['execution']=='agent_required'
