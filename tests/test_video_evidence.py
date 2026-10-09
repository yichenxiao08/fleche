import unittest

from fencecoach.athlete_tracking import AthleteTracker, selection_hint
from fencecoach.video_pipeline import find_guard_baseline, proposals


def pose(center):
    p = [[center, 0.6, 0.0, 0.9, 0.9] for _ in range(33)]
    for i in (11, 12):
        p[i][1] = 0.4
    return p


def frame(t, stance=0.7, knee=120, epoch=1):
    return {
        "time_ms": t,
        "quality": 0.9,
        "track_epoch": epoch,
        "features": {
            "stance_ratio": stance,
            "left_knee_angle": knee,
            "right_knee_angle": knee,
            "hip_x_torso": 1.0,
            "torso_tilt": 5,
        },
    }


class VideoEvidenceTests(unittest.TestCase):
    def test_declared_location_is_distinct_from_facing(self):
        self.assertEqual(
            selection_hint("Foreground athlete on screen right, facing screen left."), "right"
        )
        self.assertIsNone(selection_hint("Primary athlete, facing screen right."))
        tracker = AthleteTracker({"x": 0, "y": 0, "width": 1, "height": 1}, 1000, 500, "right")
        self.assertIsNone(tracker.select([pose(0.2)], 0)[0])
        selected, meta = tracker.select([pose(0.2), pose(0.7)], 83)
        self.assertEqual(selected[23][0], 0.7)
        self.assertEqual(meta["reason"], "declared_athlete_location")

    def test_continuity_handles_multiple_poses_and_abstains_on_tie(self):
        tracker = AthleteTracker({"x": 0, "y": 0, "width": 1, "height": 1}, 1000, 500)
        selected, meta = tracker.select([pose(0.3)], 0)
        self.assertIsNotNone(selected)
        selected, meta = tracker.select([pose(0.75), pose(0.31)], 83)
        self.assertEqual(selected[23][0], 0.31)
        self.assertTrue(meta["selected_from_multiple"])
        selected, meta = tracker.select([pose(0.32), pose(0.325)], 166)
        self.assertIsNone(selected)
        self.assertEqual(meta["reason"], "ambiguous_athlete_match")

    def test_full_frame_initial_ambiguity_and_reacquisition_epoch(self):
        tracker = AthleteTracker({"x": 0, "y": 0, "width": 1, "height": 1}, 1000, 500)
        self.assertIsNone(tracker.select([pose(0.3), pose(0.7)], 0)[0])
        _, first = tracker.select([pose(0.3)], 83)
        _, second = tracker.select([pose(0.3)], 1000)
        self.assertGreater(second["epoch"], first["epoch"])
        unknown = AthleteTracker({"x": 0, "y": 0, "width": 1, "height": 1}, 1000, 500, "unknown")
        self.assertIsNone(unknown.select([pose(0.3), pose(0.7)], 0)[0])

    def test_standing_is_not_guard_and_later_guard_is_found(self):
        frames = [frame(t, 0.2, 178) for t in range(0, 1000, 83)]
        self.assertIsNone(find_guard_baseline(frames))
        frames += [frame(t) for t in range(1500, 2500, 83)]
        guard = find_guard_baseline(frames)
        self.assertGreaterEqual(guard["start_ms"], 1500)

    def test_onset_precedes_large_expansion_and_identity_break_drops_rep(self):
        frames = [frame(t) for t in range(0, 1000, 100)]
        frames += [frame(1000, 0.95), frame(1100, 1.25), frame(1200, 1.5)]
        frames += [frame(t) for t in range(1300, 1900, 100)]
        candidates, _ = proposals(frames, baseline=0.7, start_after_ms=500)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["movement_onset_ms"], 900)
        for f in frames:
            if f["time_ms"] >= 1300:
                f["track_epoch"] = 2
        self.assertEqual(proposals(frames, baseline=0.7, start_after_ms=500)[0], [])


if __name__ == "__main__":
    unittest.main()
