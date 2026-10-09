import unittest

from fencecoach.comparisons import comparable_capture


class CaptureComparisonTests(unittest.TestCase):
    def test_missing_setup_and_different_conditions_are_not_comparable(self):
        self.assertFalse(comparable_capture({}, {})[0])
        a = {
            "camera_setup_id": "garage",
            "weapon": "foil",
            "weapon_arm": "right",
            "front_leg": "right",
            "facing": "right",
            "camera_motion": "fixed",
            "scene_type": "solo",
        }
        self.assertTrue(comparable_capture(a, a)[0])
        self.assertFalse(comparable_capture(a, {**a, "camera_setup_id": "garden"})[0])
        self.assertFalse(comparable_capture(a, {**a, "inference_crop": {"width": 0.8}})[0])
