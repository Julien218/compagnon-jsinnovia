#!/usr/bin/env python3
import unittest

from avatar_runtime_qa import evaluate_runtime_qa


class RuntimeQATests(unittest.TestCase):
    def test_coherent_mesh_passes(self):
        qa = {
            "armature": "AvatarFactoryRig",
            "bones": ["root", "body"],
            "animations": ["idle"],
            "connected_components": 2,
            "largest_component_ratio": 0.96,
        }
        self.assertEqual(evaluate_runtime_qa(1.5, 25, qa), [])

    def test_fragmented_mesh_is_rejected(self):
        qa = {
            "armature": "AvatarFactoryRig",
            "bones": ["root", "body"],
            "animations": ["idle"],
            "connected_components": 57,
            "largest_component_ratio": 0.40,
        }
        self.assertEqual(
            evaluate_runtime_qa(1.56, 25, qa),
            [
                "mesh_fragmented_too_many_components",
                "mesh_fragmented_no_dominant_component",
            ],
        )

    def test_production_accessories_are_allowed(self):
        qa = {
            "armature": "AvatarFactoryRig",
            "bones": ["root", "body", "head"],
            "animations": ["idle"],
            "connected_components": 8,
            "largest_component_ratio": 0.9486,
        }
        self.assertEqual(evaluate_runtime_qa(15.847, 25, qa), [])


if __name__ == "__main__":
    unittest.main()
