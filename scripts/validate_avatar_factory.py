#!/usr/bin/env python3
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    ROOT / 'config/avatar-factory.json',
    ROOT / 'config/finops-policy.schema.json',
    ROOT / 'workflows/comfyui/avatar_hunyuan3d_shape_api.json',
    ROOT / 'workflows/comfyui/avatar_hunyuan3d_multiview_api.json',
    ROOT / 'scripts/avatar_factory_server.py',
    ROOT / 'scripts/avatar_runtime_qa.py',
    ROOT / 'scripts/test_avatar_runtime_qa.py',
    ROOT / 'scripts/avatar_reference_upload_server.py',
    ROOT / 'scripts/avatar_preview_server.py',
    ROOT / 'scripts/run_avatar_comfyui.ps1',
    ROOT / 'scripts/blender_finalize_avatar.py',
    ROOT / 'scripts/render_avatar_preview.py',
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
multi_workflow = json.loads((ROOT / 'workflows/comfyui/avatar_hunyuan3d_multiview_api.json').read_text(encoding='utf-8'))
server_source = (ROOT / 'scripts/avatar_factory_server.py').read_text(encoding='utf-8')
runner_source = (ROOT / 'scripts/run_avatar_comfyui.ps1').read_text(encoding='utf-8')
preflight_source = (ROOT / 'scripts/preflight_avatar_factory.ps1').read_text(encoding='utf-8')
finalizer_source = (ROOT / 'scripts/blender_finalize_avatar.py').read_text(encoding='utf-8')
assert cfg['version'] >= 2
assert cfg['server']['port'] == 8791
assert cfg['routing']['default'] == 'local'
assert cfg['pipeline'] == ['reference_qa','shape_3d','blender_finalize','runtime_qa','human_approval']
assert cfg['approval_gates'] == ['human_approval']
assert cfg['runtime']['validation_format'] == 'GLB'
assert cfg['runtime']['max_connected_components'] > 0
assert 0 < cfg['runtime']['min_largest_component_ratio'] <= 1
assert manifest['runtime']['target_format'] == 'VRM'
assert manifest['production']['human_approval_before_publish'] is True
assert workflow['2']['class_type'] == 'LoadImage'
assert workflow['10']['class_type'] == 'SaveGLB'
assert multi_workflow['6']['class_type'] == 'Hunyuan3Dv2ConditioningMultiView'
assert multi_workflow['6']['inputs']['front'] == ['13', 0]
assert multi_workflow['6']['inputs']['left'] == ['18', 0]
assert multi_workflow['6']['inputs']['back'] == ['19', 0]
assert multi_workflow['6']['inputs']['right'] == ['14', 0]
assert multi_workflow['16']['class_type'] == 'LoadImage'
assert multi_workflow['17']['class_type'] == 'LoadImage'
assert multi_workflow['18']['class_type'] == 'CLIPVisionEncode'
assert multi_workflow['19']['class_type'] == 'CLIPVisionEncode'
assert multi_workflow['1']['inputs']['ckpt_name'] == 'hunyuan3d-dit-v2-mv_fp16.safetensors'
assert multi_workflow['15']['class_type'] == 'FluxGuidance'
assert multi_workflow['15']['inputs']['guidance'] == 3.5
assert multi_workflow['7']['inputs']['positive'] == ['15', 0]
assert multi_workflow['7']['inputs']['steps'] == 20
assert multi_workflow['7']['inputs']['cfg'] == 1.0
assert multi_workflow['10']['class_type'] == 'SaveGLB'
assert 'right_reference_path' in server_source
assert 'left_reference_path' in server_source
assert 'back_reference_path' in server_source
assert 'Mode multivue incomplet' in server_source
assert 'seed must be between 1 and 2147483646' in server_source
assert 'hunyuan3d-dit-v2-mv_fp16.safetensors' in runner_source
assert 'LeftReferencePath' in runner_source
assert 'BackReferencePath' in runner_source
assert "@('front','left','back','right')" in runner_source
assert "@('front','left','back','right')" in preflight_source
assert "requiredNodes += 'FluxGuidance'" in runner_source
assert 'remove_detached_fragments' in finalizer_source
assert "'fragment_cleanup': fragment_cleanup" in finalizer_source
for script in ['avatar_factory_server.py', 'avatar_runtime_qa.py', 'test_avatar_runtime_qa.py', 'avatar_reference_upload_server.py', 'avatar_preview_server.py', 'blender_finalize_avatar.py', 'render_avatar_preview.py', 'sync_finops.py']:
    py_compile.compile(str(ROOT / 'scripts' / script), doraise=True)
print('Avatar Factory validation: OK')
