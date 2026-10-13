"""Evidence invariants across free-form questions and provider context encoding."""

import json
import unittest

from fencecoach.coach.latency import (
    expand_session_context,
    local_overview_context,
    local_session_context,
)
from fencecoach.coach.technique_evidence import (
    baseline_context,
    current_session_context,
    session_evidence_context,
)
from fencecoach.schemas import CoachRequest


def make_request(question="How did I do?"):
    references = [
        {
            "job_id": "approved-source",
            "rep_number": 4,
            "revision": 3,
            "stated_corrections": "Intentional shorter reach",
        }
    ]
    reps = []
    # An arbitrary feature demonstrates that context does not depend on known topic regexes.
    for number in range(1, 42):
        reps.append(
            {
                "rep_number": number,
                "lunge_ms": number * 2000,
                "measurements": {
                    "target_alignment_offset": {
                        "value": number / 100,
                        "unit": "leg_lengths",
                        "phase": "lunge_hold",
                        "note": "Normalized target offset",
                    },
                    "front_foot_lift_to_stable_finish": {"value": 399, "unit": "ms"},
                },
                "phases": {
                    "lunge_hold": {
                        "start_ms": number * 2000,
                        "end_ms": number * 2000 + 200,
                        "sample_count": 3,
                        "method": "phase median",
                        "measurements": {
                            "target_alignment_offset": {
                                "value": number / 100,
                                "unit": "leg_lengths",
                                "range": [0.01, 0.42],
                            }
                        },
                    }
                },
                "drill_benchmarks": {
                    "timing": {
                        "category": "fast",
                        "duration_seconds": 0.399,
                        "event_definition": "front-foot lift to stable finish",
                    }
                },
                "reference_comparison": {
                    "status": "available",
                    "references": references,
                    "comparison_scope": "projected side-view comparison",
                    "rows": [
                        {
                            "metric": "target_alignment_offset",
                            "phase": "finish",
                            "unit": "leg_lengths",
                            "current": number / 100,
                            "reference_range": [0.01, 0.05],
                            "direction": "higher",
                        }
                    ],
                    "coaching_priorities": [],
                },
                "findings": [],
                "unavailable": [],
            }
        )
    return CoachRequest(
        session_id="new-session",
        question=question,
        technique_evaluation={
            "coaching_mode": "reference_comparison",
            "reps": reps,
            "reference_comparison": {"status": "available", "references": references},
        },
    )


class SessionEvidenceContractTests(unittest.TestCase):
    def test_question_wording_does_not_filter_the_canonical_inventory(self):
        for question in (
            "what about my target alignment",
            "and that on the last one?",
            "compare my legs and torso",
            "can I change the drill?",
        ):
            with self.subTest(question=question):
                packet = json.loads(current_session_context(make_request(question)))
                self.assertEqual(len(packet["per_rep_measurements"]), 41)
                self.assertTrue(
                    all(
                        "target_alignment_offset" in rep["measures"]
                        for rep in packet["per_rep_measurements"]
                    )
                )

    def test_local_compaction_retains_the_entire_evidence_packet(self):
        snapshot = current_session_context(make_request())
        self.assertEqual(
            expand_session_context(local_session_context(snapshot)), json.loads(snapshot)
        )

    def test_reference_tool_preserves_all_reps_and_reference_provenance(self):
        data = baseline_context(make_request(), "target_alignment_offset", "finish")
        self.assertEqual(data["matching_count"], 41)
        self.assertEqual(data["comparisons"][-1]["rep"], 41)
        reference = data["comparisons"][0]["reference_context"]["references"][0]
        self.assertEqual(reference["revision"], 3)
        self.assertEqual(reference["stated_corrections"], "Intentional shorter reach")
        self.assertIsNone(data["comparisons"][0]["supported_change"])

    def test_reference_scope_filters_cannot_substitute_another_feature_or_phase(self):
        data = baseline_context(make_request(), "target_alignment_offset", "finish", 17)
        self.assertEqual([row["rep"] for row in data["comparisons"]], [17])
        self.assertEqual(baseline_context(make_request(), "unknown_feature")["matching_count"], 0)
        self.assertEqual(baseline_context(make_request(), phase="onset")["matching_count"], 0)

    def test_benchmark_precision_and_phase_measurement_units_are_retained(self):
        rep = json.loads(current_session_context(make_request()))["per_rep_measurements"][0]
        self.assertEqual(rep["measures"]["front_foot_lift_to_stable_finish"]["value"], 0.399)
        self.assertEqual(rep["drill_benchmarks"]["timing"]["category"], "fast")
        phase = rep["phases"]["lunge_hold"]
        self.assertEqual(phase["units"]["target_alignment_offset"], "leg_lengths")
        self.assertEqual(phase["method"], "phase median")

    def test_local_inventory_preserves_all_features_reps_and_reference_results(self):
        packet = expand_session_context(
            local_overview_context(current_session_context(make_request()))
        )
        self.assertEqual(len(packet["per_rep_measurements"]), 41)
        column = packet["measure_columns"].index("target_alignment_offset")
        last = packet["per_rep_measurements"][-1]
        self.assertEqual(last["values"][column], 0.41)
        self.assertEqual(
            packet["phase_features_available"]["lunge_hold"]["target_alignment_offset"],
            "leg_lengths",
        )
        self.assertEqual(last["reference_comparisons_available"], 1)
        self.assertIn("get_technique_evaluation", packet["detail_access"])

    def test_detail_tool_filters_arbitrary_features_without_question_classification(self):
        packet = session_evidence_context(
            make_request("and what about that?"), ["target_alignment_offset"], ["lunge_hold"], [39]
        )
        self.assertEqual([rep["rep"] for rep in packet["per_rep_measurements"]], [39])
        rep = packet["per_rep_measurements"][0]
        self.assertEqual(set(rep["measures"]), {"target_alignment_offset"})
        self.assertEqual(set(rep["phases"]), {"lunge_hold"})
        self.assertEqual(rep["reference_comparisons"][0]["phase"], "finish")


if __name__ == "__main__":
    unittest.main()
