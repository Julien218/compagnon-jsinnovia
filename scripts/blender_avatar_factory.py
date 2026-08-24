import json
import sys
from pathlib import Path

try:
    import bpy
except ImportError as exc:
    raise SystemExit('This script must run inside Blender') from exc

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if len(args) < 2:
    raise SystemExit('Usage: blender --background --python scripts/blender_avatar_factory.py -- input.glb output.glb')

input_path = Path(args[0]).resolve()
output_path = Path(args[1]).resolve()
if not input_path.exists():
    raise SystemExit(f'Input GLB not found: {input_path}')

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(input_path))
mesh_objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not mesh_objects:
    raise SystemExit('No mesh found in imported GLB')

for obj in mesh_objects:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if len(obj.data.polygons) > 150000:
        modifier = obj.modifiers.new(name='AvatarFactoryDecimate', type='DECIMATE')
        modifier.ratio = max(0.15, 150000 / len(obj.data.polygons))
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)

output_path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(output_path), export_format='GLB', export_apply=True)
report = {
    'input': str(input_path),
    'output': str(output_path),
    'meshes': len(mesh_objects),
    'polygons': sum(len(o.data.polygons) for o in mesh_objects),
}
output_path.with_suffix('.qa.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
