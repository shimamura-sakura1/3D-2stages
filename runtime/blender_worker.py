"""Run only inside Blender 4.2+. Receives data, never arbitrary generated Python."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def collection(name):
    result = bpy.context.scene.collection.children.get(name)
    if result is None:
        result = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(result)
    return result


def move(obj, destination):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    destination.objects.link(obj)


def transform(obj, specification):
    obj.location = specification["location"]
    obj.rotation_euler = [math.radians(v) for v in specification["rotation"]]
    obj.scale = specification["scale"]


def box(name, dimensions, destination, material):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move(obj, destination)
    obj.data.materials.append(material)
    return obj


def check_blender_version():
    if bpy.app.version < (4, 2, 0):
        raise RuntimeError("Blender 4.2 or newer is required for Stage 2")


def build(request, export=True):
    check_blender_version()
    plan = request["plan"]
    # An MCP session can contain unsaved user work. Never clear the active scene.
    scene = bpy.data.scenes.new(plan["scene"]["name"])
    bpy.context.window.scene = scene
    scene.world = bpy.data.worlds.new(scene.name + " World")
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    material = bpy.data.materials.new("Shared matte palette")
    material.diffuse_color = tuple(request["style"].get("materials", {}).get("base_color", [0.48, 0.38, 0.25, 1]))
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.8
    for entry in plan["assets"]:
        before = set(bpy.data.objects)
        source = request["assets"][entry["asset_id"]]
        if source.lower().endswith(".glb"):
            bpy.ops.import_scene.gltf(filepath=source)
        else:
            bpy.ops.wm.obj_import(filepath=source)
        imported = set(bpy.data.objects) - before
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError("Imported asset has no meshes")
        destination = collection(entry["collection"])
        root = bpy.data.objects.new(entry["asset_id"], None)
        destination.objects.link(root)
        for obj in imported:
            if obj.type in {"CAMERA", "LIGHT"}:
                bpy.data.objects.remove(obj, do_unlink=True)
                continue
            move(obj, destination)
            obj.name = f"{entry['asset_id']}_{obj.name}"
            if obj.parent not in imported:
                obj.parent = root
        # Center the asset horizontally and put its base at Z=0; preserve part transforms.
        bpy.context.view_layer.update()
        corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
        offset = Vector(((min(p.x for p in corners) + max(p.x for p in corners)) / 2,
                         (min(p.y for p in corners) + max(p.y for p in corners)) / 2,
                         min(p.z for p in corners)))
        for obj in list(root.children):
            obj.location -= offset
        transform(root, entry["transform"])
    for item in plan["procedural"]:
        destination = collection(item["collection"])
        if item["kind"] == "box":
            obj = box(item["name"], item["dimensions"], destination, material)
            transform(obj, item["transform"])
        else:
            # X=railway length, Y=gauge, Z=rail height; count=sleepers.
            length, gauge, height = item["dimensions"]
            root = bpy.data.objects.new(item["name"], None)
            destination.objects.link(root)
            for sign in (-1, 1):
                rail = box(f"{item['name']}_rail_{sign}", [length, 0.065, height], destination, material)
                rail.parent = root
                rail.location = [0, sign * gauge / 2, height / 2 + 0.12]
            for index in range(item["count"]):
                sleeper = box(f"{item['name']}_sleeper_{index}", [0.2, gauge + 0.6, 0.12], destination, material)
                sleeper.parent = root
                sleeper.location = [-length / 2 + (index + 0.5) * length / item["count"], 0, 0.06]
            transform(root, item["transform"])
    bpy.ops.object.camera_add(location=plan["camera"]["location"])
    camera = bpy.context.object
    camera.name = "Scene camera"
    direction = Vector(plan["camera"]["target"]) - camera.location
    if direction.length == 0:
        raise RuntimeError("Camera position and target must differ")
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = plan["camera"]["focal_length_mm"]
    scene.camera = camera
    move(camera, collection("Lighting"))
    bpy.ops.object.light_add(type="SUN")
    sun = bpy.context.object
    sun.data.energy = plan["lighting"]["energy"]
    sun.rotation_euler = [math.radians(v) for v in plan["lighting"]["rotation"]]
    move(sun, collection("Lighting"))
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.4, 0.5, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.4
    scene.render.engine = "CYCLES"
    scene.cycles.samples = plan["render"]["samples"]
    scene.render.resolution_x = plan["render"]["width"]
    scene.render.resolution_y = plan["render"]["height"]
    scene.render.resolution_percentage = 100
    if export:
        export_scene(request, scene)
        render_scene(request, scene)
    return scene


def export_scene(request, scene):
    bpy.context.window.scene = scene
    output = Path(request["output_dir"])
    if (output / "scene.blend").exists() or (output / "scene.glb").exists():
        raise RuntimeError("Export already exists; use a new build instead of overwriting it")
    # Pack images used by this scene without changing unrelated open scenes.
    images = set()
    for obj in scene.objects:
        for slot in obj.material_slots:
            if slot.material and slot.material.use_nodes:
                for node in slot.material.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image:
                        images.add(node.image)
    for image in images:
        if not image.packed_file:
            image.pack()
    # Write only the generated scene and its dependencies, preserving the open file.
    bpy.data.libraries.write(str(output / "scene.blend"), {scene}, path_remap="RELATIVE", compress=False)
    bpy.ops.export_scene.gltf(filepath=str(output / "scene.glb"), export_format="GLB", use_active_scene=True)


def render_scene(request, scene):
    bpy.context.window.scene = scene
    output = Path(request["output_dir"])
    if (output / "preview.png").exists():
        raise RuntimeError("Preview already exists; inspect the job before retrying")
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / "preview.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    build(json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8")))
