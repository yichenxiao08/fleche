"""Compare phase-specific evidence with submitted reference reps, without scoring technique."""

import json
from functools import lru_cache
from hashlib import sha256
from statistics import median

from fencecoach.feedback_learning import corrected_windows
from fencecoach.technique import evaluate_lunges

POLICY = (
    "Lead with comparison to the agreed reference reps, not fixed geometry thresholds. "
    "A difference is not automatically an error. Give at most one useful practice cue supported by a "
    "phase-matched comparison. Preserve reviewer corrections on reference reps; an aspect with a stated "
    "issue is not a positive target. Reference ranges describe these examples, not a learned population "
    "standard. Different side-view cameras permit provisional projected comparisons, not verified "
    "physical speed or force comparisons. Drill thresholds are optional athlete targets."
)


@lru_cache(maxsize=32)
def _reference_evaluation(path, modified, review_json, profile_json, windows_json, content_sha256):
    result = json.loads(path.read_text(encoding="utf-8"))
    review = json.loads(review_json)
    windows = corrected_windows(review, json.loads(windows_json) or result.get("candidates", []))
    return evaluate_lunges(result, windows, json.loads(profile_json))


def attach_reference_comparisons(evaluation, current_job, directory, repository, jobs):
    """Use saved source clips locally; reference feedback never transfers as a new clip's label."""
    reference_reps = []
    for review in repository.list_reference_reviews():
        path = directory / review["job_id"] / "result.json"
        job = jobs.get(review["job_id"])
        if not path.is_file() or not job:
            continue
        try:
            source = _reference_evaluation(
                path,
                path.stat().st_mtime_ns,
                json.dumps(review, sort_keys=True),
                json.dumps(job.get("capture_profile", {}), sort_keys=True),
                json.dumps(job.get("reviewed_windows", []), sort_keys=True),
                sha256(path.read_bytes()).hexdigest(),
            )
        except (KeyError, ValueError, IndexError):
            continue
        if not source.get("capture_requirements", {}).get("side_view_supported"):
            continue
        for label in review["reps"]:
            if label.get("rating") != "reference":
                continue
            rep = next(
                (r for r in source.get("reps", []) if r["rep_number"] == label["rep_number"]), None
            )
            if rep and rep.get("geometry_available"):
                reference_reps.append(
                    {
                        "job_id": review["job_id"],
                        "revision": review["revision"],
                        "rep": rep,
                        "label": label,
                        "review": review,
                        "profile": job.get("capture_profile", {}),
                    }
                )
        if reference_reps:
            break  # One coherent reference set, not a mixture of unrelated athletes/recordings.
    metadata = [
        {
            "job_id": r["job_id"],
            "rep_number": r["rep"]["rep_number"],
            "revision": r["revision"],
            "stated_corrections": r["label"].get("main_issue", ""),
        }
        for r in reference_reps
    ]
    evaluation["reference_comparison"] = {
        "policy": POLICY,
        "references": metadata,
        "status": "available" if reference_reps else "no_reference_set",
    }
    current_profile = current_job.get("capture_profile", {})
    for rep in evaluation.get("reps", []):
        eligible = [
            r
            for r in reference_reps
            if not (
                r["job_id"] == current_job.get("job_id")
                and r["rep"]["rep_number"] == rep["rep_number"]
            )
        ]
        if not evaluation.get("capture_requirements", {}).get("side_view_supported"):
            eligible = []
        comparison = {
            "status": "available" if eligible else "unavailable",
            "rows": [],
            "coaching_priorities": [],
            "policy": POLICY,
            "references": metadata,
            "comparison_scope": "phase-matched projected side-view measurements; camera equivalence is not verified",
        }
        rep["reference_comparison"] = comparison
        if not eligible:
            comparison["reason"] = (
                "No other usable reference rep or no supported side-view projection."
            )
            continue
        for phase_name, phase in rep.get("phases", {}).items():
            if phase_name == "lunge_drive":
                continue
            canonical = "finish" if phase_name in {"lunge_hold", "lunge_finish"} else phase_name
            for key, measurement in phase.get("measurements", {}).items():
                if key not in {
                    "front_knee_angle",
                    "rear_knee_angle",
                    "projected_torso_tilt",
                    "weapon_arm_direction",
                    "weapon_elbow_angle",
                }:
                    continue
                values, spans, sources = [], [], []
                for ref in eligible:
                    issue = ref["label"].get("main_issue", "").lower()
                    if ("weapon" in key and any(w in issue for w in ("arm", "hand", "target"))) or (
                        "recovery" in canonical and any(w in issue for w in ("recovery", "recover"))
                    ):
                        continue
                    ref_phase = (
                        (
                            ref["rep"].get("phases", {}).get("lunge_hold")
                            or ref["rep"].get("phases", {}).get("lunge_finish")
                        )
                        if canonical == "finish"
                        else ref["rep"].get("phases", {}).get(phase_name)
                    )
                    ref_measurement = (ref_phase or {}).get("measurements", {}).get(key)
                    if (
                        not ref_measurement
                        or min(measurement["sample_count"], ref_measurement["sample_count"]) < 3
                    ):
                        continue
                    values.append(ref_measurement["value"])
                    spans.extend(ref_measurement["range"])
                    sources.append({"job_id": ref["job_id"], "rep": ref["rep"]["rep_number"]})
                if not values:
                    continue
                low, high = min(spans), max(spans)
                current_low, current_high = measurement["range"]
                direction = (
                    "higher"
                    if current_low > high
                    else "lower"
                    if current_high < low
                    else "overlaps"
                )
                row = {
                    "metric": key,
                    "phase": canonical,
                    "current": measurement["value"],
                    "unit": measurement["unit"],
                    "reference_median": median(values),
                    "reference_range": [low, high],
                    "current_range": [current_low, current_high],
                    "difference": measurement["value"] - median(values),
                    "direction": direction,
                    "reference_reps": sources,
                    "watch_at_seconds": round(phase["representative_ms"] / 1000, 1),
                }
                comparison["rows"].append(row)
                cue = None
                if canonical == "finish":
                    if key == "front_knee_angle" and direction == "higher":
                        cue = "Try settling into a lower finish, closer to the front-leg bend in your reference reps."
                    elif key == "rear_knee_angle" and direction == "lower":
                        cue = "Try completing the rear-leg extension as you drive into the finish."
                    elif key == "projected_torso_tilt" and direction == "higher":
                        cue = "Try keeping your chest more upright through the finish, as in your reference reps."
                if cue:
                    comparison["coaching_priorities"].append(
                        {
                            "rep": rep["rep_number"],
                            "metric": key,
                            "phase": canonical,
                            "what_to_try": cue,
                            "reason": f"Your {key.replace('_', ' ')} is {direction} at the finish than the observed reference range.",
                            "watch_at_seconds": row["watch_at_seconds"],
                            "reference_reps": sources,
                        }
                    )
        reach = rep.get("drill_benchmarks", {}).get("reach", {})
        ref_reach = [(r, r["rep"].get("drill_benchmarks", {}).get("reach", {})) for r in eligible]
        ref_reach = [(r, v) for r, v in ref_reach if v.get("status") == "estimated"]
        if reach.get("status") == "estimated" and ref_reach:
            values = [v["feet_separation_leg_lengths"] for _, v in ref_reach]
            comparison["rows"].append(
                {
                    "metric": "feet_separation_leg_lengths",
                    "phase": "finish",
                    "current": reach["feet_separation_leg_lengths"],
                    "unit": "leg lengths",
                    "reference_median": median(values),
                    "reference_range": [min(values), max(values)],
                    "difference": reach["feet_separation_leg_lengths"] - median(values),
                    "reference_reps": [
                        {"job_id": r["job_id"], "rep": r["rep"]["rep_number"]} for r, _ in ref_reach
                    ],
                }
            )
        # Timing is comparable only for the same declared drill, camera setup and weapon.
        for key in (
            "action_projected_hip_speed",
            "action_to_lunge_time",
            "estimated_active_recovery_time",
        ):
            current = rep.get("measurements", {}).get(key)
            values = []
            for ref in eligible:
                same_clip = ref["job_id"] == current_job.get("job_id")
                same_setup = current_profile.get("camera_setup_id") and current_profile.get(
                    "camera_setup_id"
                ) == ref["profile"].get("camera_setup_id")
                matching_weapon = current_profile.get("weapon") == ref["review"].get("weapon")
                matching_drill = current_profile.get("intended_drill") and current_profile.get(
                    "intended_drill"
                ) == ref["review"].get("intended_drill")
                issue = ref["label"].get("main_issue", "").lower()
                corrected_aspect = any(
                    w in issue
                    for w in (
                        ("recover", "recovery")
                        if "recovery" in key
                        else ("speed", "explosive", "power", "faster")
                    )
                )
                value = ref["rep"].get("measurements", {}).get(key)
                if (
                    current
                    and value
                    and not corrected_aspect
                    and (same_clip or (same_setup and matching_weapon and matching_drill))
                ):
                    values.append(value["value"])
            if values:
                divisor = 1000 if current["unit"] == "ms" else 1
                comparison["rows"].append(
                    {
                        "metric": key,
                        "phase": "action" if "recovery" not in key else "active_recovery",
                        "current": current["value"] / divisor,
                        "unit": "seconds" if divisor == 1000 else current["unit"],
                        "reference_median": median(values) / divisor,
                        "reference_range": [min(values) / divisor, max(values) / divisor],
                        "difference": (current["value"] - median(values)) / divisor,
                    }
                )
        comparison["status"] = "available" if comparison["rows"] else "unavailable"
        comparison["coaching_priorities"] = comparison["coaching_priorities"][:2]
    evaluation["coaching_mode"] = "reference_comparison"
    return evaluation
