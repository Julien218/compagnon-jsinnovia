#!/usr/bin/env python3
import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("avatar_reference_upload_server.py")
spec = importlib.util.spec_from_file_location("avatar_reference_upload_server", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Signature PNG suffisante pour tester le contrat d'entrée du service.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"avatar-factory-generic-subject-test"


class GenericManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        module.ROOT = root
        module.REFERENCES = root / "workspace" / "references"
        module.CHARACTERS = root / "characters"
        module.REFERENCES.mkdir(parents=True, exist_ok=True)
        module.CHARACTERS.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, character_id="chat-de-test"):
        return {
            "character_id": character_id,
            "display_name": "Chat de test",
            "subject_type": "animal",
            "file_name": "chat.png",
            "mime_type": "image/png",
            "data_base64": base64.b64encode(PNG_BYTES).decode("ascii"),
        }

    def test_upload_creates_manifest_for_any_subject(self):
        result = module.save_reference(self.payload())
        self.assertTrue(result["ok"])
        self.assertTrue(result["manifest_created"])
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["character_id"], "chat-de-test")
        self.assertEqual(manifest["subject_type"], "animal")
        self.assertTrue(manifest["generic_uploaded_subject"])
        self.assertEqual(manifest["reference"]["canonical_path"], result["relative_path"])

    def test_existing_curated_manifest_is_never_overwritten(self):
        folder = module.CHARACTERS / "canari-officiel"
        folder.mkdir(parents=True)
        manifest_path = folder / "manifest.json"
        original = {"character_id": "canari-officiel", "curated": True, "reference": {"canonical_path": "assets/canari.png"}}
        manifest_path.write_text(json.dumps(original), encoding="utf-8")

        result = module.save_reference(self.payload("canari-officiel"))
        self.assertFalse(result["manifest_created"])
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
