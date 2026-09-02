import json
import sqlite3
import sys
from pathlib import Path

try:
    import bmesh
    import bpy
    from mathutils import Vector
except ImportError as exc:
    raise SystemExit("Run inside Blender") from exc

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) < 2:
    raise SystemExit("Usage: blender --background --python scripts/blender_finalize_avatar.py -- input.glb output.glb")

src = Path(args[0]).resolve()
dst = Path(args[1]).resolve()
if not src.exists():
    raise SystemExit(f"Input GLB not found: {src}")

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_KINDS = {"auto", "person", "animal", "bird", "object", "other"}
RIG_MODES = {"auto", "none", "humanoid", "quadruped", "avian", "generic"}


def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def normalized_subject_kind(value):
    value = str(value or "auto").strip().lower()
    return value if value in SUBJECT_KINDS else "auto"


def default_rig_mode(subject_kind):
    return {
        "person": "humanoid",
        "animal": "quadruped",
        "bird": "avian",
        "object": "none",
        "other": "generic",
        "auto": "none",
    }.get(subject_kind, "none")


def normalized_rig_mode(value, subject_kind):
    value = str(value or "auto").strip().lower()
    if value not in RIG_MODES:
        value = "auto"
    return default_rig_mode(subject_kind) if value == "auto" else value


def job_metadata_from_database():
    config = load_json(ROOT / "config" / "avatar-factory.json")
    workspace = str(config.get("paths", {}).get("workspace") or "runtime/avatar-factory")
    database = ROOT / workspace / "avatar_factory.sqlite3"
    if not database.exists():
        return {}
    job_id = src.parent.name
    try:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT character_id,input_json FROM jobs WHERE id=? LIMIT 1",
            (job_id,),
        ).fetchone()
        connection.close()
        if not row:
            return {}
        payload = json.loads(row["input_json"] or "{}")
        if not isinstance(payload, dict):
            payload = {}
        return {
            **payload,
            "character_id": row["character_id"] or payload.get("character_id"),
        }
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        return {}


def production_metadata():
    candidates = [
        Path(str(src) + ".meta.json"),
        src.with_suffix(".meta.json"),
    ]
    metadata = next((load_json(candidate) for candidate in candidates if candidate.exists()), {})
    if not metadata:
        metadata = job_metadata_from_database()
    character_id = str(metadata.get("character_id") or "").strip()
    manifest_path = metadata.get("manifest_path")
    if not manifest_path and character_id:
        manifest_path = ROOT / "characters" / character_id / "manifest.json"
    manifest = load_json(Path(manifest_path)) if manifest_path else {}
    subject = manifest.get("subject") if isinstance(manifest.get("subject"), dict) else {}
    subject_kind = normalized_subject_kind(metadata.get("subject_kind") or subject.get("kind"))
    rig_mode = normalized_rig_mode(metadata.get("rig_mode") or subject.get("rig_mode"), subject_kind)
    return {
        "character_id": character_id or manifest.get("id") or "avatar",
        "subject_kind": subject_kind,
        "rig_mode": rig_mode,
        "manifest_path": str(Path(manifest_path).resolve()) if manifest_path else None,
    }


meta = production_metadata()

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(src))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not meshes:
    raise SystemExit("No mesh in GLB")


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
        "connected_components": len(component_sizes),
        "largest_component_vertices": largest,
        "largest_component_ratio": round(largest / max(1, total_vertices), 4),
        "vertices": total_vertices,
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
        bmesh.ops.delete(bm, geom=detached, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
    return {"removed_components": removed_components, "removed_vertices": removed_vertices}


for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if len(obj.data.polygons) > 180000:
        modifier = obj.modifiers.new("AvatarFactoryDecimate", "DECIMATE")
        modifier.ratio = max(0.12, 180000 / max(1, len(obj.data.polygons)))
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)

fragment_cleanup = remove_detached_fragments(meshes)

points = []
for obj in meshes:
    for corner in obj.bound_box:
        points.append(obj.matrix_world @ Vector(corner))
mins = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
maxs = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
size = maxs - mins
center = (mins + maxs) * 0.5
height = max(size.z, 0.001)
width = max(size.x, 0.001)
depth = max(size.y, 0.001)


def add_bone(edit_bones, name, head, tail, parent=None, connected=False):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent is not None:
        bone.parent = parent
        bone.use_connect = connected
    return bone


def create_rig(rig_mode):
    if rig_mode == "none":
        return None

    bpy.ops.object.armature_add(enter_editmode=True, location=(center.x, center.y, mins.z))
    armature = bpy.context.object
    armature.name = f"AvatarFactoryRig.{rig_mode}"
    edit_bones = armature.data.edit_bones
    root = edit_bones[0]
    root.name = "root"
    root.head = (center.x, center.y, mins.z)
    root.tail = (center.x, center.y, mins.z + height * 0.10)

    if rig_mode == "humanoid":
        hips = add_bone(edit_bones, "hips", root.tail, (center.x, center.y, mins.z + height * 0.38), root, True)
        spine = add_bone(edit_bones, "spine", hips.tail, (center.x, center.y, mins.z + height * 0.68), hips, True)
        neck = add_bone(edit_bones, "neck", spine.tail, (center.x, center.y, mins.z + height * 0.78), spine, True)
        add_bone(edit_bones, "head", neck.tail, (center.x, center.y, mins.z + height * 0.96), neck, True)
        for name, sign in (("arm.L", -1), ("arm.R", 1)):
            add_bone(
                edit_bones,
                name,
                (center.x, center.y, mins.z + height * 0.66),
                (center.x + sign * width * 0.45, center.y, mins.z + height * 0.52),
                spine,
            )
        for name, sign in (("leg.L", -1), ("leg.R", 1)):
            add_bone(
                edit_bones,
                name,
                (center.x + sign * width * 0.14, center.y, mins.z + height * 0.37),
                (center.x + sign * width * 0.16, center.y, mins.z + height * 0.03),
                hips,
            )
    elif rig_mode == "quadruped":
        body = add_bone(
            edit_bones,
            "body",
            root.tail,
            (center.x, center.y, mins.z + height * 0.60),
            root,
            True,
        )
        neck = add_bone(
            edit_bones,
            "neck",
            body.tail,
            (center.x, center.y - depth * 0.18, mins.z + height * 0.74),
            body,
        )
        add_bone(
            edit_bones,
            "head",
            neck.tail,
            (center.x, center.y - depth * 0.30, mins.z + height * 0.86),
            neck,
        )
        for name, x_sign, y_sign in (
            ("leg.front.L", -1, -1),
            ("leg.front.R", 1, -1),
            ("leg.back.L", -1, 1),
            ("leg.back.R", 1, 1),
        ):
            add_bone(
                edit_bones,
                name,
                (
                    center.x + x_sign * width * 0.22,
                    center.y + y_sign * depth * 0.18,
                    mins.z + height * 0.46,
                ),
                (
                    center.x + x_sign * width * 0.24,
                    center.y + y_sign * depth * 0.18,
                    mins.z + height * 0.04,
                ),
                body,
            )
        add_bone(
            edit_bones,
            "tail",
            (center.x, center.y + depth * 0.20, mins.z + height * 0.54),
            (center.x, center.y + depth * 0.52, mins.z + height * 0.68),
            body,
        )
    else:
        body = add_bone(edit_bones, "body", root.tail, (center.x, center.y, mins.z + height * 0.62), root, True)
        add_bone(edit_bones, "head", body.tail, (center.x, center.y, mins.z + height * 0.92), body, True)
        appendage_names = ("wing.L", "wing.R") if rig_mode == "avian" else ("appendage.L", "appendage.R")
        for name, sign in zip(appendage_names, (-1, 1)):
            add_bone(
                edit_bones,
                name,
                (center.x, center.y, mins.z + height * 0.55),
                (center.x + sign * width * 0.45, center.y, mins.z + height * 0.48),
                body,
            )

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


arm = create_rig(meta["rig_mode"])

if arm is not None:
    fallback_bone = "body" if arm.data.bones.get("body") else "hips" if arm.data.bones.get("hips") else "root"
    for obj in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        except Exception:
            obj.parent = arm
            obj.parent_type = "BONE"
            obj.parent_bone = fallback_bone


def insert_keyframes(pose_bone, frame):
    pose_bone.keyframe_insert(data_path="location", frame=frame)
    pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def create_idle_animation(armature):
    if armature is None:
        return []
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 96
    armature.animation_data_create()
    action = bpy.data.actions.new("idle")
    armature.animation_data.action = action
    pose = armature.pose.bones

    motion_bone = pose.get("body") or pose.get("spine") or pose.get("hips") or pose.get("root")
    head_bone = pose.get("head")
    side_bones = [
        pose.get("wing.L") or pose.get("appendage.L") or pose.get("arm.L"),
        pose.get("wing.R") or pose.get("appendage.R") or pose.get("arm.R"),
    ]
    tail_bone = pose.get("tail")

    for frame, body_z, head_y, side_rotation in (
        (1, 0.0, 0.0, 0.0),
        (24, 0.012, 0.028, 0.04),
        (48, 0.0, 0.0, 0.0),
        (72, -0.008, -0.020, -0.03),
        (96, 0.0, 0.0, 0.0),
    ):
        bpy.context.scene.frame_set(frame)
        motion_bone.location.z = height * body_z
        motion_bone.rotation_mode = "XYZ"
        insert_keyframes(motion_bone, frame)
        if head_bone:
            head_bone.rotation_mode = "XYZ"
            head_bone.rotation_euler.y = head_y
            insert_keyframes(head_bone, frame)
        for index, bone in enumerate(side_bones):
            if bone:
                bone.rotation_mode = "XYZ"
                bone.rotation_euler.y = side_rotation * (-1 if index == 1 else 1)
                insert_keyframes(bone, frame)
        if tail_bone:
            tail_bone.rotation_mode = "XYZ"
            tail_bone.rotation_euler.x = side_rotation
            insert_keyframes(tail_bone, frame)
    return ["idle"]


animations = create_idle_animation(arm)

dst.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(dst),
    export_format="GLB",
    export_apply=True,
    export_animations=bool(animations),
)
connectivity = mesh_connectivity(meshes)
report = {
    "status": "candidate_ready",
    "input": str(src),
    "output": str(dst),
    "character_id": meta["character_id"],
    "subject_kind": meta["subject_kind"],
    "rig_mode": meta["rig_mode"],
    "static_asset": arm is None,
    "meshes": len(meshes),
    "polygons": sum(len(obj.data.polygons) for obj in meshes),
    **connectivity,
    "fragment_cleanup": fragment_cleanup,
    "armature": arm.name if arm else None,
    "bones": [bone.name for bone in arm.data.bones] if arm else [],
    "animations": animations,
    "manifest_path": meta["manifest_path"],
    "note": (
        "Static GLB: no rig was added because the subject is an object or automatic safe mode."
        if arm is None
        else "Automatic validation rig; visual review required before final VRM/publication."
    ),
}
dst.with_suffix(".qa.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("AVATAR_FACTORY_FINAL=" + str(dst))
print(json.dumps(report, ensure_ascii=False))
