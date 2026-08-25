#!/usr/bin/env python3
"""Render deterministic front and side PNG previews for human Avatar Factory QA."""

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("usage: blender --background --python render_avatar_preview.py -- INPUT.glb OUTPUT_DIR")

    source = Path(args[0]).resolve()
    output_dir = Path(args[1]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh found in GLB")

    # A neutral clay override reveals topology in shape-only GLBs without
    # altering the candidate file or hiding defects behind bright white.
    clay = bpy.data.materials.new("QA Clay")
    clay.use_nodes = True
    principled = clay.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.18, 0.22, 0.30, 1.0)
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 0.72
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(clay)

    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (low + high) / 2
    size = high - low
    distance = max(size) * 2.25

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("QA World")
    scene.world.color = (0.008, 0.012, 0.03)

    camera_data = bpy.data.cameras.new("QA Camera")
    camera = bpy.data.objects.new("QA Camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 55

    for name, location, energy, size_light in (
        ("Key", center + Vector((-distance * 0.45, -distance * 0.7, distance * 0.65)), 1200, max(size) * 2),
        ("Fill", center + Vector((distance * 0.7, -distance * 0.2, distance * 0.25)), 800, max(size) * 1.5),
        ("Rim", center + Vector((0, distance * 0.6, distance * 0.8)), 1000, max(size) * 1.5),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size_light
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = location
        look_at(light, center)

    views = {
        "front": center + Vector((0, -distance, max(size.z * 0.08, 0.01))),
        "side": center + Vector((distance, 0, max(size.z * 0.08, 0.01))),
    }
    for name, location in views.items():
        camera.location = location
        look_at(camera, center)
        scene.render.filepath = str(output_dir / f"avatar-{name}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
