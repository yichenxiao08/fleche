"""Rep selectors change coverage without replacing the active movement subject."""

import json
import unittest
from pathlib import Path

from fencecoach.coach.answer_review import cited_subject_issues
from fencecoach.coach.dialogue_state import resolve_turn
from fencecoach.coach.evidence_packet import build_packet
from fencecoach.coach.intent import question_phases
from fencecoach.coach.technique_evidence import (
    current_session_context,
    question_scoped_session_context,
    session_evidence_context,
)
from fencecoach.schemas import CoachRequest, ConversationMessage, DialogueState

FIXTURE = Path(__file__).resolve().parents[1] / "evals/coach_audit/current.json"


def request():
    return CoachRequest.model_validate_json(FIXTURE.read_text())


def turn(query, question, state=None):
    query = query.model_copy(update={"question": question, "dialogue_state": state})
    resolved, state = resolve_turn(query)
    return query.model_copy(update={"question": resolved, "dialogue_state": state}), state


def observations(query):
    return [
        record
        for unit in build_packet(query).units
        if unit.kind == "observation"
        for record in unit.records
        if record.get("feature")
    ]


class DialogueRepScopeTests(unittest.TestCase):
    def test_unmapped_temporal_qualifier_preserves_named_movement_phase(self):
        self.assertEqual(
            question_phases("How fast was my return to guard after the lunge?"),
            {"returned_guard"},
        )
        self.assertEqual(
            question_phases("How was my arm recovery after the lunge?"),
            {"active_recovery", "recovery_peak", "returned_guard"},
        )

    def test_requested_finish_does_not_substitute_hold_and_reports_missing_rep(self):
        query, _ = turn(
            request(), "How was my non-sword elbow during the lunge finish in all reps?"
        )
        packet = build_packet(query)
        rows = observations(query)
        self.assertTrue(rows)
        self.assertTrue(all(row["phase"] == "lunge_finish" for row in rows))
        self.assertEqual({row["feature"] for row in rows}, {"non_weapon_elbow_angle"})
        self.assertEqual({row["rep"] for row in rows}, {1, 2, 3, 4, 5, 7, 8})
        gaps = " ".join(unit.text for unit in packet.units if unit.kind == "gap")
        self.assertIn("rep 6", gaps)
        scoped = json.loads(question_scoped_session_context(query))
        rep_six = next(rep for rep in scoped["per_rep_measurements"] if rep["rep"] == 6)
        self.assertEqual(rep_six["reference_comparisons"], [])

    def test_legacy_peak_observations_remain_unphased_and_do_not_replace_finish(self):
        query = request()
        peak = next(metric for metric in query.metrics if metric.name == "left_elbow_angle_at_peak")
        inventory = json.loads(current_session_context(query))
        record = next(
            row for row in inventory["session_measurements"] if row["evidence_id"] == peak.metric_id
        )
        self.assertIsNone(record["phase"])
        self.assertEqual(record["value"], peak.value)
        self.assertEqual(cited_subject_issues(inventory, [peak.metric_id], [peak.name]), [])
        self.assertIn(
            "The cited feature belongs to a different phase than the athlete asked about.",
            cited_subject_issues(
                inventory, [peak.metric_id], [peak.name], requested_phases=["lunge_finish"]
            ),
        )
        broad = query.model_copy(update={"question": "How was my non-sword arm here?"})
        scoped = json.loads(question_scoped_session_context(broad))
        self.assertIn(
            peak.metric_id, {row["evidence_id"] for row in scoped["session_measurements"]}
        )
        exact = session_evidence_context(query, [peak.name], ["lunge_finish"])
        self.assertEqual(exact["session_measurements"], [])

    def test_named_hold_keeps_the_actual_hold_record(self):
        query, state = turn(request(), "How was my non-sword elbow during lunge hold in rep 6?")
        rows = observations(query)
        self.assertEqual(state.phases, ["lunge_hold"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["phase"], "lunge_hold")
        self.assertEqual(rows[0]["feature"], "non_weapon_elbow_angle")
        self.assertEqual(rows[0]["rep"], 6)
        self.assertEqual(rows[0]["value"], 174.7)

    def test_timing_operation_selects_the_measured_phase_without_a_recovery_subject(self):
        for question, feature, phase, value in (
            (
                "How fast was I during active recovery in rep 3?",
                "estimated_active_recovery_time",
                "active_recovery",
                251,
            ),
            (
                "How long was the action during lunge drive in rep 3?",
                "action_to_lunge_time",
                "lunge_drive",
                1253,
            ),
        ):
            with self.subTest(question=question):
                query = request()
                rep = next(
                    rep for rep in query.technique_evaluation["reps"] if rep["rep_number"] == 3
                )
                rep["measurements"][feature] = {
                    "value": value,
                    "unit": "ms",
                    "phase": phase,
                    "time_ms": 6100,
                    "note": "Synthetic phase-labeled timing record.",
                }
                query, _ = turn(query, question)
                rows = observations(query)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["feature"], feature)
                self.assertEqual(rows[0]["phase"], phase)
                self.assertEqual(rows[0]["value"], value / 1000)
                self.assertEqual(rows[0]["evidence_id"], f"rep:3:measurement:{feature}")
                scoped = json.loads(question_scoped_session_context(query))
                self.assertIn(feature, scoped["per_rep_measurements"][0]["measures"])

    def test_legacy_recovery_interval_keeps_its_definition_without_inventing_a_phase(self):
        query, _ = turn(request(), "How fast was I during active recovery in rep 3?")
        rows = observations(query)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature"], "estimated_active_recovery_time")
        self.assertEqual(rows[0]["value"], 0.167)
        self.assertIsNone(rows[0]["phase"])
        self.assertIn("excludes the preceding hold", rows[0]["meaning"])
        self.assertEqual(
            cited_subject_issues(
                json.loads(current_session_context(query)),
                [rows[0]["evidence_id"]],
                ["estimated_active_recovery_time"],
                requested_phases=["active_recovery"],
            ),
            [],
        )

    def test_conflicting_declared_timing_phase_cannot_be_replaced_with_lunge_time(self):
        query = request()
        rep = next(rep for rep in query.technique_evaluation["reps"] if rep["rep_number"] == 3)
        rep["measurements"]["estimated_active_recovery_time"]["phase"] = "lunge_drive"
        query, _ = turn(query, "How fast was I during active recovery in rep 3?")
        self.assertEqual(observations(query), [])
        self.assertTrue(any(unit.kind == "gap" for unit in build_packet(query).units))

    def test_scope_only_widening_keeps_subject_phase_and_role(self):
        for subject, topic, feature, roles in (
            ("torso", "torso", "projected_torso_tilt", []),
            ("rear leg", "rear_leg", "rear_knee_angle", []),
            ("non-sword arm", "arm", "non_weapon_arm_direction", ["non_weapon"]),
        ):
            for selector in ("all reps", "each repetition", "every lunge", "all of my reps"):
                with self.subTest(subject=subject, selector=selector):
                    query, state = turn(
                        request(), f"How was my {subject} at the lunge finish in rep 3?"
                    )
                    query, state = turn(query, f"What about {selector}?", state)
                    self.assertEqual(state.topics, [topic])
                    self.assertEqual(set(state.phases), {"finish", "lunge_finish"})
                    self.assertEqual(state.arm_roles, roles)
                    self.assertEqual(state.rep_numbers, [])
                    self.assertTrue(state.all_reps)
                    rows = observations(query)
                    available = {
                        rep["rep_number"]
                        for rep in query.technique_evaluation["reps"]
                        if feature
                        in rep.get("phases", {}).get("lunge_finish", {}).get("measurements", {})
                    }
                    self.assertEqual(available, {1, 2, 3, 4, 5, 7, 8})
                    self.assertEqual({row["rep"] for row in rows}, available)
                    self.assertEqual({row["feature"] for row in rows}, {feature})
                    self.assertTrue(all(row.get("phase") in state.phases for row in rows))

    def test_all_scope_survives_neutral_followup_then_specific_rep_replaces_it(self):
        query, state = turn(request(), "How was my torso at starting guard in rep 3?")
        query, state = turn(query, "What about all repetitions?", state)
        query, state = turn(query, "Give me the measurements.", state)
        self.assertTrue(state.all_reps)
        self.assertEqual(state.rep_numbers, [])
        self.assertEqual(state.topics, ["torso"])
        self.assertEqual(set(state.phases), {"starting_guard"})
        self.assertEqual(len({row["rep"] for row in observations(query)}), 8)
        query, state = turn(query, "And rep 2?", state)
        self.assertFalse(state.all_reps)
        self.assertEqual(state.rep_numbers, [2])
        query, state = turn(query, "Can you explain that?", state)
        self.assertFalse(state.all_reps)
        self.assertEqual(state.rep_numbers, [2])
        self.assertEqual(state.topics, ["torso"])
        self.assertEqual(set(state.phases), {"starting_guard"})
        self.assertEqual({row["rep"] for row in observations(query)}, {2})

    def test_initial_all_scope_does_not_leak_into_later_specific_rep(self):
        query, state = turn(request(), "Analyze my rear leg at the lunge finish in all reps")
        self.assertTrue(state.all_reps)
        query, state = turn(query, "What about reps 2 and 4?", state)
        self.assertFalse(state.all_reps)
        self.assertEqual(state.rep_numbers, [2, 4])
        self.assertEqual({row["rep"] for row in observations(query)}, {2, 4})
        self.assertEqual(state.topics, ["rear_leg"])

    def test_genuine_overall_request_resets_narrow_subject(self):
        for overall in ("Overall, how did I do?", "Review the whole session", "How did I do?"):
            with self.subTest(overall=overall):
                query, state = turn(request(), "How was my non-sword arm in rep 3?")
                query, state = turn(query, "What about every rep?", state)
                query, state = turn(query, overall, state)
                self.assertNotIn("non-sword arm", query.question)
                self.assertNotIn("arm", state.topics)
                self.assertEqual(state.rep_numbers, [])
                self.assertFalse(state.all_reps)

    def test_new_named_subject_and_all_scope_replace_old_subject(self):
        query, state = turn(request(), "How was my non-sword arm in rep 3?")
        query, state = turn(query, "What about my torso at starting guard in all reps?", state)
        self.assertEqual(state.topics, ["torso"])
        self.assertEqual(state.arm_roles, [])
        self.assertEqual(set(state.phases), {"starting_guard"})
        self.assertEqual(state.rep_numbers, [])
        self.assertTrue(state.all_reps)
        rows = observations(query)
        self.assertEqual({row["feature"] for row in rows}, {"projected_torso_tilt"})
        self.assertEqual(len({row["rep"] for row in rows}), 8)

    def test_phase_scope_update_keeps_subject_coverage_and_role(self):
        for subject, topic, feature, roles in (
            ("torso", "torso", "projected_torso_tilt", []),
            ("rear leg", "rear_leg", "rear_knee_angle", []),
            ("non-sword arm", "arm", "non_weapon_arm_direction", ["non_weapon"]),
        ):
            for phase_word in ("at", "during"):
                with self.subTest(subject=subject, phase_word=phase_word):
                    query, state = turn(
                        request(), f"How was my {subject} during the lunge finish in rep 3?"
                    )
                    self.assertEqual(set(state.phases), {"finish", "lunge_finish"})
                    query, state = turn(query, "What about every rep?", state)
                    query, state = turn(query, f"And {phase_word} the recovery peak?", state)
                    self.assertEqual(state.topics, [topic])
                    self.assertEqual(state.arm_roles, roles)
                    self.assertEqual(set(state.phases), {"recovery_peak"})
                    self.assertTrue(state.all_reps)
                    rows = observations(query)
                    self.assertEqual(len({row["rep"] for row in rows}), 8)
                    self.assertEqual({row["feature"] for row in rows}, {feature})
                    self.assertEqual({row["phase"] for row in rows}, {"recovery_peak"})
                    query, state = turn(query, "And rep 2?", state)
                    self.assertFalse(state.all_reps)
                    self.assertEqual(state.rep_numbers, [2])
                    rows = observations(query)
                    self.assertEqual({row["rep"] for row in rows}, {2})
                    self.assertEqual({row["feature"] for row in rows}, {feature})
                    self.assertEqual({row["phase"] for row in rows}, {"recovery_peak"})
                    query, state = turn(query, "And my active recovery?", state)
                    self.assertEqual(state.topics, ["recovery"])
                    self.assertEqual(state.arm_roles, [])

    def test_explicit_rep_coverage_moves_general_subject_to_session(self):
        query, state = turn(request(), "In general, how should I hold my non-sword arm?")
        self.assertEqual(state.scope, "general")
        query, state = turn(query, "What about all reps?", state)
        self.assertEqual(state.scope, "session")
        self.assertEqual(state.topics, ["arm"])
        self.assertEqual(state.arm_roles, ["non_weapon"])
        self.assertTrue(state.all_reps)
        self.assertTrue(observations(query))

    def test_all_scope_roundtrip_and_user_history_replay_agree(self):
        questions = (
            "How was my torso at starting guard in rep 3?",
            "What about every rep?",
            "Give me the measurements.",
        )
        query, state = turn(request(), questions[0])
        query, state = turn(query, questions[1], state)
        restored = DialogueState.model_validate_json(state.model_dump_json())
        query, persisted = turn(query, questions[2], restored)
        replay = request().model_copy(
            update={
                "question": questions[2],
                "conversation_history": [
                    ConversationMessage(role="user", content=question) for question in questions[:2]
                ],
            }
        )
        resolved, replayed = resolve_turn(replay)
        self.assertEqual(replayed.model_dump(), persisted.model_dump())
        self.assertTrue(replayed.all_reps)
        self.assertEqual(replayed.topics, ["torso"])
        self.assertEqual(set(replayed.phases), {"starting_guard"})
        self.assertEqual(resolved, query.question)


if __name__ == "__main__":
    unittest.main()
