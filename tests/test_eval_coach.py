"""Evaluation independence, artifact preservation, deadlines and switch coverage."""

import json
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fencecoach.schemas import CoachRequest
from scripts.coach_eval_oracle import (
    check_answer,
    expectation,
    raw_records,
    scenarios,
    weapon_target_verdict,
)
from scripts.eval_coach import (
    ROOT,
    _run_turn,
    before_after_table,
    bounded_turn,
    forced_switch_scenario,
    load_or_create,
    save_artifact,
    summarize,
)


def fixture():
    return CoachRequest.model_validate_json((ROOT / "evals/coach_audit/current.json").read_text())


def synthetic_contract(record, answer):
    return {
        "answer_contract": {
            "units": [
                {
                    "kind": "observation",
                    "text": answer,
                    "records": [record],
                    "evidence": ["fixture-record"],
                }
            ]
        }
    }


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.request = fixture()
        self.expected = expectation(["arm"], [1], ["lunge_finish"])
        self.record = {
            "feature": "weapon_elbow_angle",
            "value": 160.0,
            "unit": "deg",
            "phase": "lunge_finish",
            "rep": 1,
            "time_seconds": 2.8,
        }

    def check(self, text, record=None, expected=None):
        return check_answer(
            text,
            self.request,
            expected or self.expected,
            synthetic_contract(record or self.record, text),
            ROOT / "knowledge",
        )

    def test_at_least_thirty_multiturn_independent_expectations(self):
        cases = scenarios()
        self.assertGreaterEqual(len(cases), 30)
        self.assertEqual(len(cases), len({c["id"] for c in cases}))
        for case in cases:
            self.assertGreaterEqual(len(case["turns"]), 2)
            self.assertEqual(len(case["turns"]), len(case["expected"]))
        switch = next(c for c in cases if c["id"] == "switch")
        self.assertEqual(switch["expected"][2]["topics"], ["arm"])
        self.assertEqual(switch["expected"][3]["topics"], ["arm"])

    def test_independent_raw_numeric_check_accepts_measured_prose(self):
        answer = "Your sword-elbow angle measured 160 degrees in rep 1 during lunge finish (2.8 seconds)."
        result = self.check(answer)
        self.assertTrue(result["topic_correct"])
        self.assertFalse(result["unsupported_claims_flagged"], result["issues"])
        self.assertEqual(result["cited_data_points"], 1)

    def test_matching_template_does_not_validate_fabricated_record(self):
        record = {**self.record, "value": 37}
        answer = (
            "Your sword-elbow angle measured 37 degrees in rep 1 during lunge finish (2.8 seconds)."
        )
        result = self.check(answer, record)
        self.assertTrue(result["unsupported_claims_flagged"])
        self.assertTrue(any("record_attribution" in issue for issue in result["issues"]))

    def test_real_number_with_wrong_feature_or_rep_fails(self):
        for change in ({"feature": "front_knee_angle"}, {"rep": 2}, {"phase": "starting_guard"}):
            record = {**self.record, **change}
            result = self.check(
                "Your sword-elbow angle measured 160 degrees in rep 1 during lunge finish.", record
            )
            self.assertTrue(result["unsupported_claims_flagged"], change)

    def test_timestamp_from_another_rep_fails(self):
        record = {**self.record, "time_seconds": 17.1}
        result = self.check(
            "Your sword-elbow angle measured 160 degrees in rep 1 during lunge finish (17.1 seconds).",
            record,
        )
        self.assertTrue(any("timestamp_attribution" in issue for issue in result["issues"]))

    def test_known_number_attached_to_wrong_unit_fails(self):
        result = self.check(
            "Your sword-elbow angle measured 160 seconds in rep 1 during lunge finish."
        )
        self.assertTrue(result["unsupported_claims_flagged"])
        self.assertTrue(any("incompatible unit" in issue for issue in result["issues"]))

    def test_exact_milliseconds_conversion_preserves_attribution(self):
        record = {
            "feature": "finish_to_guard_time",
            "value": 0.5,
            "unit": "seconds",
            "phase": None,
            "rep": 1,
            "time_seconds": 2.833,
        }
        expected = expectation(["recovery"], [1], duration=True)
        answer = "Your finish-to-guard interval measured 0.5 seconds in rep 1 (2.8 seconds)."
        result = self.check(answer, record, expected)
        self.assertFalse(result["unsupported_claims_flagged"], result["issues"])
        for mutation in (
            {"value": 0.5001},
            {"unit": "deg"},
            {"rep": 999},
            {"phase": "lunge_finish"},
            {"feature": "weapon_elbow_angle"},
        ):
            wrong = self.check(answer, {**record, **mutation}, expected)
            self.assertTrue(wrong["unsupported_claims_flagged"], mutation)
            self.assertTrue(
                any("record_attribution" in issue for issue in wrong["issues"]), mutation
            )

    def test_library_label_cannot_hide_fabricated_numeric_claim(self):
        result = self.check(
            "From the coaching library: your sword-elbow angle measured 37 degrees in rep 1."
        )
        self.assertTrue(result["unsupported_claims_flagged"])

    def test_semantic_weapon_arm_relation_has_independent_source_and_role(self):
        excerpt = "In the conventional simple-lunge teaching sequence, this arm reaches forward toward the target with the point aimed at it."
        sentence = "For a simple lunge, reach your sword arm toward the target."
        run = {
            "answer_contract": {
                "units": [
                    {
                        "kind": "guidance",
                        "text": sentence,
                        "evidence": ["lunge_arm_roles.md#chunk-0"],
                        "records": [{"excerpt": excerpt}],
                    }
                ]
            }
        }
        good = check_answer(sentence, self.request, expectation(["arm"]), run, ROOT / "knowledge")
        self.assertFalse(good["unsupported_claims_flagged"], good["issues"])
        self.assertFalse(good["semantic_review_needed"], good["issues"])
        for mutation in (
            sentence.replace("sword arm", "non-sword arm"),
            sentence.replace("target.", "target for 37 repetitions."),
            sentence.replace("target.", "target before your front foot moves."),
            sentence.replace("target.", "target at 90 degrees."),
            sentence.replace("target.", "target for more force."),
        ):
            bad = check_answer(
                mutation, self.request, expectation(["arm"]), run, ROOT / "knowledge"
            )
            self.assertTrue(bad["unsupported_claims_flagged"], (mutation, bad["issues"]))
        self.assertIsNone(weapon_target_verdict(sentence, {"lunge_arm_roles": excerpt}, [excerpt]))

    def test_other_paraphrases_require_review_without_false_fabrication_claim(self):
        sentence = "Try moving fluidly through your arm movement."
        result = check_answer(sentence, self.request, expectation(["arm"]), {}, ROOT / "knowledge")
        self.assertTrue(result["semantic_review_needed"])
        self.assertFalse(result["unsupported_claims_flagged"])

    def test_user_instruction_cannot_supply_provenance_for_invented_drill(self):
        sentence = "Try a moonwalk parry drill."
        self.request.question = sentence
        result = self.check(sentence)
        self.assertTrue(result["unsupported_claims_flagged"])

    def test_unrelated_reference_range_fails(self):
        record = {**self.record, "reference_range": [88.6, 98.5]}
        result = self.check("Your sword-elbow angle measured 160 degrees in rep 1.", record)
        self.assertTrue(any("reference_attribution" in issue for issue in result["issues"]))

    def test_hallucinated_advice_without_numbers_fails(self):
        result = self.check(
            "Your sword-elbow angle measured 160 degrees in rep 1. Try a moonwalk parry drill."
        )
        self.assertTrue(any("advice_provenance" in issue for issue in result["issues"]))

    def test_library_attribution_alone_does_not_verify_excerpt(self):
        run = {
            "answer_contract": {
                "units": [
                    {
                        "kind": "guidance",
                        "text": "The coaching library says: “Try an invented moonwalk parry drill.”",
                        "records": [{"excerpt": "Try an invented moonwalk parry drill."}],
                    }
                ]
            }
        }
        result = check_answer(
            run["answer_contract"]["units"][0]["text"],
            self.request,
            self.expected,
            run,
            ROOT / "knowledge",
        )
        self.assertTrue(result["unsupported_claims_flagged"])

    def test_content_fallback_requires_missing_evidence_and_label(self):
        expected = expectation(no_measurements=True, no_library=True)
        good = "I don't have a reliable matching measurement. General advice, not drawn from this session: a clear recording would help."
        result = check_answer(good, self.request, expected, {}, ROOT / "knowledge")
        self.assertTrue(result["fallback_correct"])
        bad = check_answer(
            "General advice: reach farther.", self.request, expected, {}, ROOT / "knowledge"
        )
        self.assertFalse(bad["fallback_correct"])
        wrong_gate = check_answer(good, self.request, self.expected, {}, ROOT / "knowledge")
        self.assertFalse(wrong_gate["fallback_correct"])

    def test_raw_records_reject_unavailable_and_low_confidence(self):
        for name in ("unsupported", "low_confidence"):
            request = CoachRequest.model_validate_json(
                (ROOT / f"evals/coach_audit/{name}.json").read_text()
            )
            self.assertEqual(raw_records(request), [], name)


class HarnessTests(unittest.TestCase):
    def test_before_uses_retained_legacy_runner(self):
        request = fixture()
        fake_run = type("Fake", (), {"model_dump": lambda self, **kwargs: {"mode": "gemini"}})()
        with (
            patch("scripts.eval_coach._run_conversation", return_value=fake_run) as old,
            patch("scripts.eval_coach.run_verified_conversation") as new,
            patch("scripts.eval_coach.chat_model", return_value=object()),
        ):
            _run_turn(
                {
                    "request": request.model_dump(mode="json"),
                    "phase": "before",
                    "provider": "gemini",
                    "offline": False,
                }
            )
        old.assert_called_once()
        new.assert_not_called()

    def test_existing_outputs_preserved_and_resume_requires_hash_match(self):
        metadata = {
            "schema_version": 2,
            "phase": "after",
            "provider_requested": "local",
            "execution": "offline",
            "fixture_sha256": {"current": "one"},
            "code_sha256": {"code": "one"},
            "expectation_sha256": "one",
        }
        path = ROOT / "tmp" / f"oracle-{uuid4().hex}.json"
        try:
            original = load_or_create(path, metadata)
            save_artifact(path, original)
            with self.assertRaises(ValueError):
                load_or_create(path, metadata)
            self.assertEqual(load_or_create(path, metadata, resume=True), original)
            with self.assertRaises(ValueError):
                load_or_create(path, {**metadata, "code_sha256": {"code": "two"}}, resume=True)
            self.assertEqual(json.loads(path.read_text()), original)
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(".pending.json").unlink(missing_ok=True)

    def test_deadline_terminates_and_joins_worker(self):
        started = time.perf_counter()
        result = bounded_turn(
            {}, 0.1, worker_command=[sys.executable, "-c", "import time; time.sleep(30)"]
        )
        self.assertEqual(result["status"], "timeout")
        self.assertLess(time.perf_counter() - started, 5)

    def test_missing_runs_have_no_quality_or_latency_score(self):
        result = summarize([{"status": "timeout"}, {"status": "skipped"}])
        self.assertIsNone(result["unsupported_claim_rate"])
        self.assertIsNone(result["followup_resolution_accuracy"])
        self.assertIsNone(result["median_ms"])
        self.assertEqual(result["timeouts"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertIn("not measured", before_after_table(None, {"summary": result}))

    def test_offline_protocol_timings_are_not_provider_latency(self):
        result = summarize(
            [{"status": "completed", "offline": True, "latency_ms": 3.0, "issues": []}]
        )
        self.assertIsNone(result["median_ms"])
        self.assertIsNone(result["p95_ms"])
        self.assertEqual(result["offline_protocol_median_ms"], 3.0)

    def test_deadline_worker_returns_a_real_completed_offline_run(self):
        request = fixture()
        result = bounded_turn(
            {
                "request": request.model_dump(mode="json"),
                "phase": "after",
                "provider": "local",
                "offline": True,
            },
            10,
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertIn("summary", result["run"]["report"])

    def test_forced_switch_really_runs_turn3_failover_cooldown_and_probe(self):
        started = time.perf_counter()
        result = forced_switch_scenario()
        self.assertTrue(result["passed"], result["checks"])
        self.assertEqual(len(result["rows"]), 5)
        self.assertIn({"turn": 3, "provider": "gemini"}, result["calls"])
        self.assertIn({"turn": 3, "provider": "local"}, result["calls"])
        self.assertLess(time.perf_counter() - started, 15)


if __name__ == "__main__":
    unittest.main()
