"""Blender-only style operations. Input dictionaries are resolved by project Python."""
import math
import uuid
from pathlib import Path
import bpy
from mathutils import Vector

def require_blender():
    if bpy.app.version < (4,2,0):
        raise RuntimeError('Blender 4.2 or newer required')

def material(name, p):
    require_blender()
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    nodes=mat.node_tree.nodes; links=mat.node_tree.links
    bsdf=nodes.get('Principled BSDF')
    for key,value in {'Base Color':[*p['base_color'],1],'Metallic':p['metallic'],'Roughness':p['roughness'],'Transmission Weight':p['transmission'],'IOR':p['ior'],'Emission Color':[*p['base_color'],1],'Emission Strength':p['emission_strength']}.items():
        bsdf.inputs[key].default_value=value
    if p['roughness_variation'] or p['bump_distance']:
        tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=p['noise_scale'];tex.inputs['Detail'].default_value=3
        coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['Object'],tex.inputs['Vector'])
        ramp=nodes.new('ShaderNodeMapRange')
        ramp.inputs['To Min'].default_value=max(.02,p['roughness']-p['roughness_variation']/2)
        ramp.inputs['To Max'].default_value=min(.98,p['roughness']+p['roughness_variation']/2)
        links.new(tex.outputs['Fac'],ramp.inputs['Value']);links.new(ramp.outputs['Result'],bsdf.inputs['Roughness'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.25;bump.inputs['Distance'].default_value=p['bump_distance']
        links.new(tex.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    return mat

def assign_resolved(obj, resolved):
    with bpy.data.libraries.load(resolved['library'],link=False) as (source,target):
        if resolved['resource'] not in source.materials:
            raise RuntimeError('Missing named style material')
        target.materials=[resolved['resource']]
    # Derive from the actual named library, with deterministic condition parameters.
    base=target.materials[0]
    derived=material(resolved['resource']+'.'+resolved['condition'],resolved['parameters'])
    derived['style_source']=base.name
    obj.data.materials.clear();obj.data.materials.append(derived)
    return derived

def aim(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()

def lighting(scene,p):
    require_blender()
    for obj in list(scene.objects):
        if obj.get('style_light'):
            scene.collection.objects.unlink(obj)
    world=bpy.data.worlds.new(scene.name+'.world');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs['Color'].default_value=[*p['world_color'],1]
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=p['world_strength'];scene.world=world
    for role in ('key','fill'):
        data=bpy.data.lights.new(role,'AREA');data.energy=p[role+'_energy'];data.shape='DISK';data.size=p[role+'_size']
        obj=bpy.data.objects.new(role,data);scene.collection.objects.link(obj);obj['style_light']=True;obj.location=p[role+'_location'];aim(obj,(0,0,0))

def render_settings(scene,p,color):
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=p['samples'];scene.cycles.seed=p['seed'];scene.cycles.use_denoising=p['denoise']
    scene.render.resolution_x=p['width'];scene.render.resolution_y=p['height'];scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform=color['view_transform'];scene.view_settings.exposure=color['exposure'];scene.view_settings.gamma=color['gamma']

def write_material_library(path, materials, profile):
    """Export canonical names, restoring all live names even when writing fails."""
    original={key:mat.name for key,mat in materials.items()}
    displaced=[]
    try:
        for key,mat in materials.items():
            canonical=profile+'.'+key
            existing=bpy.data.materials.get(canonical)
            if existing is not None and existing is not mat:
                displaced.append((existing,existing.name))
                existing.name='two_stage_export_'+uuid.uuid4().hex
            mat.name=canonical
        bpy.data.libraries.write(str(path),set(materials.values()),fake_user=True,compress=False)
    finally:
        for key,mat in materials.items():mat.name=original[key]
        for mat,name in displaced:mat.name=name

def calibration(style,output):
    require_blender()
    original=bpy.context.window.scene
    scene=bpy.data.scenes.new('industrial_acg_v1.calibration');bpy.context.window.scene=scene
    mats={k:material('industrial_acg_v1.'+k,p) for k,p in style['materials']['materials'].items()}
    def cube(name,loc,size,mat,bevel=.04):
        bpy.ops.mesh.primitive_cube_add(size=1,location=loc);obj=bpy.context.object;obj.name=name;obj.scale=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(mat)
        if bevel:
            mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3
            obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        return obj
    cube('ground',(0,0,-.15),(10,6,.3),mats['concrete'])
    cube('painted_metal',(-3,0,.7),(1.25,1.2,1.4),mats['painted_metal'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=.57,depth=1.4,location=(-1.55,0,.7));bpy.context.object.name='bare_metal';bpy.context.object.data.materials.append(mats['bare_metal'])
    bevel=bpy.context.object.modifiers.new('Edge','BEVEL');bevel.width=.04;bevel.segments=3
    for poly in bpy.context.object.data.polygons:poly.use_smooth=True
    cube('concrete_wall',(0,.25,.85),(1.25,.55,1.7),mats['concrete'])
    bpy.ops.mesh.primitive_torus_add(major_radius=.43,minor_radius=.17,location=(1.45,0,.61),rotation=(math.pi/2,0,0));bpy.context.object.name='rubber';bpy.context.object.data.materials.append(mats['rubber'])
    for poly in bpy.context.object.data.polygons:poly.use_smooth=True
    cube('glass_panel',(2.85,-.2,.85),(1.15,.08,1.7),mats['glass'],.015)
    cube('emissive_panel',(2.85,.55,.7),(.65,.12,.75),mats['emissive'],.03)
    if 'vegetation' in mats:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.5,location=(-3,1.7,.5))
        bpy.context.object.name='vegetation_sample';bpy.context.object.data.materials.append(mats['vegetation'])
    # Repeated dark stripes behind glass reveal transmission and refraction.
    for x in (2.5,2.85,3.2):cube('glass_background_stripe',(x,.8,1.25),(.07,.06,.6),mats['rubber'],0)
    labelmat=material('calibration.label',dict(style['materials']['materials']['rubber']))
    for index,name in enumerate(('PAINTED METAL','BARE METAL','CONCRETE','RUBBER','GLASS / LIGHT')):
        data=bpy.data.curves.new(name,'FONT');data.body=name;data.size=.16;data.align_x='CENTER';data.extrude=.001
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=(-3+index*1.47,-1.1,.012);obj.data.materials.append(labelmat)
    lighting(scene,style['lighting'])
    camdata=bpy.data.cameras.new('calibration.camera');cam=bpy.data.objects.new('calibration.camera',camdata);scene.collection.objects.link(cam);cam.location=(6,-11,7);aim(cam,(0,0,.5));camdata.type='ORTHO';camdata.ortho_scale=9.5;scene.camera=cam
    render_settings(scene,style['render'],style['color']);scene.render.filepath=output
    library=Path(style['library']);library.parent.mkdir(parents=True,exist_ok=True)
    write_material_library(library,mats,style['id'])
    cal=Path(style['calibration']);cal.parent.mkdir(parents=True,exist_ok=True)
    bpy.data.libraries.write(str(cal),{scene},fake_user=True,compress=False)
    bpy.context.window.scene=original
    return scene
