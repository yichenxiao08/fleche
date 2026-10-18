"""Next-phase contracts: semantic packets, retrieval scope and clarification carry-over."""

import unittest
from unittest.mock import patch

from fencecoach.coach.claim_check import filter_reply
from fencecoach.coach.packet_meaning import assessments, describe
from fencecoach.coach.quality_metrics import repetition
from fencecoach.coach.router import retry_after
from fencecoach.coach.turn_packet import _teaching, build_packet, resolve_scope
from fencecoach.schemas import CoachRequest, KnowledgeSource
from tests.test_packet_core import snapshot


class PacketMeaningTests(unittest.TestCase):
    def test_retryinfo_delay_and_consecutive_value_metric(self):
        self.assertEqual(retry_after(RuntimeError("{'retryDelay': '17s'}")), 17)
        rows = [
            {
                "turn": i,
                "answer": "The measured elbow angle is 168.1 degrees.",
                "packet": {"measurements": [{"value": 168.1}]},
            }
            for i in (1, 2)
        ]
        self.assertEqual(repetition(rows)["repeated_value_pairs"], 1)

    def test_citation_contract_removes_only_unmatched_number(self):
        packet = {
            "measurements": [{"evidence_id": "elbow", "value": 168.1, "rep": 2}],
            "general_guidance": [],
        }
        safe = {
            "type": "claim",
            "text": "Your elbow measured 168.1 degrees in rep 2.",
            "evidence_ids": ["elbow"],
            "library_ids": [],
        }
        bad = {**safe, "text": "Your speed was 1.37 m/s."}
        filtered, checks = filter_reply({"sentences": [safe, bad]}, packet)
        self.assertEqual(filtered, safe["text"])
        self.assertEqual(checks["removed"], 1)
        self.assertEqual(checks["sentences"][1]["reasons"], ["number_not_in_cited_evidence"])

    def test_technique_requires_an_authored_cue_not_stem_overlap(self):
        packet = {"general_guidance": [{"source_id": "guide", "text": "Reach toward the target."}]}
        row = {
            "type": "claim",
            "claim_kind": "technique",
            "text": "As general practice: Reach toward the target.",
            "cue": "Reach toward the target.",
            "library_ids": ["guide"],
            "library_quotes": [{"source_id": "guide", "quote": "Reach toward the target."}],
        }
        self.assertEqual(filter_reply({"sentences": [row]}, packet)[1]["removed"], 0)
        row["cue"] = "Guarantee the touch."
        self.assertTrue(filter_reply({"sentences": [row]}, packet)[1]["all_removed"])

    def test_clarification_and_acknowledgment_bypass_claim_checks(self):
        for kind, text in [
            ("clarification", "Your arm or recovery?"),
            ("acknowledgment", "Got it."),
            ("reset", "Let's start fresh."),
        ]:
            answer, checks = filter_reply({"sentences": [{"type": kind, "text": text}]}, {})
            self.assertEqual(answer, text)
            self.assertEqual(checks["removed"], 0)

    def test_citing_wrong_existing_row_does_not_authorize_number(self):
        packet = {
            "measurements": [
                {"evidence_id": "a", "value": 168.1},
                {"evidence_id": "b", "value": 140.2},
            ]
        }
        _, checks = filter_reply(
            {
                "sentences": [
                    {"type": "claim", "text": "The elbow is 140.2 degrees.", "evidence_ids": ["a"]}
                ]
            },
            packet,
        )
        self.assertIn("number_not_in_cited_evidence", checks["sentences"][0]["reasons"])

    def test_display_is_the_only_precision_supplied(self):
        row = describe({"feature": "weapon_arm_direction", "value": 18.153, "unit": "deg"})
        self.assertEqual(row["value"], 18.2)
        self.assertEqual(row["display"], "18.2 deg")
        self.assertIn("Elbow bend", row["does_not_indicate"])
        duration = describe(
            {"feature": "estimated_active_recovery_time", "value": 0.1, "unit": "s"}
        )
        self.assertIn("onset to guard", duration["definition"])
        self.assertIn("onset timestamp", duration["does_not_indicate"])

    def test_narrative_reference_and_unapproved_rules_never_grade(self):
        row = describe(
            dict(
                topic="arm",
                feature="weapon_elbow_angle",
                value=160,
                unit="deg",
                phase="lunge_finish",
                rep=1,
                evidence_id="a",
            )
        )
        guide = {
            "source_id": "draft",
            "text": "Research range 150 to 170 degrees.",
            "approved": False,
            "assessment_rules": [dict(topic="arm", minimum=155, maximum=165)],
        }
        result = assessments(["arm"], [row], [guide])[0]
        self.assertEqual(result["status"], "relative_only")
        self.assertEqual(result["basis"], [])

    def test_retrieval_filters_recovery_from_arm_and_lunge_from_fleche(self):
        docs = [
            KnowledgeSource(source_id=name + "#chunk-0", source=name, text=text)
            for name, text in [
                ("recovery_basics.md", "Recovery means returning to guard."),
                ("lunge_arm_roles.md", "Weapon arm points toward target."),
                ("fleche_reference.md", "Fleche is a separate movement."),
                ("lunge_teaching_reference.md", "Lunge begins with arm extension."),
            ]
        ]
        with patch("fencecoach.coach.turn_packet.search_knowledge", return_value=docs):
            arm = _teaching("arm angle", topics=["arm"])
            fleche = _teaching("fleche", topics=["fleche"], movement="fleche")
        self.assertEqual([d["source_id"] for d in arm], ["lunge_arm_roles.md#chunk-0"])
        self.assertEqual([d["source_id"] for d in fleche], ["fleche_reference.md#chunk-0"])

    def test_non_coaching_does_not_erase_topic_and_restart_does(self):
        req = CoachRequest(session_id="clip", question="my arm in rep 2")
        state = resolve_scope(req, snapshot())
        for question, kind in [("thanks", "acknowledgment"), ("hello", "greeting")]:
            req.question, req.dialogue_state = question, state
            state = resolve_scope(req, snapshot())
            self.assertEqual(state.turn_type, kind)
            self.assertEqual(state.topics, ["arm"])
            self.assertIsNone(state.open_clarifying_question)
        req.question, req.dialogue_state = "start over", state
        state = resolve_scope(req, snapshot())
        self.assertEqual(state.topics, [])

    def test_cache_reuses_evidence_without_retrieval_and_marks_assumption(self):
        req = CoachRequest(session_id="clip", question="my arm in rep 2")
        state = resolve_scope(req, snapshot())
        packet = build_packet(req, state, snapshot())
        state.last_packet = packet
        req.question, req.dialogue_state = "why does that matter?", state
        state = resolve_scope(req, snapshot())
        with patch(
            "fencecoach.coach.turn_packet.search_knowledge",
            side_effect=AssertionError("unneeded retrieval"),
        ):
            followup = build_packet(req, state, snapshot())
        self.assertTrue(followup["evidence_reused"])
        self.assertEqual(packet["measurements"], followup["measurements"])
        self.assertIn("arm", followup["resolution"]["assumption"])


if __name__ == "__main__":
    unittest.main()
