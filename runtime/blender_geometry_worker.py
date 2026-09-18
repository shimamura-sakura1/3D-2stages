"""Six bounded primitives and file import; no lookdev or rendering decisions."""
import math
import bpy
from mathutils import Vector


def world_bounds(scene):
    """Measured world AABBs grouped by semantic ID, including repeated meshes."""
    bpy.context.view_layer.update()
    depsgraph=bpy.context.evaluated_depsgraph_get()
    groups={}
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.get('scene_object_id'):
            continue
        evaluated=obj.evaluated_get(depsgraph)
        groups.setdefault(obj['scene_object_id'],[]).extend(
            evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    result={}
    for identity,points in groups.items():
        lo=[min(p[i] for p in points) for i in range(3)]
        hi=[max(p[i] for p in points) for i in range(3)]
        result[identity]={'center':[(a+b)/2 for a,b in zip(lo,hi)],'size':[b-a for a,b in zip(lo,hi)]}
    return result


def measure_scene_bounds(root, geometry, blockout):
    """Build only an isolated measurement scene; no material/camera/manifest writes.

    Call with validated approved geometry and the authored blockout. Production
    retains authority to validate these same inputs at formal plan submission.
    """
    previous=bpy.context.window.scene
    scene=bpy.data.scenes.new('two-stage.bounds')
    bpy.context.window.scene=scene
    try:
        objects={}
        for identity,result in geometry.items():
            obj=import_geometry(scene,root,result);obj['scene_object_id']=identity
            objects[identity]=obj
        for placement in blockout['objects']:
            base=objects[placement['object_id']]
            for index in range(placement['repetition']):
                obj=base if index==0 else base.copy()
                if index:scene.collection.objects.link(obj)
                transform=placement['transform']
                obj.location=Vector(transform['location'])+Vector(placement['spacing'])*index
                obj.rotation_euler=[math.radians(x) for x in transform['rotation']]
                obj.scale=transform['scale']
                if placement['parent'] is not None:obj.parent=objects[placement['parent']]
        return world_bounds(scene)
    finally:
        bpy.context.window.scene=previous
        for obj in list(scene.objects):
            mesh=obj.data if obj.type=='MESH' else None
            bpy.data.objects.remove(obj,do_unlink=True)
            if mesh is not None and mesh.users==0:bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(scene)


def primitive(scene,name,kind,size):
    if bpy.app.version<(4,2,0):raise RuntimeError('Blender 4.2 or newer required')
    if kind not in ('floor','wall','platform','column','rail','pipe'):raise RuntimeError('Unknown primitive')
    previous=bpy.context.window.scene;bpy.context.window.scene=scene
    parts=[]
    def cube(label,dimensions,location=(0,0,0)):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=label;obj.scale=dimensions
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);parts.append(obj)
        bevel=obj.modifiers.new('Edge bevel','BEVEL');bevel.width=min(dimensions)*.06;bevel.segments=2
        return obj
    try:
        x,y,z=size
        if kind in ('floor','wall','platform'):cube(name,size)
        elif kind=='column':
            bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=min(x,y)/2,depth=z);parts.append(bpy.context.object)
        elif kind=='pipe':
            # Hollow pipe along local Z, with deterministic wall thickness.
            n=32;ro=min(x,y)/2;ri=ro*.82
            vertices=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),h) for h in (-z/2,z/2) for r in (ro,ri) for i in range(n)]
            faces=[]
            for i in range(n):
                j=(i+1)%n
                faces.extend([(i,j,2*n+j,2*n+i),(n+j,n+i,3*n+i,3*n+j),(j,i,n+i,n+j),(2*n+i,2*n+j,3*n+j,3*n+i)])
            mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update();obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);parts.append(obj)
        else:
            cube(name+'.left',(x,y*.12,z*.6),(0,-y*.35,z*.2));cube(name+'.right',(x,y*.12,z*.6),(0,y*.35,z*.2))
            count=max(2,min(128,int(x/.6)+1))
            for i in range(count):cube(name+'.sleeper',(.16,y,z*.35),(-x/2+(i+.5)*x/count,0,-z*.3))
        for obj in scene.objects:obj.select_set(False)
        for obj in parts:obj.select_set(True)
        bpy.context.view_layer.objects.active=parts[0]
        if len(parts)>1:bpy.ops.object.join()
        obj=parts[0];obj.name=name;obj['geometry_primitive']=kind
        return obj
    finally:bpy.context.window.scene=previous


def import_geometry(scene,root,result):
    from pathlib import Path
    previous=bpy.context.window.scene;bpy.context.window.scene=scene
    try:
        geometry=result['geometry'];name=result['asset_id']
        if geometry['source']=='procedural':return primitive(scene,name,geometry['primitive'],result['scale']['dimensions_m'])
        path=(Path(root)/geometry['model']).resolve()
        if not path.is_relative_to(Path(root).resolve()):raise RuntimeError('Geometry path escapes project')
        before=set(scene.objects)
        if path.suffix.lower()=='.glb':bpy.ops.import_scene.gltf(filepath=str(path))
        elif path.suffix.lower()=='.obj':bpy.ops.wm.obj_import(filepath=str(path),forward_axis='Y',up_axis='Z')
        else:raise RuntimeError('Unsupported geometry format')
        meshes=[o for o in set(scene.objects)-before if o.type=='MESH']
        if not meshes:raise RuntimeError('Imported asset has no mesh')
        # Flatten imported hierarchy while retaining its evaluated world placement.
        for obj in meshes:
            matrix=obj.matrix_world.copy();obj.parent=None;obj.matrix_world=matrix
        for obj in scene.objects:obj.select_set(False)
        for obj in meshes:obj.select_set(True)
        bpy.context.view_layer.objects.active=meshes[0]
        if len(meshes)>1:bpy.ops.object.join()
        obj=meshes[0];obj.name=name
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        for extra in set(scene.objects)-before-{obj}:
            bpy.data.objects.remove(extra,do_unlink=True)
        # Apply source units and the explicit Route B scale recipe to geometry.
        factor=result['scale']['source_scale_m']
        modification=result['recipe']['modification']
        scale=modification['scale'] if modification else (1,1,1)
        for vertex in obj.data.vertices:
            vertex.co=Vector([vertex.co[i]*factor*scale[i] for i in range(3)])
        return obj
    finally:bpy.context.window.scene=previous
