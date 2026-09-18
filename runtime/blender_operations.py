"""Stable semantic operations; Blender imports occur only after packet checks."""
import hashlib
import copy
import math
import json
from pathlib import Path

OPERATIONS=('asset.import','asset.place','material.assign_semantic','lighting.apply_profile','atmosphere.apply_profile','camera.apply_profile','render.preview')

def resolved_material(material, mapping):
    """Scale only shader variation, leaving shared source parameters untouched."""
    value = copy.deepcopy(material)
    value['parameters']['roughness_variation'] *= mapping.get('roughness_variation_scale', 1)
    return value


def resolved_lighting(style, plan):
    """Resolve intensity and rotate key/fill positions around the world Z axis."""
    value = copy.deepcopy(style)
    if 'world_setup' in plan:
        value.update(copy.deepcopy(plan['world_setup']))
        return value
    factor = {'low': .65, 'medium': 1, 'high': 1.45}[plan['intensity']]
    for key in ('key_energy', 'fill_energy', 'world_strength'): value[key] *= factor
    radians = math.radians(plan.get('azimuth_offset_degrees', 0))
    for key in ('key_location', 'fill_location'):
        x, y, z = value[key]
        value[key] = [x*math.cos(radians)-y*math.sin(radians),
                      x*math.sin(radians)+y*math.cos(radians), z]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_packet(path,expected_sha):
    if file_hash(path)!=expected_sha:raise ValueError('Operation packet changed')
    p=json.loads(Path(path).read_text())
    for file,sha in p['guard'].items():
        if not Path(file).is_file() or file_hash(file)!=sha:raise ValueError('Operation input changed: '+file)
    if p['operations']!=list(OPERATIONS):raise ValueError('Unknown semantic operations')
    return p

def geometry_digest(value):
    """Signed zero has no geometric meaning and may change during blend I/O."""
    def normalize(item):
        if isinstance(item,float) and item==0:return 0.0
        if isinstance(item,list):return [normalize(x) for x in item]
        if isinstance(item,dict):return {k:normalize(v) for k,v in item.items()}
        return item
    return digest(normalize(value))

def geometry_fingerprint(scene):
    import bpy
    scene.frame_set(scene.frame_current)
    for obj in scene.objects:
        if obj.get('geometry_object'):obj.update_tag()
    bpy.context.view_layer.update()
    graph=bpy.context.evaluated_depsgraph_get();values=[]
    for obj in sorted((o for o in scene.objects if o.get('geometry_object')),key=lambda o:(o['scene_object_id'],o['instance'])):
        evaluated=obj.evaluated_get(graph);mesh=evaluated.to_mesh()
        try:values.append({'id':obj['scene_object_id'],'instance':obj['instance'],'matrix':[[round(x,7) for x in row] for row in obj.matrix_world],'vertices':[[round(x,7) for x in v.co] for v in mesh.vertices],'faces':[list(p.vertices) for p in mesh.polygons]})
        finally:evaluated.to_mesh_clear()
    return geometry_digest(values)

def require_steps(scene,p,expected):
    if scene.get('visual_inputs_digest')!=p['inputs_digest'] or not set(expected).issubset(json.loads(scene.get('visual_steps','[]'))):
        raise RuntimeError('Required semantic operations have not completed for these inputs')

def run(path,expected_sha,operation):
    if operation not in OPERATIONS:raise ValueError('Unknown semantic operation: '+operation)
    p=read_packet(path,expected_sha)
    import bpy,runpy,math
    from mathutils import Vector
    if bpy.app.version<(4,2,0):raise RuntimeError('Blender 4.2 or newer required')
    sw=runpy.run_path(p['workers']['style']);gw=runpy.run_path(p['workers']['geometry'])
    name='two-stage.'+p['build_id'];scene=bpy.data.scenes.get(name)
    original=bpy.context.window.scene
    if scene is None:
        source=p['outputs']['setup'] if operation=='render.preview' else p['outputs']['blockout']
        if Path(source).is_file():
            with bpy.data.libraries.load(source,link=False) as (available,selected):
                if name not in available.scenes:raise RuntimeError('Stored build scene is missing')
                selected.scenes=[name]
            scene=selected.scenes[0]
        elif operation=='asset.import':scene=bpy.data.scenes.new(name)
        else:raise RuntimeError('Build geometry is not available; run asset.import first')
    bpy.context.window.scene=scene
    try:
        if operation=='asset.import':
            if scene.get('blockout_key'):
                if scene['blockout_key']!=p['blockout_key'] or geometry_fingerprint(scene)!=scene['geometry_digest']:raise RuntimeError('Existing geometry changed')
                return {'status':'geometry_reused','build_id':p['build_id']}
            if scene.objects:raise RuntimeError('Incomplete existing build; inspect before restarting')
            for key,result in p['geometry'].items():
                obj=gw['import_geometry'](scene,p['project'],result);obj.name=p['build_id']+'.'+key
                obj['geometry_object']=True;obj['scene_object_id']=key;obj['instance']=0
        elif operation=='asset.place':
            if not scene.get('blockout_key'):
                objects={o['scene_object_id']:o for o in scene.objects if o.get('geometry_object')}
                for placement in p['plans']['blockout_plan']['objects']:
                    base=objects[placement['object_id']]
                    for i in range(placement['repetition']):
                        obj=base if i==0 else base.copy()
                        if i:
                            obj.data=base.data.copy();scene.collection.objects.link(obj);obj['instance']=i
                        tr=placement['transform'];obj.location=Vector(tr['location'])+Vector(placement['spacing'])*i
                        obj.rotation_euler=[math.radians(x) for x in tr['rotation']];obj.scale=tr['scale']
                        if placement['parent'] is not None:obj.parent=objects[placement['parent']]
                scene['blockout_key']=p['blockout_key'];scene['geometry_digest']=geometry_fingerprint(scene)
                path=Path(p['outputs']['blockout']);path.parent.mkdir(parents=True,exist_ok=True)
                if path.exists():raise RuntimeError('Existing blockout file must not be overwritten')
                bpy.data.libraries.write(str(path),{scene},compress=False)
            elif geometry_fingerprint(scene)!=scene['geometry_digest']:raise RuntimeError('Blockout geometry changed')
        else:
            if not scene.get('geometry_digest') or geometry_fingerprint(scene)!=scene['geometry_digest']:raise RuntimeError('Geometry changed before visual operation')
            if operation=='material.assign_semantic':
                scene['visual_inputs_digest']=p['inputs_digest']
                scene['visual_steps']=json.dumps([])
                mappings = {x['object_id']: x for x in p['plans']['semantic_material_map']['mappings']}
                for obj in scene.objects:
                    if obj.get('geometry_object'):
                        identity = obj['scene_object_id']
                        sw['assign_resolved'](obj, resolved_material(p['materials'][identity], mappings[identity]))
            elif operation=='lighting.apply_profile':
                require_steps(scene,p,['material.assign_semantic'])
                light = resolved_lighting(p['style']['lighting'], p['plans']['lookdev_plan']['lighting'])
                sw['lighting'](scene,light)
            elif operation=='atmosphere.apply_profile':
                require_steps(scene,p,['material.assign_semantic','lighting.apply_profile'])
                if scene.world is None:raise RuntimeError('Apply lighting before atmosphere')
                world=scene.world;world.use_nodes=True;nodes=world.node_tree.nodes
                for n in list(nodes):
                    if n.name=='two-stage.atmosphere':nodes.remove(n)
                amount=p['plans']['lookdev_plan']['atmosphere']['amount']
                if amount!='none':
                    volume=nodes.new('ShaderNodeVolumeScatter');volume.name='two-stage.atmosphere'
                    volume.inputs['Color'].default_value=[*p['style']['atmosphere']['color'],1]
                    volume.inputs['Density'].default_value=p['style']['atmosphere']['density']*{'subtle':.5,'medium':1,'dense':2}[amount]
                    world.node_tree.links.new(volume.outputs['Volume'],nodes.get('World Output').inputs['Volume'])
            elif operation=='camera.apply_profile':
                require_steps(scene,p,['material.assign_semantic','lighting.apply_profile','atmosphere.apply_profile'])
                r=p['plans']['render_plan'];camera=scene.camera
                if camera is None:
                    camera=bpy.data.objects.new(name+'.camera',bpy.data.cameras.new(name+'.camera'));scene.collection.objects.link(camera);scene.camera=camera
                camera.location=r['camera']['location'];sw['aim'](camera,r['camera']['target']);camera.data.type='PERSP';camera.data.lens=r['camera']['focal_length_mm']
                camera.data.clip_start=r['camera'].get('clip_start',p['style']['camera']['clip_start']);camera.data.clip_end=r['camera'].get('clip_end',p['style']['camera']['clip_end'])
                camera.data.sensor_fit='HORIZONTAL';camera.data.sensor_width=r['camera'].get('sensor_width_mm',36)
                render={**p['style']['render'],**r['preview']};color={**p['style']['color'],'exposure':r['color']['exposure']}
                sw['render_settings'](scene,render,color)
                if r['renderer']=='eevee':scene.render.engine='BLENDER_EEVEE_NEXT'
                after=geometry_fingerprint(scene)
                if after!=scene['geometry_digest']:raise RuntimeError('Lookdev changed geometry')
                steps=json.loads(scene['visual_steps']);steps.append('camera.apply_profile');scene['visual_steps']=json.dumps(steps)
                output=Path(p['outputs']['setup']);output.parent.mkdir(parents=True,exist_ok=True)
                bpy.data.libraries.write(str(output),{scene},compress=False)
                receipt={'status':'setup_complete','build_id':p['build_id'],'inputs_digest':p['inputs_digest'],'geometry_before':scene['geometry_digest'],'geometry_after':after,'blend_sha256':file_hash(output),'blender_version':bpy.app.version_string}
                Path(p['outputs']['receipt']).write_text(json.dumps(receipt,indent=2))
            elif operation=='render.preview':
                require_steps(scene,p,['material.assign_semantic','lighting.apply_profile','atmosphere.apply_profile','camera.apply_profile'])
                output=Path(p['outputs']['preview'])
                if output.exists():raise RuntimeError('Preview already exists; use a new pass path')
                # Rendering is explicit and synchronous here; MCP caller queues it with a timer.
                output.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(output)
                bpy.ops.render.render(write_still=True,scene=scene.name)
            steps=json.loads(scene.get('visual_steps','[]'))
            if operation not in steps:steps.append(operation)
            scene['visual_steps']=json.dumps(steps)
            if geometry_fingerprint(scene)!=scene['geometry_digest']:raise RuntimeError('Visual operation changed geometry')
        return {'status':'executed','operation':operation,'build_id':p['build_id'],'geometry_digest':scene.get('geometry_digest')}
    finally:bpy.context.window.scene=original

def render_job(packet_path,packet_sha,intent_path,intent_sha):
    """Run a reserved preview and write a proposal receipt, never official metadata."""
    from datetime import datetime,timezone
    import traceback
    if file_hash(intent_path)!=intent_sha:raise ValueError('Preview intent changed')
    intent=json.loads(Path(intent_path).read_text())
    packet=read_packet(packet_path,packet_sha)
    if intent['render_plan_hash']!=digest(packet['plans']['render_plan']) or intent['manifest_version']!=packet['manifest_version']:
        raise ValueError('Preview job does not match operation packet')
    receipt_path=Path(intent_path).parent/'worker-receipt.json'
    if receipt_path.exists():raise ValueError('Preview job already has a receipt; reserve another pass')
    receipt={'intent_sha256':intent_sha,'packet_sha256':packet_sha,'build_id':packet['build_id'],'pass_id':intent['pass_id'],'inputs_digest':packet['inputs_digest'],'render_success':False,'error':None,'image_sha256':None,'timestamp':datetime.now(timezone.utc).isoformat(),'geometry_digest':None}
    try:
        for operation in OPERATIONS:
            result=run(packet_path,packet_sha,operation)
        receipt.update(render_success=True,image_sha256=file_hash(packet['outputs']['preview']),geometry_digest=result['geometry_digest'])
    except Exception:
        receipt['error']=traceback.format_exc()
    receipt['timestamp']=datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(receipt,indent=2))
    return receipt
