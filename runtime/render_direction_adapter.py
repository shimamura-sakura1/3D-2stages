"""Compile relative visual decisions into deterministic executable production plans."""
import copy
import itertools
import math
import json
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from runtime.validators import validate_contract
from runtime.visual_contracts import require


def radial(azimuth, elevation):
    a,e = math.radians(azimuth),math.radians(elevation)
    return [math.cos(e)*math.cos(a),math.cos(e)*math.sin(a),math.sin(e)]


def compile_render_direction(render_direction, scene_context, resolved_style):
    d = validate_contract('render_direction',render_direction)
    validate_contract('scene_context',scene_context)
    return _compile_direction(d,scene_context,resolved_style)


def compile_visual_direction(direction, scene_context, style, execution, task_id):
    validate_contract('visual_compile_request',{'direction':direction,'scene_context':scene_context,'execution':execution,'task_id':task_id})
    camera=direction['camera'];key=direction['lighting']['key']
    require(camera['target']['mode']=='subject_center' and key['reference_frame']=='camera_subject','Unsupported camera target or light reference frame')
    require(0<camera['subject_coverage']<=1 and camera['focal_length_mm']>0,'Invalid executable camera framing')
    require(camera['subject_ref']==scene_context['scene']['primary_subject']['object_id'],'Direction subject mismatch')
    # Feed the existing geometric solver explicit numbers, never qualitative prose.
    normalized={'direction_id':task_id,'revision':direction['revision'],
        'project_id':scene_context['production']['project_id'],'scene_version':scene_context['production']['scene_version'],
        'scene_type':scene_context['scene']['scene_type'],'camera':copy.deepcopy(camera),
        'lighting':copy.deepcopy(direction['lighting']),'atmosphere':{'amount':execution['fog_amount']}}
    normalized['camera']['subject_coverage']={'target':camera['subject_coverage']}
    normalized['lighting']['key']['softness']=execution['softness']
    look,render=_compile_direction(normalized,scene_context,style)
    for plan in (look,render):
        del plan['render_direction'];plan['visual_task']={'task_id':task_id}
    validate_contract('lookdev_plan',look);validate_contract('render_plan',render)
    return look,render


def _compile_direction(d,scene_context,resolved_style):
    scene, prod = scene_context['scene'], scene_context['production']
    require((d['project_id'],d['scene_version']) == (prod['project_id'],prod['scene_version']), 'Direction project/scene mismatch')
    require(d['scene_type'] == scene['scene_type'], 'Direction scene type mismatch')
    require(d['camera']['subject_ref'] == scene['primary_subject']['object_id'], 'Direction primary subject mismatch')
    style = copy.deepcopy(resolved_style)
    # Only executable defaults are consumed here. Priors belong to the external agent.
    settings = style.get('execution_default',style)
    cam, bounds = d['camera'], scene['primary_subject']['bounds']
    target = [c+s*offset for c,s,offset in zip(bounds['center'],bounds['size'],cam['target']['offset_normalized'])]
    back = radial(cam['azimuth_deg'],cam['elevation_deg'])
    a,e = math.radians(cam['azimuth_deg']),math.radians(cam['elevation_deg'])
    right = [-math.sin(a),math.cos(a),0]
    up = [-math.sin(e)*math.cos(a),-math.sin(e)*math.sin(a),math.cos(e)]
    render_settings = settings['render']; camera_defaults = settings['camera']
    sensor = camera_defaults.get('sensor_width_mm',36)
    width,height = render_settings['width'],render_settings['height']
    coverage,focal = cam['subject_coverage']['target'],cam['focal_length_mm']
    tangents = [sensor/(2*focal),sensor*height/width/(2*focal)]
    distance = 0
    # Exact perspective fit of the measured AABB including its near-side depth.
    for signs in itertools.product((-1,1),repeat=3):
        corner = [c+sign*s/2-t for c,sign,s,t in zip(bounds['center'],signs,bounds['size'],target)]
        depth = sum(v*b for v,b in zip(corner,back))
        for axis,tangent in zip((right,up),tangents):
            distance = max(distance,depth+abs(sum(v*b for v,b in zip(corner,axis)))/(coverage*tangent))
    distance += max(bounds['size'])*1e-6
    eye = [t+distance*b for t,b in zip(target,back)]
    require(eye[2] > scene['ground_z'], 'Compiled camera is below scene ground; request a revised direction')
    radius = math.sqrt(sum(s*s for s in scene['bounds']['size']))
    clip_start = min(camera_defaults['clip_start'],max(.001,distance*.001))
    clip_end = max(camera_defaults['clip_end'],distance+math.dist(target,scene['bounds']['center'])+radius*2)
    light_defaults = settings['lighting']; key = d['lighting']['key']
    light_distance = max(bounds['size'])*2
    setup = {}
    # Camera-subject azimuth zero points from the subject toward the camera.
    for role,angle,elevation in [('key',cam['azimuth_deg']+key['azimuth_deg'],key['elevation_deg']),
                                 ('fill',cam['azimuth_deg'],cam['elevation_deg'])]:
        ray = radial(angle,elevation)
        setup[role+'_location'] = [t+light_distance*v for t,v in zip(target,ray)]
        setup[role+'_target'] = target[:]
        setup[role+'_type'] = light_defaults.get(role+'_type','AREA')
        setup[role+'_color'] = light_defaults.get(role+'_color',[1,1,1])
        setup[role+'_size'] = light_defaults[role+'_size']*{'small':.5,'medium':1,'large':2}[key['softness']]
        setup[role+'_energy'] = light_defaults['key_energy']*(1 if role == 'key' else d['lighting']['fill']['ratio_to_key'])
    base = {'schema_version':'0.2','project_id':prod['project_id'],'scene_version':prod['scene_version']}
    source = {'direction_id':d['direction_id'],'revision':d['revision']}
    look = {**base,'document_id':'lookdev_directed','revision':prod.get('look_revision',0),
            'style_assignment_id':prod.get('style_assignment_id','style_assignment_01'),
            'material_map_id':prod.get('material_map_id','semantic_material_map_01'),
            'lighting':{'profile':settings['lighting']['profile'],'intensity':'medium','world_setup':setup},
            'atmosphere':{'profile':settings['atmosphere']['profile'],'amount':{'moderate':'medium','heavy':'dense'}.get(d['atmosphere']['amount'],d['atmosphere']['amount'])},
            'render_direction':source,'render_direction_mapping':{'lighting_source':'relative_direction'}}
    render = {**base,'document_id':'render_directed','revision':prod.get('render_revision',0),'purpose':'preview',
              'renderer':render_settings['renderer'],
              'camera':{'profile':camera_defaults['profile'],'location':eye,'target':target,'focal_length_mm':focal,
                        'rotation':[math.pi/2-e,0,a+math.pi/2],
                        'clip_start':clip_start,'clip_end':clip_end,'sensor_width_mm':sensor},
              'preview':{k:render_settings[k] for k in ('width','height','samples')},
              'color':{'profile':settings['color']['profile'],
                       'exposure':settings['color']['exposure']},
              'output':{'image_path':'stage2/previews/pass_00/preview.png'},'render_direction':source}
    validate_contract('lookdev_plan',look); validate_contract('render_plan',render)
    return look,render


def main():
    """Standalone deterministic compilation; does not register or execute plans."""
    from runtime.errors import WorkflowError
    import argparse
    parser=argparse.ArgumentParser(description='Compile validated relative direction without executing a scene')
    parser.add_argument('--audit-dir',help='New directory for validated input snapshots')
    args=parser.parse_args()
    try:
        request=json.load(sys.stdin)
        validate_contract('render_direction_request',request)
        require(request['context']['project']=={'project_id':request['direction']['project_id'],
                'scene_version':request['direction']['scene_version']},'Context/direction identity mismatch')
        look,render=compile_render_direction(request['direction'],request['scene_context'],request['style'])
        result={'lookdev_plan':look,'render_plan':render}
        validate_contract('directed_plans',result)
        if args.audit_dir:
            folder=Path(args.audit_dir)
            require(not folder.exists(), 'Audit directory must be new')
            for kind,key in [('render_context','context'),('render_direction','direction'),('render_review','review'),('scene_context','scene_context')]:
                validate_contract(kind,request[key])
            folder.mkdir(parents=True)
            for key in ('context','direction','review','scene_context'):
                (folder/(key+'.json')).write_text(json.dumps(request[key],allow_nan=False),encoding='utf-8')
        print(json.dumps(result,allow_nan=False))
        return 0
    except (WorkflowError,ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
