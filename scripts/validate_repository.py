from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str):
    path = ROOT / relative_path
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main() -> None:
    manifest = load_json("config/elyna-3d.manifest.json")
    sources = load_json("config/source-assets.json")
    presets = load_json("config/comfyui_presets.json")
    turnaround = load_json("assets/turnaround/GENERATED_ASSETS.json")
    workflow = load_json("workflows/comfyui/elyna_hunyuan3d_shape.json")
    api_workflow = load_json("workflows/comfyui/elyna_hunyuan3d_shape_api.json")

    canonical_name = "00_phenix_companion_officiel_reference.png"
    canonical_drive_id = "1y96GHd7_du62CNAIS9fZCUZsra7xKAto"
    checkpoint_name = "hunyuan_3d_v2.1.safetensors"

    require(manifest["id"] == "elyna", "Manifest id must remain elyna")
    require(manifest["canonicalReference"]["fileName"] == canonical_name, "Manifest canonical filename mismatch")
    require(manifest["canonicalReference"]["googleDriveFileId"] == canonical_drive_id, "Manifest canonical Drive ID mismatch")
    require(sources["sourceOfTruth"]["fileName"] == canonical_name, "Source asset filename mismatch")
    require(sources["sourceOfTruth"]["googleDriveFileId"] == canonical_drive_id, "Source asset Drive ID mismatch")
    require(turnaround["sourceOfTruth"] == canonical_name, "Turnaround source of truth mismatch")

    required_states = {"idle", "listening", "thinking", "speaking", "greeting", "presenting", "success", "error"}
    require(required_states.issubset(set(manifest["states"])), "Manifest is missing required runtime states")
    require({"blink", "aa"}.issubset(set(manifest["expressions"])), "Manifest is missing required expressions")

    require(presets["checkpoint"] == checkpoint_name, "Preset checkpoint mismatch")
    require(presets["presets"]["diagnostic_low_vram"]["latentResolution"] == 1024, "Diagnostic preset must remain 1024")
    require(presets["presets"]["production_shape"]["latentResolution"] == 2048, "Production candidate preset must remain 2048")

    required_nodes = {
        "ImageOnlyCheckpointLoader",
        "LoadImage",
        "ModelSamplingAuraFlow",
        "CLIPVisionEncode",
        "Hunyuan3Dv2Conditioning",
        "EmptyLatentHunyuan3Dv2",
        "KSampler",
        "VAEDecodeHunyuan3D",
        "VoxelToMesh",
        "SaveGLB",
    }

    node_types = {node.get("type") for node in workflow["nodes"]}
    require(required_nodes.issubset(node_types), f"Workflow missing nodes: {sorted(required_nodes - node_types)}")

    loader = next(node for node in workflow["nodes"] if node.get("type") == "ImageOnlyCheckpointLoader")
    image_loader = next(node for node in workflow["nodes"] if node.get("type") == "LoadImage")
    latent = next(node for node in workflow["nodes"] if node.get("type") == "EmptyLatentHunyuan3Dv2")

    require(checkpoint_name in loader.get("widgets_values", []), "Workflow checkpoint mismatch")
    require(canonical_name in image_loader.get("widgets_values", []), "Workflow canonical image mismatch")
    require(latent.get("widgets_values", [None])[0] == 1024, "Committed workflow must default to diagnostic 1024 mode")

    api_node_types = {node["class_type"] for node in api_workflow.values()}
    require(required_nodes.issubset(api_node_types), f"API workflow missing nodes: {sorted(required_nodes - api_node_types)}")
    require(api_workflow["1"]["inputs"]["ckpt_name"] == checkpoint_name, "API workflow checkpoint mismatch")
    require(api_workflow["2"]["inputs"]["image"] == canonical_name, "API workflow canonical image mismatch")
    require(api_workflow["4"]["inputs"]["resolution"] == 1024, "API workflow must default to diagnostic 1024 mode")
    require(api_workflow["10"]["inputs"]["filename_prefix"] == "Elyna/elyna_shape_low_vram_1024", "API workflow output prefix mismatch")

    secondary = {item["fileName"] for item in sources["secondaryReferences"]}
    expected_secondary = {
        "avatar_companion_fullbody_idle.png",
        "avatar_companion_fullbody_wave.png",
        "avatar_companion_fullbody_welcome.png",
        "avatar_companion_fullbody_holograms.png",
        "avatar_companion_bust_idle.png",
        "avatar_companion_bust_speaking.png",
        "avatar_companion_bust_thinking.png",
    }
    require(expected_secondary == secondary, "Secondary reference registry is incomplete or contains unexpected entries")

    required_paths = [
        "scripts/setup_hunyuan3d_checkpoint.ps1",
        "scripts/run_elyna_comfyui.ps1",
        "scripts/bootstrap_elyna_3d.ps1",
        "workflows/comfyui/elyna_hunyuan3d_shape.json",
        "workflows/comfyui/elyna_hunyuan3d_shape_api.json",
    ]
    for relative in required_paths:
        require((ROOT / relative).is_file(), f"Required production file missing: {relative}")

    print("Elyna companion repository validation: OK")


if __name__ == "__main__":
    main()
