import json
import math
import sys
from pathlib import Path

try:
    import bmesh
    import bpy
    from mathutils import Vector
except ImportError as exc:
    raise SystemExit('Run inside Blender') from exc

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if len(args) < 2:
    raise SystemExit('Usage: blender --background --python scripts/blender_finalize_avatar.py -- input.glb output.glb')

src = Path(args[0]).resolve()
dst = Path(args[1]).resolve()
if not src.exists():
    raise SystemExit(f'Input GLB not found: {src}')

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(src))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not meshes:
    raise SystemExit('No mesh in GLB')


def mesh_connectivity(objects):
    """Return topology facts used to reject visibly fragmented generations."""
    component_sizes = []
    total_vertices = 0
    for obj in objects:
        vertex_count = len(obj.data.vertices)
        total_vertices += vertex_count
        if vertex_count == 0:
            continue
        parent = list(range(vertex_count))
        sizes = [1] * vertex_count

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left, right):
            left_root = find(left)
            right_root = find(right)
            if left_root == right_root:
                return
            if sizes[left_root] < sizes[right_root]:
                left_root, right_root = right_root, left_root
            parent[right_root] = left_root
            sizes[left_root] += sizes[right_root]

        for polygon in obj.data.polygons:
            vertices = list(polygon.vertices)
            for index in vertices[1:]:
                union(vertices[0], index)

        roots = {}
        for index in range(vertex_count):
            root = find(index)
            roots[root] = roots.get(root, 0) + 1
        component_sizes.extend(roots.values())

    largest = max(component_sizes, default=0)
    return {
        'connected_components': len(component_sizes),
        'largest_component_vertices': largest,
        'largest_component_ratio': round(largest / max(1, total_vertices), 4),
        'vertices': total_vertices,
    }


def remove_detached_fragments(objects, min_dominant_ratio=0.80):
    """Remove loose scan artefacts only when one connected piece clearly dominates."""
    removed_components = 0
    removed_vertices = 0
    for obj in objects:
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        unvisited = set(bm.verts)
        components = []
        while unvisited:
            seed = unvisited.pop()
            component = {seed}
            pending = [seed]
            while pending:
                vertex = pending.pop()
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    if other in unvisited:
                        unvisited.remove(other)
                        component.add(other)
                        pending.append(other)
            components.append(component)
        if len(components) <= 1:
            bm.free()
            continue
        dominant = max(components, key=len)
        total = sum(len(component) for component in components)
        if len(dominant) / max(1, total) < min_dominant_ratio:
            bm.free()
            continue
        detached = [vertex for component in components if component is not dominant for vertex in component]
        removed_components += len(components) - 1
        removed_vertices += len(detached)
        bmesh.ops.delete(bm, geom=detached, context='VERTS')
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
    return {'removed_components': removed_components, 'removed_vertices': removed_vertices}

# Normalize transforms, remove detached scan artefacts and cap excessive geometry.
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if len(obj.data.polygons) > 180000:
        mod = obj.modifiers.new('AvatarFactoryDecimate', 'DECIMATE')
        mod.ratio = max(0.12, 180000 / max(1, len(obj.data.polygons)))
        bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.select_set(False)

fragment_cleanup = remove_detached_fragments(meshes)

# World-space bounding box drives a generic mascot rig.
points = []
for obj in meshes:
    for corner in obj.bound_box:
        points.append(obj.matrix_world @ Vector(corner))
mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
size = maxs - mins
center = (mins + maxs) * 0.5
height = max(size.z, 0.001)
width = max(size.x, 0.001)

bpy.ops.object.armature_add(enter_editmode=True, location=(center.x, center.y, mins.z))
arm = bpy.context.object
arm.name = 'AvatarFactoryRig'
eb = arm.data.edit_bones
root = eb[0]
root.name = 'root'
root.head = (center.x, center.y, mins.z)
root.tail = (center.x, center.y, mins.z + height * 0.15)

body = eb.new('body')
body.parent = root
body.use_connect = True
body.head = root.tail
body.tail = (center.x, center.y, mins.z + height * 0.62)

head = eb.new('head')
head.parent = body
head.use_connect = True
head.head = body.tail
head.tail = (center.x, center.y, mins.z + height * 0.92)

for name, sign in [('wing.L', -1), ('wing.R', 1)]:
    bone = eb.new(name)
    bone.parent = body
    bone.head = (center.x, center.y, mins.z + height * 0.55)
    bone.tail = (center.x + sign * width * 0.45, center.y, mins.z + height * 0.48)

bpy.ops.object.mode_set(mode='OBJECT')

# Automatic weights. If a mesh cannot be weighted, keep it rigidly attached to body rather than failing the whole job.
for obj in meshes:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except Exception:
        obj.parent = arm
        obj.parent_type = 'BONE'
        obj.parent_bone = 'body'

# Lightweight idle loop: breathing/head tilt/wing micro movement.
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = 96
arm.animation_data_create()
action = bpy.data.actions.new('idle')
arm.animation_data.action = action
for frame, body_z, head_y, wing in [(1,0,0,0),(24,0.015,0.035,0.06),(48,0,0,0),(72,-0.01,-0.025,-0.04),(96,0,0,0)]:
    bpy.context.scene.frame_set(frame)
    pb = arm.pose.bones
    pb['body'].location.z = height * body_z
    pb['head'].rotation_mode = 'XYZ'
    pb['head'].rotation_euler.y = head_y
    pb['wing.L'].rotation_mode = 'XYZ'
    pb['wing.R'].rotation_mode = 'XYZ'
    pb['wing.L'].rotation_euler.y = wing
    pb['wing.R'].rotation_euler.y = -wing
    for name in ['body','head','wing.L','wing.R']:
        pb[name].keyframe_insert(data_path='location', frame=frame)
        pb[name].keyframe_insert(data_path='rotation_euler', frame=frame)

# Neutral camera-independent output for Three.js / R3F validation.
dst.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(dst), export_format='GLB', export_apply=True, export_animations=True)
connectivity = mesh_connectivity(meshes)
report = {
    'status': 'candidate_ready',
    'input': str(src),
    'output': str(dst),
    'meshes': len(meshes),
    'polygons': sum(len(o.data.polygons) for o in meshes),
    **connectivity,
    'fragment_cleanup': fragment_cleanup,
    'armature': arm.name,
    'bones': [b.name for b in arm.data.bones],
    'animations': ['idle'],
    'note': 'Automatic validation rig; visual review required before final VRM/publication.'
}
dst.with_suffix('.qa.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('AVATAR_FACTORY_FINAL=' + str(dst))
print(json.dumps(report))
