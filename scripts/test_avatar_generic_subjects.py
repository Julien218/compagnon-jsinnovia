#!/usr/bin/env python3
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "avatar_reference_upload_server.py"
spec = importlib.util.spec_from_file_location("avatar_reference_upload_server", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_slug_security():
    assert_equal(module.safe_slug("../../canari"), "canari", "path traversal is removed")
    assert_equal(module.safe_slug("Ma Tasse Rouge"), "Ma-Tasse-Rouge", "spaces become hyphens")


def test_rig_mapping():
    expected = {
        "person": "humanoid",
        "animal": "quadruped",
        "bird": "avian",
        "object": "none",
        "other": "generic",
        "auto": "none",
    }
    for kind, rig in expected.items():
        assert_equal(module.normalize_rig_mode("auto", kind), rig, f"rig mapping for {kind}")


def test_manifest_creation_and_views():
    original_root = module.ROOT
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.ROOT = root
            references = root / "runtime" / "avatar-factory" / "references" / "tasse-demo"
            references.mkdir(parents=True)
            payload = {
                "character_id": "tasse-demo",
                "subject_name": "Tasse rouge",
                "subject_kind": "object",
                "rig_mode": "auto",
            }
            for view in ("front", "left", "back", "right"):
                reference = references / f"{view}.png"
                reference.write_bytes(b"reference")
                result = module.upsert_character_manifest(payload, reference, view)
                assert Path(result["manifest_path"]).exists()

            manifest = json.loads(
                (root / "characters" / "tasse-demo" / "manifest.json").read_text(encoding="utf-8")
            )
            assert_equal(manifest["subject"]["kind"], "object", "object kind")
            assert_equal(manifest["subject"]["rig_mode"], "none", "object stays static")
            assert_equal(manifest["runtime"]["required_states"], ["static"], "object runtime state")
            assert_equal(
                manifest["reference"]["available_views"],
                ["back", "front", "left", "right"],
                "four views indexed",
            )
            assert manifest["production"]["turnaround_required"] is True
    finally:
        module.ROOT = original_root


def test_existing_manifest_is_upgraded_not_destroyed():
    original_root = module.ROOT
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.ROOT = root
            path = root / "characters" / "chat-demo" / "manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "id": "chat-demo",
                "name": "Ancien chat",
                "custom_field": {"preserve": True},
                "reference": {"views": {}},
            }), encoding="utf-8")
            result = module.upsert_character_manifest({
                "character_id": "chat-demo",
                "subject_name": "Chat de test",
                "subject_kind": "animal",
                "rig_mode": "auto",
            })
            manifest = result["manifest"]
            assert manifest["custom_field"]["preserve"] is True
            assert_equal(manifest["subject"]["rig_mode"], "quadruped", "animal rig")
            assert_equal(manifest["name"], "Chat de test", "name refreshed")
    finally:
        module.ROOT = original_root


if __name__ == "__main__":
    test_slug_security()
    test_rig_mapping()
    test_manifest_creation_and_views()
    test_existing_manifest_is_upgraded_not_destroyed()
    print("Avatar Factory generic subjects: OK")
