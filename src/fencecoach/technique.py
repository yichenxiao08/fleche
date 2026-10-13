"""Per-rep basic-lunge geometry evaluator, independent of reviewed technique text.

Rules implement a conventional solo-drill rubric, not a learned correctness
classifier. Thresholds are explicit development heuristics with no accuracy claim.
"""

import math
from statistics import median

from fencecoach.lunge_benchmarks import evaluate_benchmarks
from fencecoach.phase_metrics import rep_phases
from fencecoach.quality import assess_quality

VERSION = "solo-lunge-rubric-v4-custom-benchmarks"
RULES = {
    "torso_pitch_change": {
        "threshold": 20,
        "minimum_finish_tilt": 30,
        "unit": "deg",
        "cue": "Try moving through the lunge without throwing your chest ahead of your hips.",
    },
    "front_knee_shallow": {
        "threshold": 125,
        "unit": "deg",
        "cue": "For this basic drill, try a lower finish with more front-knee bend while keeping the landing controlled.",
    },
    "rear_knee_bent": {
        "threshold": 150,
        "unit": "deg",
        "cue": "Try extending the rear leg as you drive forward; avoid forcing the knee into a locked position.",
    },
    "knee_past_toe": {
        "threshold": 0.12,
        "unit": "torso",
        "cue": "Review the landing side-on and adjust your step so the front knee finishes over the foot for this drill.",
    },
    "arm_direction": {
        "threshold": 25,
        "unit": "deg",
        "cue": "Choose one target height and reach your sword hand directly toward it instead of sweeping up or down.",
    },
    "guard_not_restored": {
        "threshold": 0.35,
        "unit": "torso",
        "cue": "Finish the recovery back at your starting guard before beginning the next rep.",
    },
}


def evaluate_lunges(result, windows=None, profile=None):
    profile = {**result.get("capture_profile", {}), **(profile or {})}
    windows = windows if windows is not None else result.get("candidates", [])
    output = {
        "version": VERSION,
        "method": "explicit solo-drill heuristics, not a trained classifier",
        "rules": RULES,
        "reps": [],
        "findings": [],
        "suppressed_findings": [],
        "limitations": [
            "2D image geometry; thresholds are unvalidated review triggers, not universal technique targets.",
            "No measured force, balance, ground contact, blade contact or injury diagnosis.",
            "Action timing depends on the selected phase anchors. Finish-to-guard includes any hold.",
            "A flag requires agreement across neighboring pose samples. Agreement is not proof of landmark accuracy.",
        ],
    }
    qa = result.get("quality_gate") or assess_quality(result)
    output["whole_clip_quality"] = "supported" if qa.get("coaching_allowed") else "unsupported"
    hard_issues = [
        i
        for i in qa["issues"]
        if i["code"] in {"low_resolution", "experimental_bout", "camera_motion"}
        and i["severity"] == "reject"
    ]
    if hard_issues:
        output.update(
            status="unsupported",
            reason=" ".join(i["tip"] for i in hard_issues),
        )
        return output
    if (
        profile.get("scene_type", "solo") != "solo"
        or profile.get("camera_motion") == "moving"
        or result.get("camera_evidence", {}).get("moving")
    ):
        output.update(
            status="unsupported",
            reason="Basic-drill evaluation requires one fencer and a fixed camera.",
        )
        return output
    width, height = result["width"], result["height"]
    frames = result.get("frames", [])
    front = profile.get("front_leg", "unknown")
    arm = profile.get("weapon_arm", "unknown")
    facing = profile.get("facing", "unknown")
    side_view = profile.get("camera_view") == "side"
    output["capture_requirements"] = {
        "side_view_confirmed": side_view,
        "front_leg": front,
        "weapon_arm": arm,
        "facing": facing,
    }

    def point(frame, i):
        p = frame["landmarks"][i]
        return p[0] * width, p[1] * height

    def usable(frame, ids):
        p = frame.get("landmarks", [])
        return (
            len(p) == 33
            and bool(frame.get("features"))
            and all(
                len(p[i]) >= 5
                and min(p[i][3:5]) >= 0.7
                and 0.01 <= p[i][0] <= 0.99
                and 0.01 <= p[i][1] <= 0.99
                for i in ids
            )
        )

    def near(time, ids):
        options = [f for f in frames if abs(f["time_ms"] - time) <= 125 and usable(f, ids)]
        return min(options, key=lambda f: abs(f["time_ms"] - time), default=None)

    def signed_torso(frame):
        s = [point(frame, i) for i in (11, 12)]
        h = [point(frame, i) for i in (23, 24)]
        return math.degrees(
            math.atan2(
                (s[0][0] + s[1][0] - h[0][0] - h[1][0]) / 2,
                (h[0][1] + h[1][1] - s[0][1] - s[1][1]) / 2,
            )
        )

    # Multiple neighboring samples can support role inference even in a short
    # clip with one or two reps. They are not independent training examples.
    anchor_times = [
        t
        for w in windows
        for t in (w.get("onset_ms", w.get("movement_onset_ms")), w["start_ms"])
        if t is not None
    ]
    anchors = [
        f
        for f in frames
        if any(abs(f["time_ms"] - t) <= 125 for t in anchor_times)
        and usable(f, (11, 12, 23, 24, 27, 28))
    ]
    inferred = {}
    if profile.get("camera_view", "unknown") == "unknown" and len(anchors) >= 3:
        ratios = [
            abs(point(f, 11)[0] - point(f, 12)[0]) / f["features"]["torso_pixels"]
            for f in anchors
            if f["features"].get("torso_pixels", 0) > 5
            and f["features"].get("stance_ratio", 0) > 0.45
        ]
        if len(ratios) >= 3 and median(ratios) < 0.6:
            side_view = True
            inferred["camera_view"] = (
                "side-like projection inferred from shoulder/stance geometry; not independently verified"
            )
    if side_view and facing in {"left", "right"}:
        sign = -1 if facing == "left" else 1
        for role, ids, minimum in (("front_leg", (27, 28), 0.4), ("weapon_arm", (15, 16), 0.35)):
            if profile.get(role, "unknown") in {"left", "right"}:
                continue
            votes = []
            for frame in anchors:
                if usable(frame, ids):
                    offset = (
                        (point(frame, ids[0])[0] - point(frame, ids[1])[0])
                        * sign
                        / frame["features"]["torso_pixels"]
                    )
                    if abs(offset) >= minimum:
                        votes.append("left" if offset > 0 else "right")
            if len(votes) >= 3:
                winner = max(set(votes), key=votes.count)
                if votes.count(winner) / len(votes) >= 0.8:
                    if role == "front_leg":
                        front = winner
                    else:
                        arm = winner
                    inferred[role] = (
                        f"{winner}: inferred from consistently leading endpoint; confirm if mirrored or tracking swaps sides"
                    )
    output["capture_requirements"].update(
        side_view_supported=side_view, front_leg=front, weapon_arm=arm, inferred=inferred
    )
    if side_view and front in {"left", "right"} and facing in {"left", "right"}:
        front_ankle, rear_ankle = (27, 28) if front == "left" else (28, 27)
        offsets = [
            (point(f, front_ankle)[0] - point(f, rear_ankle)[0])
            * (-1 if facing == "left" else 1)
            / f["features"]["torso_pixels"]
            for f in anchors
            if f["features"].get("torso_pixels", 0) > 5
        ]
        if len(offsets) >= 3 and sum(value < -0.4 for value in offsets) / len(offsets) >= 0.8:
            output["capture_requirements"]["warning"] = (
                "The declared front leg consistently leads opposite to the selected facing direction. "
                "Confirm facing/lead leg or whether the recording is mirrored. Direction-dependent checks were withheld."
            )
            facing = "unknown"
            output["capture_requirements"]["facing_used"] = "unknown"
    if inferred:
        output["limitations"].append(
            "Some capture roles were inferred geometrically; findings remain review flags, not verified corrections."
        )

    for number, window in enumerate(windows, 1):
        start, end = window["start_ms"], window["end_ms"]
        onset = window.get("onset_ms")
        if onset is None:
            onset = window.get("movement_onset_ms")
        rep = {
            "rep_number": number,
            "lunge_ms": start,
            "guard_ms": end,
            "action_start_ms": onset,
            "measurements": {},
            "findings": [],
            "suppressed_findings": [],
            "unavailable": [],
        }
        local = [
            f for f in frames if (onset if onset is not None else start) <= f["time_ms"] <= end
        ]
        epochs = {f.get("track_epoch", 0) for f in local if f.get("features")}
        if len(epochs) > 1 or (
            local
            and sum(f.get("tracking", {}).get("detected_poses", 1) > 1 for f in local) / len(local)
            > 0.1
        ):
            rep.update(
                status="unavailable",
                unavailable=[
                    "This interval contains a tracking identity break or multiple visible people."
                ],
            )
            output["reps"].append(rep)
            continue
        m = rep["measurements"]
        phase_result = rep_phases(
            frames,
            window,
            {**profile, "front_leg": front, "weapon_arm": arm, "facing": facing},
            width,
            height,
        )
        rep["phases"] = phase_result["phases"]
        rep["hold_detected"] = phase_result["hold_detected"]
        rep["drill_benchmarks"] = evaluate_benchmarks(
            frames,
            window,
            rep["phases"],
            {
                **profile,
                "camera_view": "side" if side_view else profile.get("camera_view"),
                "front_leg": front,
                "weapon_arm": arm,
                "facing": facing,
            },
            width,
            height,
        )
        finish_phase_name = "lunge_hold" if phase_result["hold_detected"] else "lunge_finish"
        finish_phase = rep["phases"].get(finish_phase_name, {})
        finish_anchor = finish_phase.get("representative_ms", start)
        initial_phase = rep["phases"].get("starting_guard", {}).get("measurements", {})
        if output["capture_requirements"].get("warning"):
            rep["unavailable"].append(output["capture_requirements"]["warning"])

        def phase_measurement(key):
            phase_name = "returned_guard" if key == "guard_stance_change" else finish_phase_name
            phase = rep["phases"].get(phase_name, {})
            values = phase.get("measurements", {})
            lookup = {
                "forward_torso_pitch_change": "signed_torso_tilt",
                "guard_stance_change": "stance_width",
            }.get(key, key)
            sample = values.get(lookup)
            if not sample:
                return None
            sample = {**sample}
            if key == "forward_torso_pitch_change":
                if "signed_torso_tilt" not in initial_phase:
                    return None
                sample["value"] = (
                    sample["value"] - initial_phase["signed_torso_tilt"]["value"]
                ) * (-1 if facing == "left" else 1)
            elif key == "guard_stance_change":
                if "stance_width" not in initial_phase:
                    return None
                sample["value"] -= initial_phase["stance_width"]["value"]
            return sample, phase, phase_name

        def add(key, value, unit, frame, note=""):
            if value is not None:
                summary = phase_measurement(key)
                m[key] = {
                    "value": round(value, 3),
                    "unit": unit,
                    "time_ms": frame["time_ms"] if frame else start,
                    "note": note,
                }
                if summary:
                    sample, phase, phase_name = summary
                    m[key].update(
                        value=round(sample["value"], 3),
                        time_ms=sample["representative_ms"],
                        single_frame_value=round(value, 3),
                        summary_method="phase_median",
                        phase=phase_name,
                        phase_start_ms=phase["start_ms"],
                        phase_end_ms=phase["end_ms"],
                        sample_count=sample["sample_count"],
                        note=note
                        + f" Median over {sample['sample_count']} visible samples in {phase_name.replace('_', ' ')}.",
                    )

        def flag(rule, observation, key, ids, measure, predicate):
            samples = [
                f
                for f in frames
                if (
                    m[key]["phase_start_ms"] <= f["time_ms"] <= m[key]["phase_end_ms"]
                    if m[key].get("summary_method") == "phase_median"
                    else abs(f["time_ms"] - m[key]["time_ms"]) <= 125
                )
                and usable(f, ids)
                and f.get("track_epoch", 0) in epochs
            ]
            values = [(f["time_ms"], measure(f)) for f in samples]
            values = [(t, value) for t, value in values if value is not None]
            agreeing = [(t, value) for t, value in values if predicate(value)]
            span = max((t for t, _ in values), default=0) - min((t for t, _ in values), default=0)
            support = {
                "sample_count": len(values),
                "agreeing_samples": len(agreeing),
                "span_ms": span,
                "value_range": [
                    round(min(v for _, v in values), 3),
                    round(max(v for _, v in values), 3),
                ]
                if values
                else None,
                "timestamps_ms": [t for t, _ in values],
                "note": "Temporal agreement of sampled 2D geometry, not an accuracy probability.",
            }
            m[key]["sample_support"] = support
            if len(agreeing) < 2 or span < 60 or len(agreeing) / max(1, len(values)) < 2 / 3:
                suppressed = {
                    "rule": rule,
                    "rep_number": number,
                    "measurement_key": key,
                    "evidence_ms": m[key]["time_ms"],
                    "reason": "The selected frame's flag was not corroborated by enough neighboring samples.",
                    "sample_support": support,
                }
                rep["suppressed_findings"].append(suppressed)
                output["suppressed_findings"].append(suppressed)
                rep["unavailable"].append(
                    f"{rule.replace('_', ' ')}: neighboring samples do not agree enough for a correction."
                )
                return
            finding = {
                "id": f"technique-rep-{number}-{rule}",
                "rep_number": number,
                "rule": rule,
                "status": "review",
                "observation": observation,
                "cue": RULES[rule]["cue"],
                "evidence_ms": m[key]["time_ms"],
                "measurement": m[key],
                "sample_support": support,
                "basis": "basic solo-drill rubric; unvalidated heuristic",
            }
            rep["findings"].append(finding)
            output["findings"].append(finding)

        if onset is not None and 0 <= onset <= start < end:
            add(
                "action_to_lunge_time",
                start - onset,
                "ms",
                None,
                "Anchor-to-anchor duration, not reaction time or speed in m/s.",
            )
        add(
            "finish_to_guard_time",
            end - start,
            "ms",
            None,
            "Includes any hold at the lunge finish; not active recovery speed.",
        )
        finish = near(finish_anchor, (11, 12, 23, 24))
        initial = near(onset, (11, 12, 23, 24)) if onset is not None else None
        if finish:
            rep["selected_frame_ms"] = finish["time_ms"]
            add(
                "projected_torso_tilt",
                finish["features"].get("torso_tilt"),
                "deg",
                finish,
                "Relative to image vertical, not spinal curvature or physical balance.",
            )
            if initial:
                initial_pitch = initial_phase.get("signed_torso_tilt", {}).get(
                    "value", signed_torso(initial)
                )
                change = signed_torso(finish) - initial_pitch
                if facing == "left":
                    change = -change
                add(
                    "forward_torso_pitch_change",
                    change if facing in {"left", "right"} else abs(change),
                    "deg",
                    finish,
                    "Change from action-start posture cancels a constant camera roll.",
                )
                change = m["forward_torso_pitch_change"]["value"]
                if (
                    side_view
                    and facing in {"left", "right"}
                    and change > RULES["torso_pitch_change"]["threshold"]
                    and m["projected_torso_tilt"]["value"]
                    > RULES["torso_pitch_change"]["minimum_finish_tilt"]
                ):
                    flag(
                        "torso_pitch_change",
                        "Your torso pitches farther forward than at the start of this rep.",
                        "forward_torso_pitch_change",
                        (11, 12, 23, 24),
                        lambda f: (
                            (signed_torso(f) - initial_pitch) * (-1 if facing == "left" else 1)
                        ),
                        lambda value: (
                            value > RULES["torso_pitch_change"]["threshold"]
                            and abs(value + initial_pitch * (-1 if facing == "left" else 1))
                            > RULES["torso_pitch_change"]["minimum_finish_tilt"]
                        ),
                    )
        else:
            rep["unavailable"].append(
                "No sufficiently visible torso frame within 125 ms of the lunge bookmark."
            )
        if not side_view:
            rep["unavailable"].append(
                "Confirm a side view to apply the posture rubric; projected measurements alone are not graded."
            )
        if front in {"left", "right"}:
            hip, knee, ankle, toe = (23, 25, 27, 31) if front == "left" else (24, 26, 28, 32)
            leg_frame = near(finish_anchor, (hip, knee, ankle))
            if leg_frame:
                key = f"{front}_knee_angle"
                add(
                    "front_knee_angle",
                    leg_frame["features"].get(key),
                    "deg",
                    leg_frame,
                    "Included knee angle; approximately 90 degrees is a teaching reference, not a universal cutoff.",
                )
                if (
                    side_view
                    and m.get("front_knee_angle", {}).get("value", 0)
                    > RULES["front_knee_shallow"]["threshold"]
                ):
                    flag(
                        "front_knee_shallow",
                        "The front leg remains comparatively straight at the selected lunge finish.",
                        "front_knee_angle",
                        (hip, knee, ankle),
                        lambda f: f["features"].get(key),
                        lambda value: value > RULES["front_knee_shallow"]["threshold"],
                    )
                if facing in {"left", "right"} and usable(leg_frame, (hip, knee, ankle, toe)):
                    torso = leg_frame["features"].get("torso_pixels", 0)
                    if torso > 5:
                        distance = (
                            (point(leg_frame, knee)[0] - point(leg_frame, toe)[0])
                            * (-1 if facing == "left" else 1)
                            / torso
                        )
                        add(
                            "front_knee_ahead_of_toe",
                            distance,
                            "torso",
                            leg_frame,
                            "Projected horizontal offset, independently measured from knee angle.",
                        )
                        if (
                            side_view
                            and m["front_knee_ahead_of_toe"]["value"]
                            > RULES["knee_past_toe"]["threshold"]
                        ):
                            flag(
                                "knee_past_toe",
                                "The projected front knee is ahead of the toe at this selected frame.",
                                "front_knee_ahead_of_toe",
                                (hip, knee, ankle, toe),
                                lambda f: (
                                    (point(f, knee)[0] - point(f, toe)[0])
                                    * (-1 if facing == "left" else 1)
                                    / f["features"]["torso_pixels"]
                                ),
                                lambda value: value > RULES["knee_past_toe"]["threshold"],
                            )
            rear = "right" if front == "left" else "left"
            ids = (24, 26, 28) if rear == "right" else (23, 25, 27)
            rear_frame = near(finish_anchor, ids)
            if rear_frame:
                add(
                    "rear_knee_angle",
                    rear_frame["features"].get(f"{rear}_knee_angle"),
                    "deg",
                    rear_frame,
                )
                if (
                    side_view
                    and "rear_knee_angle" in m
                    and m["rear_knee_angle"]["value"] < RULES["rear_knee_bent"]["threshold"]
                ):
                    flag(
                        "rear_knee_bent",
                        "The rear knee remains bent at the selected lunge finish.",
                        "rear_knee_angle",
                        ids,
                        lambda f: f["features"].get(f"{rear}_knee_angle"),
                        lambda value: value < RULES["rear_knee_bent"]["threshold"],
                    )
        else:
            rep["unavailable"].append(
                "Specify the anatomical front leg before front/rear-leg evaluation."
            )
        if arm in {"left", "right"}:
            s, elbow, wrist = (11, 13, 15) if arm == "left" else (12, 14, 16)
            arm_frame = near(finish_anchor, (s, elbow, wrist))
            if arm_frame:
                a, b = point(arm_frame, s), point(arm_frame, wrist)
                dx, dy = b[0] - a[0], a[1] - b[1]
                direction = math.degrees(math.atan2(dy, abs(dx)))
                add(
                    "weapon_arm_direction",
                    direction,
                    "deg",
                    arm_frame,
                    "Shoulder-to-wrist direction relative to image horizontal; positive is upward. This is not elbow bend.",
                )
                direction = m["weapon_arm_direction"]["value"]
                add(
                    "weapon_elbow_angle",
                    arm_frame["features"].get(f"{arm}_elbow_angle"),
                    "deg",
                    arm_frame,
                )
                if side_view and abs(direction) > RULES["arm_direction"]["threshold"]:
                    flag(
                        "arm_direction",
                        "The sword arm points noticeably "
                        + ("upward" if direction > 0 else "downward")
                        + " relative to the image horizontal; check it against your intended target height.",
                        "weapon_arm_direction",
                        (s, elbow, wrist),
                        lambda f: math.degrees(
                            math.atan2(
                                point(f, s)[1] - point(f, wrist)[1],
                                abs(point(f, wrist)[0] - point(f, s)[0]),
                            )
                        ),
                        lambda value: (
                            value > RULES["arm_direction"]["threshold"]
                            if direction > 0
                            else value < -RULES["arm_direction"]["threshold"]
                        ),
                    )
        else:
            rep["unavailable"].append(
                "Specify the anatomical weapon arm before evaluating sword-arm direction."
            )
        guard = near(end, (11, 12, 23, 24, 27, 28))
        initial_stance = near(onset, (11, 12, 23, 24, 27, 28)) if onset is not None else None
        if guard and initial_stance:
            initial_width = initial_phase.get("stance_width", {}).get(
                "value", initial_stance["features"]["stance_ratio"]
            )
            delta = guard["features"]["stance_ratio"] - initial_width
            add(
                "guard_stance_change",
                delta,
                "torso",
                guard,
                "Stance width difference from this rep's starting position.",
            )
            if (
                side_view
                and m["guard_stance_change"]["value"] > RULES["guard_not_restored"]["threshold"]
            ):
                flag(
                    "guard_not_restored",
                    "Your stance is wider at the return bookmark than at this rep's start.",
                    "guard_stance_change",
                    (11, 12, 23, 24, 27, 28),
                    lambda f: f["features"]["stance_ratio"] - initial_width,
                    lambda value: value > RULES["guard_not_restored"]["threshold"],
                )
        if initial and finish and onset is not None:
            moving = [
                f for f in frames if onset <= f["time_ms"] <= start and usable(f, (11, 12, 23, 24))
            ]
            speeds = []
            scale = initial["features"].get("torso_pixels", 0)
            for a, b in zip(moving, moving[1:]):
                dt = (b["time_ms"] - a["time_ms"]) / 1000
                if scale > 5 and 0 < dt <= 0.125:
                    dx = abs(
                        (point(b, 23)[0] + point(b, 24)[0] - point(a, 23)[0] - point(a, 24)[0]) / 2
                    )
                    speeds.append(dx / scale / dt)
            if len(speeds) >= 3:
                add(
                    "action_projected_hip_speed",
                    median(speeds),
                    "torso/s",
                    finish,
                    "Median horizontal image-plane hip speed; fixed initial torso scale, not m/s or measured explosiveness.",
                )
        recovery_onset = phase_result["recovery_onset_ms"]
        if recovery_onset is not None and guard:
            add(
                "estimated_recovery_onset",
                recovery_onset,
                "ms",
                None,
                "First two consecutive samples with backward hip displacement above 0.06 initial torso lengths; estimated, not a reviewed phase label.",
            )
            add(
                "estimated_active_recovery_time",
                max(0, end - recovery_onset),
                "ms",
                guard,
                "Estimated backward-motion onset to guard bookmark; excludes the preceding hold and is limited by pose sampling.",
            )
        geometry_keys = set(m) - {
            "action_to_lunge_time",
            "finish_to_guard_time",
            "action_projected_hip_speed",
            "estimated_recovery_onset",
            "estimated_active_recovery_time",
        }
        rep["geometry_available"] = bool(geometry_keys)
        rep["status"] = (
            "review_flags"
            if rep["findings"]
            else "measured_no_flags"
            if geometry_keys
            else "unavailable"
        )
        output["reps"].append(rep)
    times = [
        r["measurements"]["action_to_lunge_time"]["value"]
        for r in output["reps"]
        if "action_to_lunge_time" in r["measurements"]
    ]
    output["timing_summary"] = {
        "action_to_lunge_median_ms": median(times) if times else None,
        "action_to_lunge_range_ms": [min(times), max(times)] if times else None,
        "policy": "Compare repetitions within the same intended drill. No universal correct speed threshold is applied.",
    }
    output["status"] = (
        "review_flags"
        if output["findings"]
        else "measured_no_flags"
        if any(r.get("geometry_available") for r in output["reps"])
        else "unavailable"
        if output["reps"]
        else "no_reps"
    )
    output["limitations"].append(
        "No flags does not mean correct technique; some checks may be unavailable."
    )
    return output
