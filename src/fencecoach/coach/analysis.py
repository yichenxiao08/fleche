"""Turn reviewed session measurements into a small, traceable coaching brief."""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

from fencecoach.schemas import CoachRequest, MetricObservation

CONFIDENCE_THRESHOLD = 0.65
_REP_ID = re.compile(r"(?:^|-)rep-(\d+)(?:-|$)", re.IGNORECASE)
_RECOVERY_ID = re.compile(r"(?:^|-)recovery-(\d+)(?:-|$)", re.IGNORECASE)


def _rep_key(metric: MetricObservation) -> str | None:
    match = _REP_ID.search(metric.metric_id)
    if match:
        return metric.metric_id[: match.start()] + ":" + match.group(1)
    match = _RECOVERY_ID.search(metric.metric_id)
    if match:
        return metric.metric_id[: match.start()] + ":" + match.group(1)
    return None


def _reliable(metric: MetricObservation) -> bool:
    # A manually marked interval has no pose-quality estimate, but the athlete did
    # review its boundaries. Geometry from that window still needs visible landmarks.
    return metric.confidence >= CONFIDENCE_THRESHOLD or bool(
        metric.provenance and metric.provenance.annotation == "manual_window"
    )


def _seconds(metric: MetricObservation) -> float | None:
    unit = metric.unit.lower().strip()
    if unit in {"ms", "millisecond", "milliseconds"}:
        return metric.value / 1000
    if unit in {"s", "sec", "second", "seconds"}:
        return metric.value
    return None


def build_coaching_brief(request: CoachRequest) -> dict:
    """Prioritize repeatable patterns and keep side-specific claims grounded."""
    profile = request.capture_profile or {}
    grouped: dict[str, list[MetricObservation]] = defaultdict(list)
    for metric in request.metrics:
        key = _rep_key(metric)
        if key:
            grouped[key].append(metric)

    recovery = [
        metric
        for metric in request.metrics
        if metric.name == "recovery_time" and _reliable(metric) and _seconds(metric) is not None
    ]
    recovery_seconds = [_seconds(metric) for metric in recovery]
    recovery_seconds = [value for value in recovery_seconds if value is not None]
    front_leg = profile.get("front_leg", "unknown")
    weapon_arm = profile.get("weapon_arm", "unknown")
    weapon = profile.get("weapon", "unknown")

    def side_measurements(name: str, side: str, suffix: str):
        return [
            metric
            for metric in request.metrics
            if metric.name == f"{side}_{name}_{suffix}" and _reliable(metric)
        ]

    front_knee = (
        side_measurements("knee_angle", front_leg, "at_peak")
        if front_leg in {"left", "right"}
        else []
    )
    front_knee_change = (
        side_measurements("knee_flexion", front_leg, "from_onset")
        if front_leg in {"left", "right"}
        else []
    )
    weapon_onset = (
        side_measurements("arm_extension", weapon_arm, "at_onset")
        if weapon_arm in {"left", "right"}
        else []
    )
    weapon_peak = (
        side_measurements("arm_extension", weapon_arm, "at_peak")
        if weapon_arm in {"left", "right"}
        else []
    )
    weapon_elbow_peak = (
        side_measurements("elbow_angle", weapon_arm, "at_peak")
        if weapon_arm in {"left", "right"}
        else []
    )

    patterns: list[dict] = []
    if len(recovery_seconds) >= 3:
        low, high = min(recovery_seconds), max(recovery_seconds)
        typical = median(recovery_seconds)
        spread = high - low
        if spread >= max(0.5, typical * 0.75):
            patterns.append(
                {
                    "topic": "recovery consistency",
                    "priority": "high",
                    "observation": (
                        f"The reviewed recovery intervals vary substantially within this session "
                        f"({low:.2f}–{high:.2f} seconds across {len(recovery_seconds)} reps). "
                        "This is a repeatability cue, not proof that a faster return is better."
                    ),
                    "practice_focus": (
                        "Make the return to en garde deliberate and repeatable before trying to speed it up."
                    ),
                    "drill": (
                        "Do five slow lunges. Recover to the same en-garde position, pause, "
                        "and reset before the next repetition. Compare the return intervals."
                    ),
                    "evidence_ids": [metric.metric_id for metric in recovery],
                    "retrieval_topics": "lunge deliberate recovery to en garde repeatability",
                }
            )

    if len(front_knee) >= 2 or len(front_knee_change) >= 2:
        values = [metric.value for metric in front_knee]
        flexion = [metric.value for metric in front_knee_change]
        if flexion:
            onset_amount = median(flexion)
            if onset_amount >= 0:
                observation = (
                    f"From movement onset to the lunge peak, the specified {front_leg} front knee "
                    f"flexes by a median of {onset_amount:.1f} degrees across {len(flexion)} reps. "
                    "That describes this side-view motion; it does not set a correct depth."
                )
            else:
                observation = (
                    f"From movement onset to the lunge peak, the specified {front_leg} front knee "
                    f"opens by a median of {abs(onset_amount):.1f} degrees across {len(flexion)} reps. "
                    "That describes this side-view motion; it does not set a correct depth."
                )
            evidence = [*front_knee_change, *front_knee]
        else:
            spread = max(values) - min(values)
            observation = (
                f"The specified {front_leg} front-knee readings at the lunge peak span "
                f"{min(values):.1f}–{max(values):.1f} degrees across {len(values)} reps "
                f"(a {spread:.1f}-degree within-session spread). This describes repeatability "
                "and does not establish whether the bend is technically correct."
            )
            evidence = front_knee
        patterns.append(
            {
                "topic": "front knee through the lunge",
                "priority": "context",
                "observation": observation,
                "practice_focus": (
                    "Do not chase a generic knee-angle target; compare the same front leg across "
                    "your own controlled repetitions."
                ),
                "evidence_ids": [metric.metric_id for metric in evidence],
                "retrieval_topics": "front knee angle lunge side view measurement limits",
            }
        )

    paired_arm = []
    onset_by_rep = {_rep_key(metric): metric for metric in weapon_onset if _rep_key(metric)}
    peak_by_rep = {_rep_key(metric): metric for metric in weapon_peak if _rep_key(metric)}
    for rep_key in onset_by_rep.keys() & peak_by_rep.keys():
        onset_metric, peak_metric = onset_by_rep[rep_key], peak_by_rep[rep_key]
        paired_arm.append((onset_metric, peak_metric, peak_metric.value - onset_metric.value))
    if len(paired_arm) >= 2:
        median_change = median(item[2] for item in paired_arm)
        if weapon == "foil" and median_change >= 0.15:
            patterns.append(
                {
                    "topic": "foil arm timing",
                    "priority": "high",
                    "observation": (
                        f"The confirmed weapon arm continues to straighten between the reviewed "
                        f"movement-onset and lunge-peak frames in {len(paired_arm)} reps. "
                        "The pose estimate cannot see the blade or establish attack intent."
                    ),
                    "practice_focus": (
                        "For a simple, unopposed foil lunge, experiment with beginning the hand "
                        "extension just before the front foot launches; timing can change in a bout."
                    ),
                    "drill": (
                        "Perform five slow, simple foil lunges. Let the weapon hand begin first, "
                        "then launch the lunge; review the hand and front-foot timing together."
                    ),
                    "evidence_ids": [
                        metric.metric_id
                        for onset_metric, peak_metric, _ in paired_arm
                        for metric in (onset_metric, peak_metric)
                    ],
                    "retrieval_topics": "foil simple attack lunge arm extension timing",
                }
            )

    # Older saved reviews have peak elbow angles but not peak arm-extension
    # ratios. They still support a useful within-session shape comparison.
    if len(weapon_elbow_peak) >= 2:
        least_bent = max(weapon_elbow_peak, key=lambda item: item.value)
        most_bent = min(weapon_elbow_peak, key=lambda item: item.value)
        spread = least_bent.value - most_bent.value
        if spread >= 20 and least_bent.start_ms is not None and most_bent.start_ms is not None:
            patterns.append(
                {
                    "topic": "weapon arm at the finish",
                    "priority": "review",
                    "observation": (
                        f"At the reviewed peak at {most_bent.start_ms / 1000:.2f}s, the confirmed "
                        f"{weapon_arm} weapon elbow is more bent in the image-plane estimate "
                        f"than at {least_bent.start_ms / 1000:.2f}s "
                        f"({most_bent.value:.1f} versus {least_bent.value:.1f} degrees). "
                        "This is a comparison of arm shape at selected frames, not a diagnosis "
                        "of late extension, target reach, or incorrect technique."
                    ),
                    "practice_focus": (
                        f"Compare the weapon hand and elbow at {least_bent.start_ms / 1000:.2f}s "
                        f"and {most_bent.start_ms / 1000:.2f}s. If both attempts were meant to "
                        "finish at the same target with the same action, check whether the "
                        "different arm position was deliberate or whether you began pulling "
                        "the hand back before finishing. Repeat slowly toward the same target "
                        "to investigate; do not prescribe a fixed elbow angle."
                    ),
                    "evidence_ids": [least_bent.metric_id, most_bent.metric_id],
                    "retrieval_topics": "simple foil lunge weapon hand extension finish measurement limits",
                }
            )

    # A direct user question or selected metric sets priority. Otherwise choose the
    # strongest supported multi-rep pattern; do not invent a fault when none exists.
    question = request.question.lower()
    focus = next(
        (metric for metric in request.metrics if metric.metric_id == request.focus_metric_id),
        None,
    )
    requested_topic = None
    if "recover" in question:
        requested_topic = "recovery"
    elif "knee" in question or "bend" in question:
        requested_topic = "knee"
    elif "arm" in question or "extension" in question:
        requested_topic = "arm"
    elif any(
        word in question
        for word in ("lunge", "lunging", "overall form", "technique correct", "is it correct")
    ):
        requested_topic = "lunge"
    elif focus:
        requested_topic = (
            "knee"
            if "knee" in focus.name
            else "arm"
            if "arm" in focus.name
            else "recovery"
            if "recovery" in focus.name
            else None
        )
    if requested_topic == "recovery":
        selected = next(
            (item for item in patterns if item["topic"] == "recovery consistency"), None
        )
    elif requested_topic == "knee":
        selected = next(
            (item for item in patterns if item["topic"] == "front knee through the lunge"), None
        )
    elif requested_topic == "arm":
        selected = next(
            (item for item in patterns if item["topic"] == "foil arm timing"), None
        ) or next((item for item in patterns if item["topic"] == "weapon arm at the finish"), None)
    elif requested_topic == "lunge":
        # Broad lunge questions should prioritize mechanics, not recovery just
        # because a recovery pattern happened to be the highest-priority finding.
        selected = (
            next((item for item in patterns if item["topic"] == "foil arm timing"), None)
            or next(
                (item for item in patterns if item["topic"] == "weapon arm at the finish"), None
            )
            or next(
                (item for item in patterns if item["topic"] == "front knee through the lunge"), None
            )
        )
    else:
        selected = next((item for item in patterns if item["priority"] == "high"), None)
    if selected is None and patterns and requested_topic is None:
        selected = patterns[0]

    previous_text = " ".join(
        " ".join(
            str(part)
            for part in (
                review.get("summary", ""),
                review.get("next_drill", {}).get("name", "")
                if isinstance(review.get("next_drill"), dict)
                else "",
            )
        )
        for review in request.previous_reviews[-3:]
    ).lower()
    asks_about_history = any(
        phrase in question
        for phrase in (
            "previous review",
            "last session",
            "previous session",
            "last practice",
            "last time",
            "previously",
            "we talked about",
            "talked about before",
            "did i practice",
            "did that cue",
            "same cue",
            "what did we work on",
            "compare with last",
            "compare to last",
        )
    )
    previous_topics = [
        topic
        for topic, words in (
            ("recovery consistency", ("recover", "return to en-garde", "return to en garde")),
            ("front knee through the lunge", ("knee", "bend")),
            ("foil arm timing", ("arm extension", "weapon arm", "hand extension")),
        )
        if asks_about_history and any(word in previous_text for word in words)
    ]

    return {
        "capture_context": {
            "weapon": weapon,
            "weapon_arm": weapon_arm,
            "front_leg": front_leg,
            "facing": profile.get("facing", "unknown"),
            "camera_motion": profile.get("camera_motion", "unknown"),
        },
        "reviewed_repetition_count": len(grouped),
        "patterns": patterns[:4],
        "selected_focus": selected,
        "requested_topic": requested_topic,
        "previous_coaching_topics": previous_topics,
        "continuity_note": (
            "Previous reviews are context only. Mention prior coaching only when the athlete asks "
            "to compare or follow up; never let it replace the current question."
        ),
        "selection_note": (
            "Answer the current question first. For a broad lunge question, prioritize knee or weapon-arm mechanics; discuss recovery only when explicitly requested. Give the broader picture and one useful cue."
        ),
        "guardrails": [
            "Never compare left and right as if they should match.",
            "Do not invent an ideal angle, range, speed, or universal technique target.",
            "A pose measurement or tracking-quality value is not a correctness score.",
            "If no repeated, reliable pattern supports a correction, say what cannot be concluded and offer one useful next recording or practice step.",
        ],
    }
