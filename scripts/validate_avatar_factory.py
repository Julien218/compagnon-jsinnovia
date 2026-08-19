#!/usr/bin/env python3
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    ROOT / 'config/avatar-factory.json',
    ROOT / 'config/finops-policy.schema.json',
    ROOT / 'scripts/avatar_factory_server.py',
    ROOT / 'scripts/start_avatar_factory.ps1',
    ROOT / 'characters/vaincriez-canary/manifest.json',
]
missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
if missing:
    raise SystemExit('Missing required files: ' + ', '.join(missing))

cfg = json.loads((ROOT / 'config/avatar-factory.json').read_text(encoding='utf-8'))
manifest = json.loads((ROOT / 'characters/vaincriez-canary/manifest.json').read_text(encoding='utf-8'))
assert cfg['server']['port'] == 8791
assert cfg['routing']['default'] == 'local'
assert 'human_approval' in cfg['approval_gates']
assert manifest['runtime']['target_format'] == 'VRM'
assert manifest['production']['human_approval_before_publish'] is True
py_compile.compile(str(ROOT / 'scripts/avatar_factory_server.py'), doraise=True)
print('Avatar Factory validation: OK')
