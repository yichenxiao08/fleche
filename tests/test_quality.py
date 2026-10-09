import unittest

from fencecoach.quality import assess_quality


def fixture():
    p = [[0.5, 0.5, 0, 0.9, 0.9] for _ in range(33)]
    return {
        "width": 1280,
        "height": 720,
        "frames": [
            {
                "features": {"stance_ratio": 0.8},
                "landmarks": p,
                "track_epoch": 1,
                "tracking": {"detected_poses": 1},
            }
            for _ in range(12)
        ],
        "capture_profile": {"scene_type": "solo", "facing": "right", "camera_motion": "fixed"},
        "camera_evidence": {"assessed": True, "moving": False},
        "candidates": [{}],
    }


class QualityTests(unittest.TestCase):
    def test_supported_and_low_resolution_rejection(self):
        r = fixture()
        self.assertEqual(assess_quality(r)["verdict"], "supported")
        r["height"] = 240
        self.assertFalse(assess_quality(r)["coaching_allowed"])

    def test_multiple_people_and_identity_break(self):
        r = fixture()
        r["frames"][0]["track_epoch"] = 2
        self.assertFalse(assess_quality(r)["coaching_allowed"])
        r = fixture()
        for f in r["frames"]:
            f["tracking"]["detected_poses"] = 2
        self.assertFalse(assess_quality(r)["coaching_allowed"])

    def test_camera_and_body_clipping(self):
        r = fixture()
        r["camera_evidence"]["moving"] = True
        self.assertFalse(assess_quality(r)["coaching_allowed"])
        r = fixture()
        r["frames"][0]["landmarks"][27][0] = 1.02
        self.assertFalse(assess_quality(r)["coaching_allowed"])

    def test_unknown_facing_warns_and_bout_is_experimental(self):
        r = fixture()
        r["capture_profile"]["facing"] = "unknown"
        self.assertEqual(assess_quality(r)["verdict"], "supported_with_warnings")
        r["capture_profile"]["scene_type"] = "bout"
        self.assertFalse(assess_quality(r)["coaching_allowed"])
