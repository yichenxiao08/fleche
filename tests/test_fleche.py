import unittest

from fencecoach.fleche import detect_fleche


def frame(t, hip, rear, shoulder, epoch=0):
    points = [[0.5, 0.5, 0, 0.95] for _ in range(33)]
    points[0][1] = 0.1
    for j in (27, 28):
        points[j][1] = 0.9
    points[27][0], points[28][0] = 0.55, rear
    for j in (23, 24):
        points[j][0], points[j][1] = hip, 0.6
    for j in (11, 12):
        points[j][0], points[j][1] = shoulder, 0.35
    return {
        "time_ms": t,
        "landmarks": points,
        "quality": 0.95,
        "track_epoch": epoch,
        "features": {"stance_ratio": 0.8, "left_arm_extension": 0.95},
    }


class FlecheRulesTests(unittest.TestCase):
    def setUp(self):
        self.frames = [
            frame(0, 0.45, 0.4, 0.45),
            frame(100, 0.45, 0.4, 0.45),
            frame(200, 0.46, 0.4, 0.46),
            frame(300, 0.47, 0.5, 0.49),
            frame(400, 0.54, 0.65, 0.60),
            frame(500, 0.60, 0.7, 0.67),
            frame(600, 0.65, 0.75, 0.72),
        ]
        self.profile = {"facing": "right", "camera_motion": "fixed", "weapon_arm": "left"}
        self.guard = {"start_ms": 0, "end_ms": 100, "stance_ratio": 0.4}

    def test_beta_crossing_and_timing(self):
        events = detect_fleche(self.frames, 1000, 1000, self.profile, self.guard)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "beta")
        self.assertIn(
            "fleche_arm_extension_before_image_drive",
            [m["name"] for m in events[0]["measurements"]],
        )

    def test_fixed_camera_and_guard_required(self):
        self.assertEqual(
            detect_fleche(
                self.frames, 1000, 1000, {**self.profile, "camera_motion": "moving"}, self.guard
            ),
            [],
        )
        self.assertEqual(detect_fleche(self.frames, 1000, 1000, self.profile, None), [])

    def test_tracking_gap_and_cropped_crossing_abstain(self):
        self.frames[4]["track_epoch"] = 1
        self.assertEqual(detect_fleche(self.frames, 1000, 1000, self.profile, self.guard), [])
        self.frames[4]["track_epoch"] = 0
        self.frames[4]["landmarks"][28][0] = 1.1
        self.assertEqual(detect_fleche(self.frames, 1000, 1000, self.profile, self.guard), [])
