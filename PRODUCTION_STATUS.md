# Elyna — Production status

_Last updated: 2026-08-16_

## Source identity

- [x] Canonical phoenix reference identified and indexed
- [x] Canonical Drive file ID recorded
- [x] Secondary full-body and bust references indexed
- [x] Character design rules locked in `config/elyna-3d.manifest.json`

## Turnaround

- [x] Front / left / back / right generation registry exists
- [ ] Binary turnaround PNGs uploaded to durable storage
- [ ] Four views visually validated against the canonical reference

Current registry: `assets/turnaround/GENERATED_ASSETS.json`

## Shape generation

- [x] Hunyuan3D 2.1 pipeline selected
- [x] Executable ComfyUI UI workflow added: `workflows/comfyui/elyna_hunyuan3d_shape.json`
- [x] Executable ComfyUI API prompt added: `workflows/comfyui/elyna_hunyuan3d_shape_api.json`
- [x] Diagnostic preset defined (1024)
- [x] Production candidate preset defined (2048)
- [x] Verified checkpoint installer added: `scripts/setup_hunyuan3d_checkpoint.ps1`
- [x] One-command API runner added: `scripts/run_elyna_comfyui.ps1`
- [x] Runner validates checkpoint SHA256, ComfyUI connectivity and required Hunyuan3D nodes before submission
- [ ] Raw Elyna GLB generated and reviewed on real Hunyuan3D compute

## Blender / animation

- [ ] Mesh cleanup and retopology
- [ ] Separate logical parts (headset/mic, armor, wings, tail, limbs)
- [ ] UV and PBR materials
- [ ] Rig and skinning
- [ ] Wing and tail controls
- [ ] Expressions `blink` and `aa`
- [ ] States: idle, listening, thinking, speaking, greeting, presenting, success, error

## Runtime delivery

- [x] Web runtime prepared in `js-innov.ia`
- [x] `@pixiv/three-vrm` integration prepared
- [x] 2D fallback retained
- [x] Activation gate requires a validated VRM
- [ ] Final `elyna.vrm` delivered
- [ ] Desktop and mobile visual smoke tests
- [ ] 3D activation approved

## Blocking item

The remaining blocking asset for actual 3D activation is a real generated, cleaned, rigged and validated VRM. A rendered image, dummy mesh or placeholder file must never be renamed to `.vrm`.

## Execution order

1. Install/verify `hunyuan_3d_v2.1.safetensors` with `scripts/setup_hunyuan3d_checkpoint.ps1`.
2. Start ComfyUI.
3. Keep `00_phenix_companion_officiel_reference.png` or `elyna-reference.png` in `ComfyUI/input/`.
4. Run `scripts/run_elyna_comfyui.ps1 -Preset diagnostic`.
5. Review the 1024 raw GLB against the canonical phoenix reference.
6. Only if the diagnostic is stable and faithful, run `scripts/run_elyna_comfyui.ps1 -Preset production`.
7. Move the chosen GLB to Blender for cleanup, retopology and rigging.
8. Export VRM and run the website validation gate.
9. Activate 3D only after desktop/mobile smoke tests pass.
