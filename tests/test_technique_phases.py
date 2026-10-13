import unittest

from fencecoach.phase_metrics import rep_phases
from fencecoach.technique import evaluate_lunges
from fencecoach.video_pipeline import find_guard_baseline

PROFILE = {
    "camera_view": "side",
    "front_leg": "right",
    "weapon_arm": "right",
    "facing": "right",
    "scene_type": "solo",
    "camera_motion": "fixed",
}


def pose_frame(time, front_knee=100, rear_knee=170, hip_x=0.5):
    p = [[0.5, 0.5, 0, 0.99, 0.99] for _ in range(33)]
    for i in (11, 12):
        p[i][:2] = [hip_x, 0.3]
    for i in (23, 24):
        p[i][:2] = [hip_x, 0.6]
    for i in (27, 31):
        p[i][:2] = [0.3, 0.9]
    for i in (28, 32):
        p[i][:2] = [0.7, 0.9]
    p[14][:2], p[16][:2] = [hip_x + 0.1, 0.3], [hip_x + 0.2, 0.3]
    return {
        "time_ms": time,
        "landmarks": p,
        "quality": 0.99,
        "track_epoch": 0,
        "features": {
            "torso_pixels": 180,
            "torso_tilt": 0,
            "stance_ratio": 1.0,
            "hip_x_torso": hip_x * 1000 / 180,
            "right_knee_angle": front_knee,
            "left_knee_angle": rear_knee,
            "right_elbow_angle": 170,
        },
    }


def result(frames):
    return {
        "width": 1000,
        "height": 600,
        "duration_ms": 3000,
        "frames": frames,
        "capture_profile": PROFILE,
        "quality_gate": {"coaching_allowed": True, "issues": []},
    }


class TechniquePhaseTests(unittest.TestCase):
    def test_one_bad_frame_cannot_become_a_knee_correction(self):
        frames = [
            pose_frame(600),
            pose_frame(900),
            pose_frame(1000, 145),
            pose_frame(1100),
            pose_frame(1800),
        ]
        evaluation = evaluate_lunges(
            result(frames), [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}]
        )
        rep = evaluation["reps"][0]
        self.assertEqual(rep["measurements"]["front_knee_angle"]["value"], 100)
        self.assertEqual(rep["measurements"]["front_knee_angle"]["summary_method"], "phase_median")
        self.assertFalse(any(f["rule"] == "front_knee_shallow" for f in rep["findings"]))

    def test_single_visible_sample_withholds_a_correction(self):
        frames = [pose_frame(600), pose_frame(1000, 140), pose_frame(1800)]
        evaluation = evaluate_lunges(
            result(frames), [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}]
        )
        self.assertFalse(evaluation["findings"])
        self.assertEqual(evaluation["suppressed_findings"][0]["sample_support"]["sample_count"], 1)

    def test_consistent_knee_observation_has_multiple_supporting_frames(self):
        frames = [
            pose_frame(600),
            pose_frame(900, 135),
            pose_frame(1000, 140),
            pose_frame(1100, 138),
            pose_frame(1800),
        ]
        evaluation = evaluate_lunges(
            result(frames), [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}]
        )
        finding = next(f for f in evaluation["findings"] if f["rule"] == "front_knee_shallow")
        self.assertEqual(finding["measurement"]["value"], 138)
        self.assertEqual(finding["sample_support"]["agreeing_samples"], 3)

    def test_bookmarks_without_pose_are_unavailable_not_a_pass(self):
        evaluation = evaluate_lunges(
            result([]), [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}]
        )
        self.assertEqual(evaluation["status"], "unavailable")
        self.assertEqual(evaluation["reps"][0]["status"], "unavailable")
        self.assertFalse(evaluation["reps"][0]["geometry_available"])

    def test_hold_and_recovery_peak_medians_use_only_their_phases(self):
        frames = [pose_frame(600, 160)]
        frames += [pose_frame(t, 95, 170) for t in range(1000, 1500, 100)]
        frames += [
            pose_frame(1500, 130, 110, 0.47),
            pose_frame(1600, 150, 80, 0.44),
            pose_frame(1700, 155, 100, 0.40),
            pose_frame(1800, 155, 110, 0.37),
        ]
        phases = rep_phases(
            frames, {"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}, PROFILE, 1000, 600
        )
        self.assertTrue(phases["hold_detected"])
        self.assertEqual(phases["recovery_onset_ms"], 1500)
        self.assertEqual(
            phases["phases"]["lunge_hold"]["measurements"]["front_knee_angle"]["value"], 95
        )
        peak = phases["phases"]["recovery_peak"]
        self.assertEqual((peak["start_ms"], peak["end_ms"]), (1500, 1700))
        self.assertEqual(peak["measurements"]["rear_knee_angle"]["value"], 100)

    def test_declared_facing_conflict_withholds_directional_metrics(self):
        data = result([pose_frame(t) for t in range(600, 1900, 100)])
        evaluation = evaluate_lunges(
            data, [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}], {"facing": "left"}
        )
        self.assertIn("warning", evaluation["capture_requirements"])
        self.assertNotIn("front_knee_ahead_of_toe", evaluation["reps"][0]["measurements"])

    def test_initial_guard_checkbox_does_not_override_walk_in(self):
        frames = [pose_frame(t, 178, 178) for t in range(0, 1400, 100)]
        for f in frames:
            f["features"]["stance_ratio"] = 0.2
        frames += [pose_frame(t, 110) for t in range(1500, 2600, 100)]
        guard = find_guard_baseline(frames, initial_guard_confirmed=True)
        self.assertEqual(guard["start_ms"], 1500)
        self.assertEqual(guard["method"], "auto_detected_stable_guard")

    def test_torso_scale_change_is_not_hip_translation(self):
        frames = [pose_frame(t, 110) for t in range(0, 1000, 100)]
        for index, f in enumerate(frames):
            scale = 180 + index * 8
            f["features"].update(torso_pixels=scale, hip_x_torso=500 / scale)
        self.assertIsNotNone(find_guard_baseline(frames))

    def test_legacy_pose_without_scale_does_not_crash_footwork(self):
        from fencecoach.motion import footwork_proposals

        frames = [pose_frame(t) for t in range(0, 1000, 100)]
        for f in frames:
            del f["features"]["hip_x_torso"]
        self.assertEqual(footwork_proposals(frames, 1.0, PROFILE), [])

    def test_coach_source_exposes_the_requested_phase_medians(self):
        from fencecoach.coach.technique_evidence import selected_evaluation
        from fencecoach.schemas import CoachRequest

        frames = [pose_frame(600)] + [pose_frame(t, rear_knee=120) for t in range(900, 1900, 100)]
        evaluation = evaluate_lunges(
            result(frames), [{"onset_ms": 600, "start_ms": 1000, "end_ms": 1800}]
        )
        request = CoachRequest(
            session_id="test",
            question="What is my lunge knee angle in rep 1?",
            technique_evaluation=evaluation,
        )
        source = selected_evaluation(request)
        phases = source["rep_measurements"][0]["phase_medians"]
        self.assertIn("lunge_finish", phases)
        self.assertEqual(phases["lunge_finish"]["medians"]["front_knee_angle"]["value"], 100)
        self.assertIn("rep-phase", source["measurement_policy"])


if __name__ == "__main__":
    unittest.main()
