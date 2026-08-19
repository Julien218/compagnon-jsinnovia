#!/usr/bin/env python3
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    ROOT / 'config/avatar-factory.json',
    ROOT / 'config/finops-policy.schema.json',
    ROOT / 'workflows/comfyui/avatar_hunyuan3d_shape_api.json',
    ROOT / 'scripts/avatar_factory_server.py',
    ROOT / 'scripts/avatar_reference_upload_server.py',
    ROOT / 'scripts/run_avatar_comfyui.ps1',
    ROOT / 'scripts/blender_finalize_avatar.py',
    ROOT / 'scripts/sync_finops.py',
    ROOT / 'scripts/start_avatar_factory.ps1',
    ROOT / 'scripts/preflight_avatar_factory.ps1',
    ROOT / 'QUICKSTART_AVATAR_FACTORY.md',
    ROOT / 'characters/vaincriez-canary/manifest.json',
]
missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
if missing:
    raise SystemExit('Missing required files: ' + ', '.join(missing))

cfg = json.loads((ROOT / 'config/avatar-factory.json').read_text(encoding='utf-8'))
manifest = json.loads((ROOT / 'characters/vaincriez-canary/manifest.json').read_text(encoding='utf-8'))
workflow = json.loads((ROOT / 'workflows/comfyui/avatar_hunyuan3d_shape_api.json').read_text(encoding='utf-8'))
assert cfg['version'] >= 2
assert cfg['server']['port'] == 8791
assert cfg['routing']['default'] == 'local'
assert cfg['pipeline'] == ['reference_qa','shape_3d','blender_finalize','runtime_qa','human_approval']
assert cfg['approval_gates'] == ['human_approval']
assert cfg['runtime']['validation_format'] == 'GLB'
assert manifest['runtime']['target_format'] == 'VRM'
assert manifest['production']['human_approval_before_publish'] is True
assert workflow['2']['class_type'] == 'LoadImage'
assert workflow['10']['class_type'] == 'SaveGLB'
for script in ['avatar_factory_server.py', 'avatar_reference_upload_server.py', 'blender_finalize_avatar.py', 'sync_finops.py']:
    py_compile.compile(str(ROOT / 'scripts' / script), doraise=True)
print('Avatar Factory validation: OK')
