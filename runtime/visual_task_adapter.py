"""Optional file-task adapter. The calling Agent, not Python, reasons visually."""
import json
import os
import subprocess
import sys
from pathlib import Path

from runtime.io import inside,sha256
from runtime.validators import validate_contract
from runtime.visual_contracts import require
from runtime.errors import WorkflowError

SCHEMA_NAMES={'request':'request','visual_brief':'brief','scene_context':'scene','style_context':'style',
    'knowledge_context':'knowledge','scene_state':'scene_state','references':'references',
    'render_direction':'direction','render_review':'review','render_error':'error'}
ROOT=Path(__file__).resolve().parents[1]


def _runtime_ready(executable):
    try:
        result=subprocess.run([executable,'-B','-c','import jsonschema; import PIL'],capture_output=True,timeout=10)
        return result.returncode==0
    except (OSError,subprocess.TimeoutExpired):return False


def select_executor(config=None):
    config=config or {};validate_contract('visual_execution_config',config)
    mode=config.get('mode','auto')
    local={'executor':'main','reason':'Built-in visual reasoning','transport':'local_agent','mode':mode}
    if mode=='main':return local
    home=config.get('home');reason='Optional implementation is not configured'
    if home:
        root=Path(home).expanduser().resolve()
        try:
            files=['SKILL.md','runtime/load_task.py','runtime/publish_result.py']
            for name,target in SCHEMA_NAMES.items():
                relative=f'contracts/{name}.schema.json';files.append(relative)
                raw=inside(root,relative).read_text(encoding='utf-8')
                for a,b in SCHEMA_NAMES.items():raw=raw.replace(a+'.schema.json','visual_task_'+b+'.schema.json')
                require(json.loads(raw)==json.loads((ROOT/'contracts'/f'visual_task_{target}.schema.json').read_text(encoding='utf-8')),'Incompatible visual task protocol')
            require(all(inside(root,p).is_file() for p in files),'Incomplete optional implementation')
            executable=config.get('python',sys.executable)
            require(_runtime_ready(executable),'Optional implementation Python dependencies are unavailable')
            return {'executor':'external','reason':'Compatible file-task implementation and Python dependencies available',
                'transport':'agent_file_task','mode':mode,'home':str(root),'python':executable,
                'resources':{p:sha256(inside(root,p)) for p in files}}
        except (OSError,ValueError,WorkflowError) as exc:
            # Discovery may fail, but malformed task inputs are never handled here.
            reason=str(exc)
    require(mode!='external','Required visual implementation unavailable: '+reason)
    return {**local,'reason':reason}


def invocation(selection,task_directory,operation='create_direction'):
    """Return real helper commands and an Agent entry, never a fictional service."""
    if selection['executor']=='main':
        prompt={'create_direction':'direction','review_render':'review','refine_direction':'refinement'}[operation]
        return {'agent_entry':str(ROOT/'prompts'/f'visual_task_{prompt}.md'),'transport':'local_agent'}
    root=Path(selection['home'])
    require(all(sha256(inside(root,p))==h for p,h in selection['resources'].items()),'Optional implementation changed after selection')
    return {'agent_entry':str(root/'SKILL.md'),'transport':'agent_file_task',
        'load':[selection['python'],'-B',str(root/'runtime/load_task.py'),str(task_directory)],
        'publish':[selection['python'],'-B',str(root/'runtime/publish_result.py'),str(task_directory)],
        'instruction':'Caller Agent reads the selected operation, views declared images, then publishes its decision with original input_digests.'}


def collect(manager,task_id,*,expected_version,execution=None):
    from runtime.visual_tasks import read_task,strict_json,submit
    record,request,_,_=read_task(manager,task_id,fresh=True)
    folder=inside(manager.root,record['request_path']).parent
    key='render_review' if record['operation']=='review_render' else 'render_direction'
    result=inside(folder,request['outputs'][key])
    error=inside(folder,request['outputs']['error'])
    require(not (result.exists() and error.exists()),'Ambiguous result and error; inspect the caller before recovery')
    if error.is_file():
        from runtime.visual_tasks import record_error
        return record_error(manager,task_id,strict_json(error),expected_version=expected_version)
    require(result.is_file(),'No published task result is available')
    require(result.stat().st_nlink==1,'Linked task result is unsupported')
    return submit(manager,task_id,strict_json(result),execution=execution,expected_version=expected_version)
