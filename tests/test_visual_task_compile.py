import copy
import pytest
from runtime.errors import WorkflowError
from runtime.style_registry import StyleRegistry
from tests.visual_task_helpers import setup,direction,execution

def test_numeric_compile_and_explicit_interpretation(tmp_path):
    from runtime.render_direction_adapter import compile_visual_direction
    _,spec=setup(tmp_path);style=StyleRegistry().load('industrial_acg_v1')
    a=compile_visual_direction(direction(),spec['scene_context'],style,execution(),'task_1')
    b=compile_visual_direction(direction(),spec['scene_context'],style,execution(),'task_1')
    assert a==b and a[1]['camera']['location'][2]>0
    assert a[0]['visual_task']=={'task_id':'task_1'}
    with pytest.raises(WorkflowError):compile_visual_direction(direction(),spec['scene_context'],style,{},'task_1')
    d=direction();d['lighting']['key']['reference_frame']='unsupported'
    with pytest.raises(WorkflowError):compile_visual_direction(d,spec['scene_context'],style,execution(),'task_1')
