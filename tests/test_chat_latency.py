import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk

from fencecoach.coach.graph import run_coach
from fencecoach.coach.grounding import unsupported_claims
from fencecoach.coach.latency import compact_guidance, compact_measurements
from fencecoach.schemas import CoachRequest, MetricObservation
from fencecoach.settings import settings


class StreamingModel:
    model = "synthetic-latency-test"

    def __init__(self):
        self.read = 0
        self.closed = False
        self.options = {}

    def bind(self, **kwargs):
        self.options.update(kwargs.get("options", {}))
        return self

    def stream(self, messages):
        try:
            for text in (
                "Try a slow set with a deliberate reset between attempts. ",
                "At 2.0 seconds, the tracked left knee angle is 110 degrees. ",
                "Repeat this drill toward the same target because it helps make the attempts comparable. ",
                "Compare the same phase on your next attempt. ",
            ):
                self.read += 1
                yield AIMessageChunk(content=text)
        finally:
            self.closed = True

    def invoke(self, messages):
        return AIMessage(content="".join(chunk.content for chunk in self.stream(messages)))


# This fixture checks the legacy free-prose writer's bounded stream and publication guard.
# These contracts exercise the retained COACH_CORE=old implementation.
@patch.object(settings, "coach_core", "old")
@patch.object(settings, "fencecoach_verified_dialogue", False)
class ChatLatencyTests(unittest.TestCase):
    def test_only_complete_checked_answer_is_published_and_stream_is_closed(self):
        model = StreamingModel()
        request = CoachRequest(
            session_id="latency-test",
            question="Review my lunge",
            metrics=[
                MetricObservation(
                    metric_id="rep-1-knee",
                    name="left_knee_angle_at_peak",
                    value=110,
                    unit="deg",
                    confidence=0.9,
                    start_ms=2000,
                    end_ms=2000,
                )
            ],
        )
        published = []
        run = run_coach(request, "local", model=model, on_text=published.append)
        self.assertEqual(model.read, 4)
        self.assertTrue(model.closed)
        self.assertLessEqual(model.options["num_predict"], 160)
        self.assertIn("same phase", run.report.summary)
        self.assertEqual(published, [run.report.summary])

    def test_compaction_preserves_ids_values_and_confirmed_side(self):
        rows = [
            {
                "metric_id": str(i),
                "name": name,
                "value": value,
                "unit": "deg",
                "confidence": 0.9,
                "start_ms": i * 1000,
            }
            for i, (name, value) in enumerate(
                [
                    ("left_elbow_angle_at_peak", 90),
                    ("right_elbow_angle_at_peak", 160),
                    ("right_elbow_angle_at_peak", 175),
                    ("left_knee_angle_at_peak", 110),
                ]
            )
        ]
        chosen = compact_measurements(rows, "my arm extension", {"weapon_arm": "right"})
        self.assertEqual([row["value"] for row in chosen], [160, 175])
        self.assertEqual([row["metric_id"] for row in chosen], ["1", "2"])

    def test_guidance_is_shortened_at_a_sentence_boundary(self):
        self.assertEqual(
            compact_guidance("Complete sentence. Another longer sentence.", 25),
            "Complete sentence.",
        )

    def test_unsupported_rotation_claim_is_rejected(self):
        self.assertTrue(
            unsupported_claims(
                "The knee angle indicates over-rotation. Keep the knee within a neutral range to avoid injury."
            )
        )


if __name__ == "__main__":
    unittest.main()
