"""Translate semantic class/condition into versioned Blender shader parameters."""
from runtime.style_registry import StyleRegistry
from runtime.errors import BoundaryError

def resolve_material(profile, material_class, condition, *, registry=None, version=None, project_root=None):
    style=(registry or StyleRegistry()).load(profile,version=version,project_root=project_root)
    definitions=style['materials']
    if material_class not in definitions['materials']:
        raise BoundaryError(f'Unknown material class: {material_class}')
    if condition not in definitions['conditions']:
        raise BoundaryError(f'Unknown material condition: {condition}')
    parameters=dict(definitions['materials'][material_class])
    variation=definitions['conditions'][condition]
    parameters['roughness']=min(.98,parameters['roughness']+variation['roughness_add'])
    parameters['roughness_variation']*=variation['variation_scale']
    return {'profile':profile,'profile_version':style['version'],'material_class':material_class,'condition':condition,'resource':profile+'.'+material_class,'library':style['library'],'parameters':parameters,**{k:style[k] for k in ('lighting','atmosphere','camera','color','render')}}
