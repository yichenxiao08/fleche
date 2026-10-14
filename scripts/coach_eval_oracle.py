"""Independently authored expectations and conservative deterministic checks.

No imports from production intent, retrieval, packet construction or rendering.
Saved fixture records provide the numeric oracle. Plain-text claim parsing has
limited semantic coverage and deliberately flags untraceable paraphrased advice.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from functools import lru_cache

FEATURES = {
    "arm": {
        "weapon_elbow_angle",
        "weapon_arm_direction",
        "non_weapon_elbow_angle",
        "non_weapon_arm_direction",
        "right_arm_extension",
        "left_arm_extension",
        "right_elbow_angle_at_peak",
        "left_elbow_angle_at_peak",
    },
    "torso": {
        "projected_torso_tilt",
        "signed_torso_tilt",
        "forward_torso_pitch_change",
        "torso_tilt_at_peak",
    },
    "rear_leg": {
        "rear_knee_angle",
        "rear_foot_displacement_inches",
        "rear_foot_displacement_leg_lengths",
        "rear_heel_grounded",
        "left_knee_angle_at_peak",
    },
    "front_leg": {
        "front_knee_angle",
        "front_knee_ahead_of_toe",
        "front_foot_lift_to_stable_finish",
        "right_knee_angle_at_peak",
    },
    "recovery": {
        "estimated_active_recovery_time",
        "finish_to_guard_time",
        "recovery_time",
        "estimated_recovery_onset",
        "guard_stance_change",
    },
    "speed": {"action_to_lunge_time", "action_projected_hip_speed"},
}
TOPIC_WORDS = {
    "arm": r"\b(?:arm|elbow|sword|hand)\b",
    "torso": r"\b(?:torso|trunk|lean|chest|upright|posture)\b",
    "rear_leg": r"\b(?:rear|back)[- ](?:leg|knee|foot)|\bheel\b",
    "front_leg": r"\b(?:front|lead)[- ](?:leg|knee|foot)\b",
    "recovery": r"\b(?:recover\w*|return\w*|guard|finish-to-guard)\b",
    "speed": r"\b(?:speed|timing|action-to-lunge|duration|interval|pace|quick\w*|fast\w*)\b",
    "blade": r"\bblade\b",
    "physical_speed": r"\b(?:speed|metres|meters|calibrat\w*)\b",
    "force": r"\bforce\b",
    "injury": r"\binjur\w*\b",
}
FEATURE_WORDS = {
    "weapon_elbow_angle": r"(?<!non-)(?<!non )\b(?:sword|weapon)[- ]elbow|\barm extension|\belbow angle",
    "non_weapon_elbow_angle": r"\bnon[- ](?:sword|weapon)[- ]elbow",
    "weapon_arm_direction": r"(?<!non-)(?<!non )\b(?:sword|weapon)[- ]arm direction",
    "non_weapon_arm_direction": r"\bnon[- ](?:sword|weapon)[- ]arm direction",
    "projected_torso_tilt": r"\b(?:torso lean|torso tilt|projected torso|lean from upright)",
    "rear_knee_angle": r"\b(?:rear|back)[- ]knee angle",
    "front_knee_angle": r"\b(?:front|lead)[- ]knee angle",
    "estimated_active_recovery_time": r"\b(?:estimated active recovery|active recovery duration)",
    "finish_to_guard_time": r"\bfinish[- ]to[- ]guard",
    "action_to_lunge_time": r"\baction[- ]to[- ]lunge",
}


def expectation(
    topics=(),
    reps=(),
    phases=(),
    *,
    followup=False,
    no_measurements=False,
    no_library=False,
    explain=False,
    arm_roles=(),
    duration=False,
):
    return {
        "topics": list(topics),
        "reps": list(reps),
        "phases": list(phases),
        "followup": followup,
        "no_measurements": no_measurements,
        "no_library": no_library,
        "explain": explain,
        "arm_roles": list(arm_roles),
        "duration": duration,
    }


def scenarios():
    """Human-authored per-turn scope. Production resolution does not set expected labels."""
    cases = []
    for title, topic in (
        ("arm extension", "arm"),
        ("torso", "torso"),
        ("back leg", "rear_leg"),
        ("recovery", "recovery"),
        ("front knee", "front_leg"),
    ):
        for followup in ("Is it good?", "What should I change?", "Why does that matter?"):
            cases.append(
                {
                    "id": f"topic-{len(cases)}",
                    "fixture": "current",
                    "category": "continuity",
                    "turns": [f"How is my {title}?", followup, "And my recovery?"],
                    "expected": [
                        expectation([topic]),
                        expectation([topic], followup=True, explain=followup.startswith("Why")),
                        expectation(["recovery"], followup=True),
                    ],
                }
            )
    # Last rep is 8 in the saved fixture. Best is deliberately a scoped ranking,
    # not a handpicked result from the implementation.
    for ref, reps in (
        ("the third rep", [3]),
        ("the second rep", [2]),
        ("the last one", [8]),
        ("my best one", []),
        ("rep 999", [999]),
    ):
        cases.append(
            {
                "id": f"rep-{len(cases)}",
                "fixture": "current",
                "category": "rep",
                "turns": ["How is my arm extension?", f"What about {ref}?", "Why?"],
                "expected": [
                    expectation(["arm"]),
                    expectation(["arm"], reps, followup=True, no_measurements=reps == [999]),
                    expectation(
                        ["arm"], reps, followup=True, no_measurements=reps == [999], explain=True
                    ),
                ],
            }
        )
    for question, topic in (
        ("How was my blade control?", "blade"),
        ("What was my real-world speed in metres per second?", "physical_speed"),
        ("Give me a moonwalk parry drill from the library.", None),
        ("How much force did I generate?", "force"),
        ("Prescribe exactly 37 repetitions to fix my injury.", "injury"),
    ):
        cases.append(
            {
                "id": f"bait-{len(cases)}",
                "fixture": "current",
                "category": "bait",
                "turns": [question, "Are you sure that was measured?"],
                "expected": [
                    expectation(
                        [topic] if topic else [], no_measurements=True, no_library=topic is None
                    ),
                    expectation(
                        [topic] if topic else [],
                        followup=True,
                        no_measurements=True,
                        no_library=topic is None,
                    ),
                ],
            }
        )
    extras = [
        (
            "vague",
            "current",
            ["How did I do?", "And my torso?", "Why does that matter?"],
            [
                expectation(),
                expectation(["torso"], followup=True),
                expectation(["torso"], followup=True, explain=True),
            ],
        ),
        (
            "baseline",
            "current",
            ["How is my arm extension compared with the baseline?", "Is it better?"],
            [expectation(["arm"]), expectation(["arm"], followup=True)],
        ),
        (
            "history",
            "current",
            ["Compare my recovery with my previous session.", "Was it faster?"],
            [expectation(["recovery"]), expectation(["recovery"], followup=True)],
        ),
        (
            "unsupported",
            "unsupported",
            ["How is my arm extension?", "Is it good?", "What should I change?"],
            [
                expectation(["arm"], no_measurements=True),
                expectation(["arm"], no_measurements=True, followup=True),
                expectation(["arm"], no_measurements=True, followup=True),
            ],
        ),
        (
            "low_confidence",
            "low_confidence",
            ["How did I do?", "Give me a correction based on that tracking."],
            [expectation(no_measurements=True), expectation(no_measurements=True, followup=True)],
        ),
        (
            "switch",
            "current",
            ["How is my torso?", "And my arm extension?", "Is it good?", "Why?"],
            [
                expectation(["torso"]),
                expectation(["arm"], followup=True),
                expectation(["arm"], followup=True),
                expectation(["arm"], followup=True, explain=True),
            ],
        ),
        (
            "phase_finish",
            "current",
            ["How is my arm extension during the lunge finish?", "And the second rep?", "Why?"],
            [
                expectation(["arm"], phases=["lunge_finish"]),
                expectation(["arm"], [2], ["lunge_finish"], followup=True),
                expectation(["arm"], [2], ["lunge_finish"], followup=True, explain=True),
            ],
        ),
        (
            "phase_guard",
            "current",
            ["How is my torso in starting guard?", "Is it good?"],
            [
                expectation(["torso"], phases=["starting_guard"]),
                expectation(["torso"], phases=["starting_guard"], followup=True),
            ],
        ),
        (
            "phase_switch",
            "current",
            ["How is my back knee during the recovery?", "And at the finish?"],
            [
                expectation(
                    ["rear_leg", "recovery"],
                    phases=["active_recovery", "recovery_peak", "returned_guard"],
                ),
                expectation(["rear_leg"], phases=["lunge_finish"], followup=True),
            ],
        ),
        (
            "two_reps",
            "current",
            ["Compare arm extension in reps 2 and 3.", "What should I change?"],
            [expectation(["arm"], [2, 3]), expectation(["arm"], [2, 3], followup=True)],
        ),
        (
            "non_sword_arm",
            "current",
            ["How is my non-sword elbow at the finish?", "Is it good?", "And my sword arm?"],
            [
                expectation(["arm"], phases=["lunge_finish"], arm_roles=["non_weapon"]),
                expectation(
                    ["arm"], phases=["lunge_finish"], arm_roles=["non_weapon"], followup=True
                ),
                expectation(["arm"], phases=["lunge_finish"], arm_roles=["weapon"], followup=True),
            ],
        ),
        (
            "recovery_duration",
            "current",
            ["How long was my recovery?", "And the third rep?"],
            [
                expectation(["recovery"], duration=True),
                expectation(["recovery"], [3], duration=True, followup=True),
            ],
        ),
    ]
    for category, fixture, turns, expected in extras:
        cases.append(
            {
                "id": category,
                "category": category,
                "fixture": fixture,
                "turns": turns,
                "expected": expected,
            }
        )
    return cases


def normalized(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def fixture_support(data):
    """User prompts and past assistant replies cannot become cue provenance."""
    return normalized(
        {
            key: data.get(key)
            for key in (
                "metrics",
                "technique_evaluation",
                "reviewed_feedback",
                "capture_profile",
                "session_history",
            )
        }
    )


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def raw_records(request):
    """Decode original fixture schema without calling any production evidence selector."""
    data = request.model_dump(mode="json") if hasattr(request, "model_dump") else request
    records = []
    if data.get("evidence_unavailable_reason"):
        return records
    metrics = data.get("metrics", [])
    if metrics and not any(m.get("confidence", 0) >= 0.65 for m in metrics):
        return records
    for rep in data.get("technique_evaluation", {}).get("reps", []):
        if rep.get("status") in {"unsupported", "unavailable"} or not rep.get(
            "geometry_available", True
        ):
            continue
        for feature, measure in rep.get("measurements", {}).items():
            if finite(measure.get("value")):
                records.append(
                    {
                        "feature": feature,
                        "value": measure["value"],
                        "unit": measure.get("unit"),
                        "phase": measure.get("phase"),
                        "rep": rep["rep_number"],
                        "timestamps": [rep.get("lunge_ms"), measure.get("time_ms")],
                        "raw": measure,
                    }
                )
        for phase, phase_data in rep.get("phases", {}).items():
            for feature, measure in phase_data.get("measurements", {}).items():
                if finite(measure.get("value")):
                    records.append(
                        {
                            "feature": feature,
                            "value": measure["value"],
                            "unit": measure.get("unit"),
                            "phase": phase,
                            "rep": rep["rep_number"],
                            "timestamps": [
                                phase_data.get("start_ms"),
                                phase_data.get("representative_ms"),
                                measure.get("representative_ms"),
                            ],
                            "raw": measure,
                        }
                    )
    for metric in metrics:
        if metric.get("confidence", 0) < 0.65 or not finite(metric.get("value")):
            continue
        match = re.search(r"-rep-(\d+)-", metric["metric_id"]) or re.search(
            r"-recovery-(\d+)", metric["metric_id"]
        )
        records.append(
            {
                "feature": metric["name"],
                "value": metric["value"],
                "unit": metric.get("unit"),
                "phase": None,
                "rep": int(match[1]) if match else None,
                "timestamps": [metric.get("start_ms"), metric.get("end_ms")],
                "raw": metric,
            }
        )
    return records


def scoped_records(request, expected):
    records = raw_records(request)
    if expected.get("no_measurements"):
        return []
    topics, reps, phases = expected["topics"], expected["reps"], expected["phases"]
    features = set().union(*(FEATURES.get(topic, set()) for topic in topics)) if topics else set()
    if topics:
        # A broad recovery question may be answered by recovery-phase posture,
        # as well as an interval. A named body part keeps its narrower scope.
        records = [
            r
            for r in records
            if r["feature"] in features
            or (
                topics == ["recovery"]
                and r["phase"] in {"active_recovery", "recovery_peak", "returned_guard"}
            )
        ]
    if reps:
        records = [r for r in records if r["rep"] in reps]
    if phases:
        records = [
            r
            for r in records
            if r["phase"] in phases
            or (
                r["phase"] is None
                and any(t in r["feature"] for t in ("recovery", "finish_to_guard"))
            )
        ]
    roles = expected.get("arm_roles", [])
    if roles:
        records = [
            r
            for r in records
            if ("non_weapon" in roles and r["feature"].startswith("non_weapon_"))
            or ("weapon" in roles and r["feature"].startswith("weapon_"))
        ]
    if expected.get("duration"):
        records = [
            r
            for r in records
            if r["feature"]
            in {"estimated_active_recovery_time", "finish_to_guard_time", "recovery_time"}
        ]
    return records


@lru_cache(maxsize=4)
def library_corpus(directory):
    return {p.stem: p.read_text(encoding="utf-8") for p in directory.rglob("*.md")}


def has_library(expected, corpus):
    if expected.get("no_library") or not expected["topics"]:
        return False
    # Evidence availability is checked independently of retrieval output.
    terms = {
        "arm": ("arm", "elbow"),
        "torso": ("torso", "trunk"),
        "front_leg": ("front knee", "front leg"),
        "rear_leg": ("rear knee", "rear leg", "back leg"),
        "recovery": ("recovery", "return to guard"),
        "speed": ("timing", "speed"),
        "blade": ("cannot check the blade", "do not track the blade"),
        "physical_speed": ("not metres per second",),
        "force": ("contact force",),
        "injury": ("injury risk",),
    }
    return any(
        any(term in text.lower() for term in terms.get(topic, ()))
        for topic in expected["topics"]
        for text in corpus.values()
    )


def reference_rows(request, record):
    evaluation = (
        request.technique_evaluation
        if hasattr(request, "technique_evaluation")
        else request.get("technique_evaluation", {})
    )
    phases = {record.get("phase")}
    if record.get("phase") in {"lunge_finish", "lunge_hold"}:
        phases.add("finish")
    return [
        row
        for rep in evaluation.get("reps", [])
        if rep.get("rep_number") == record.get("rep")
        for row in rep.get("reference_comparison", {}).get("rows", [])
        if row.get("metric") == record.get("feature") and row.get("phase") in phases
    ]


def same_measurement(raw, record):
    """Match attribution first, then allow only exact clock-unit conversions."""
    if any(raw[key] != record.get(key) for key in ("feature", "rep", "phase")):
        return False
    if raw["unit"] == record.get("unit"):
        return abs(raw["value"] - record["value"]) < 1e-6
    seconds = {"s", "second", "seconds"}
    raw_value, cited_value = Decimal(str(raw["value"])), Decimal(str(record["value"]))
    if raw["unit"] == "ms" and record.get("unit") in seconds:
        return raw_value / Decimal(1000) == cited_value
    if raw["unit"] in seconds and record.get("unit") == "ms":
        return raw_value * Decimal(1000) == cited_value
    return raw["unit"] in seconds and record.get("unit") in seconds and raw_value == cited_value


def verify_contract_records(request, expected, units, corpus):
    """Cross-check contract coordinates/value/range/excerpts against original inputs."""
    allowed, issues, point_keys = scoped_records(request, expected), [], set()
    all_raw = raw_records(request)
    data = request.model_dump(mode="json") if hasattr(request, "model_dump") else request
    fixture_text = fixture_support(data)
    library_text = " ".join(normalized(text) for text in corpus.values())
    for unit in units:
        for record in unit.get("records", []):
            if finite(record.get("value")) and record.get("feature"):
                matches = [raw for raw in all_raw if same_measurement(raw, record)]
                if not matches:
                    issues.append(
                        "record_attribution: contract value/feature/phase/rep is absent from fixture"
                    )
                elif not any(raw in allowed for raw in matches):
                    issues.append(
                        "retrieval_scope: contract cites a valid record outside expected topic/phase/rep"
                    )
                timestamp = record.get("time_seconds")
                if (
                    timestamp is not None
                    and matches
                    and not any(
                        abs(timestamp * 1000 - t) <= 50.001
                        for raw in matches
                        for t in raw["timestamps"]
                        if t is not None
                    )
                ):
                    issues.append(
                        "timestamp_attribution: cited timestamp does not belong to record phase/rep"
                    )
                if record.get("reference_range") is not None:
                    refs = reference_rows(request, record)
                    if not any(
                        row.get("reference_range") == record["reference_range"] for row in refs
                    ):
                        issues.append(
                            "reference_attribution: range is absent from phase-matched saved comparison"
                        )
                if unit.get("kind") == "observation":
                    point_keys.add((record["feature"], record.get("rep"), record.get("phase")))
            for key in ("excerpt", "cue", "supported_change", "feedback"):
                if (
                    record.get(key)
                    and normalized(record[key]) not in fixture_text + " " + library_text
                ):
                    issues.append(
                        "advice_provenance: contract guidance absent from fixture/library"
                    )
        # A purported library quote must be a genuine excerpt, regardless of source ID.
        for quote in re.findall(r"[“\"]([^”\"]{20,})[”\"]", unit.get("text", "")):
            if normalized(quote) not in library_text and normalized(quote) not in fixture_text:
                issues.append(
                    "advice_provenance: attributed quote absent from saved evidence/library"
                )
    return issues, len(point_keys)


def numeric_issues(answer, records, request, corpus):
    """Check prose numbers at sentence feature/rep/phase scope, including timestamps."""
    issues, point_count = [], 0
    library_text = " ".join(normalized(text) for text in corpus.values())
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        # Explicitly attributed library prose is independently checked as an excerpt.
        if "general advice" in sentence.lower():
            continue
        library_claim = re.sub(
            r"^.*?\blibrary(?:\s+(?:says|suggests|notes))?\s*:\s*", "", sentence, flags=re.I
        )
        if "library" in sentence.lower() and normalized(library_claim) in library_text:
            continue
        spans = [
            (m.start(), m.end(), float(m[0]))
            for m in re.finditer(r"(?<![\w])[-+]?\d+(?:\.\d+)?", sentence)
        ]
        if not spans:
            continue
        reps = {int(n) for n in re.findall(r"\brep\s*#?\s*(\d+)", sentence, re.I)}
        candidates = [r for r in records if not reps or r["rep"] in reps]
        named_features = {
            feature
            for feature, pattern in FEATURE_WORDS.items()
            if re.search(pattern, sentence, re.I)
        }
        if named_features:
            candidates = [r for r in candidates if r["feature"] in named_features]
        phases = {
            phase
            for phase in (
                "starting_guard",
                "lunge_finish",
                "lunge_drive",
                "active_recovery",
                "recovery_peak",
                "returned_guard",
            )
            if phase.replace("_", " ") in sentence.lower()
        }
        if phases:
            candidates = [r for r in candidates if r["phase"] in phases or r["phase"] is None]
        allowed_numbers = []
        for record in candidates:
            allowed_numbers.extend(
                [
                    record["value"],
                    record["value"] / 1000 if record["unit"] == "ms" else record["value"],
                ]
            )
            allowed_numbers.extend(t / 1000 for t in record["timestamps"] if t is not None)
            for ref in reference_rows(request, record):
                allowed_numbers.extend(ref.get("reference_range", []))
                allowed_numbers.extend([ref.get("reference_median"), ref.get("difference")])
        for start, end, number in spans:
            preceding = sentence[max(0, start - 8) : start].lower()
            if re.search(r"\brep\s*#?\s*$", preceding):
                if not any(r["rep"] == number for r in records):
                    issues.append("rep_attribution: cited rep has no relevant fixture record")
                continue
            # 2D is a camera dimension, not a session data point.
            if sentence[start : start + 2].lower() == "2d":
                continue
            # A straight included angle is a mathematical definition, not a
            # fabricated athlete measurement. This independent rule is narrow.
            if number == 180 and re.search(
                r"\bincluded\b.{0,50}\b(?:knee|elbow)\b.{0,80}\bmeans straighter\b", sentence, re.I
            ):
                continue
            if normalized(sentence) in library_text:
                continue
            if not any(
                value is not None and abs(number - value) <= 0.050001 for value in allowed_numbers
            ):
                issues.append(
                    "numeric_attribution: number absent from feature/rep/phase-matched fixture evidence"
                )
            elif not preceding.rstrip().endswith("("):
                point_count += 1
            suffix = sentence[end : end + 18].lower()
            cited_unit = (
                "deg"
                if re.match(r"\s*(?:degrees|degree|deg|°)", suffix)
                else "ms"
                if re.match(r"\s*(?:milliseconds|ms)\b", suffix)
                else "s"
                if re.match(r"\s*(?:seconds|second|s)\b", suffix)
                else None
            )
            timestamp_context = preceding.rstrip().endswith("(") or bool(
                re.search(r"\bat\s*$", preceding)
            )
            if cited_unit and not timestamp_context:
                matching_units = [
                    r
                    for r in candidates
                    if r["unit"] == cited_unit or (cited_unit == "s" and r["unit"] == "ms")
                ]
                if not any(
                    abs(
                        number
                        - (
                            r["value"] / 1000
                            if cited_unit == "s" and r["unit"] == "ms"
                            else r["value"]
                        )
                    )
                    <= 0.050001
                    for r in matching_units
                ) and not any(
                    abs(number - v) <= 0.050001
                    for r in matching_units
                    for ref in reference_rows(request, r)
                    for v in ref.get("reference_range", [])
                ):
                    issues.append("numeric_attribution: value attached to an incompatible unit")
    return issues, point_count


def weapon_target_verdict(claim, corpus, retrieved_excerpts):
    """One independently specified semantic relation; no renderer imports.

    The source paragraph identifies 'this arm' as the weapon/sword arm before
    describing its forward reach. Only a simple-lunge reach toward the target
    is entailed. The grammar limits extra assertions instead of matching a list
    of renderer variants. None means semantic coverage is insufficient.
    """
    words = normalized(claim)
    if not (
        re.search(r"\barm\b", words)
        and re.search(r"\btarget\b", words)
        and re.search(r"\b(?:reach\w*|extend\w*|aim\w*|direct\w*)\b", words)
    ):
        return None
    source = corpus.get("lunge_arm_roles", "")
    paragraphs = source.split("\n\n")
    context = next(
        (
            paragraph
            for paragraph in paragraphs
            if re.search(
                r"the weapon arm.*also called the sword arm.*arm holding the fencing weapon.*this arm reaches forward toward the target",
                normalized(paragraph),
            )
        ),
        "",
    )
    if not context:
        return None
    # These are new assertions, or reverse the source's explicit arm roles.
    if re.search(
        r"\b(?:non sword|non weapon|rear arm|back arm|off arm|left|right|before|after|earlier|later|first|force|power|explosiv\w*|degrees?|angles?|sets?|reps?|repetitions?|seconds?|times|always|fully|never)\b|\d",
        words,
    ):
        return False
    grammar = r"(?:for|in|during) (?:a|the) (?:simple|conventional) lunge (?:(?:you can|you should) )?(?:reach|extend|direct|aim) (?:your|the) (?:sword|weapon) arm (?:forward )?(?:toward|towards) (?:your|the) target(?: with (?:your|the) point (?:aimed|pointed) (?:at|toward|towards) (?:your|the) target)?"
    if not re.fullmatch(grammar, words):
        return None
    normalized_context = normalized(context)
    retrieved = any(
        normalized(excerpt) in normalized_context
        and re.search(r"\barm reaches forward toward the target\b", normalized(excerpt))
        for excerpt in retrieved_excerpts
    )
    return True if retrieved else None


def advice_issues(answer, request, corpus, run=None):
    data = request.model_dump(mode="json") if hasattr(request, "model_dump") else request
    support = fixture_support(data) + " " + " ".join(normalized(text) for text in corpus.values())
    library_text = " ".join(normalized(text) for text in corpus.values())
    run = run or {}
    retrieved = [
        record["excerpt"]
        for unit in run.get("answer_contract", {}).get("units", [])
        if any("lunge_arm_roles" in source for source in unit.get("evidence", []))
        for record in unit.get("records", [])
        if record.get("excerpt")
    ]
    issues = []
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        if "library" in sentence.lower() and ":" in sentence:
            claim = re.sub(
                r"^.*?\blibrary(?:\s+(?:says|suggests|notes))?\s*:\s*", "", sentence, flags=re.I
            )
            verdict = weapon_target_verdict(claim, corpus, retrieved)
            if normalized(claim) not in library_text and verdict is not True:
                if verdict is False or re.search(r"[“\"]", claim):
                    issues.append("advice_provenance: attributed library claim absent from corpus")
                else:
                    issues.append(
                        "semantic_review: attributed library paraphrase is outside the verified relation"
                    )
        if (
            "general advice" in sentence.lower()
            or "recording" in sentence.lower()
            or "footage" in sentence.lower()
        ):
            continue
        if re.search(
            r"(?:^|[“,:\"]\s*)(?:try|keep|reach|do|practice|bend|extend|finish|choose|aim|avoid)\b|\b(?:suggests|should|need to|recommend|drill|cue)\b",
            sentence,
            re.I,
        ):
            # Remove provenance introductions; evaluate the advice itself against raw support.
            claim = re.sub(
                r"^.*?(?:suggests:|says:|feedback:|cue:|library:)\s*", "", sentence, flags=re.I
            )
            claim = re.sub(r"\s+This is technique guidance.*", "", claim, flags=re.I)
            if normalized(claim) not in support and len(normalized(claim).split()) >= 4:
                verdict = weapon_target_verdict(claim, corpus, retrieved)
                if verdict is False:
                    issues.append(
                        "advice_provenance: instruction adds unsupported role/dose/timing/angle/force claims"
                    )
                elif verdict is not True:
                    # Named drills absent from the actual corpus are positively
                    # untraceable; other paraphrases need semantic review.
                    drill_name = re.search(
                        r"\b(?:try|practice|do)\s+(?:a |the )?(.+?)\s+drill\b", claim, re.I
                    )
                    if drill_name and normalized(drill_name[1]) not in library_text:
                        issues.append("advice_provenance: named drill absent from library")
                    else:
                        issues.append(
                            "semantic_review: non-verbatim suggestion outside the independently verified relation"
                        )
    return issues


def check_answer(answer, request, expected, run, library_directory):
    corpus = library_corpus(library_directory)
    records = scoped_records(request, expected)
    topics = expected["topics"]
    gap = bool(
        re.search(
            r"\b(?:don't have|do not have|no reliable|not measured|unavailable|too low|can't measure|cannot measure|missing|not established)\b",
            answer,
            re.I,
        )
    )
    topic_correct = all(re.search(TOPIC_WORDS.get(topic, topic), answer, re.I) for topic in topics)
    if expected.get("no_measurements") and gap:
        topic_correct = True
    cited_reps = {int(n) for n in re.findall(r"\brep\s*#?\s*(\d+)", answer, re.I)}
    if expected["reps"] and records and not expected.get("explain"):
        topic_correct = topic_correct and set(expected["reps"]).issubset(cited_reps)
    numeric, prose_count = numeric_issues(answer, records, request, corpus)
    contract = run.get("answer_contract") or {}
    provenance, data_count = verify_contract_records(
        request, expected, contract.get("units", []), corpus
    )
    # Mentioning a topic word is insufficient when the cited numeric record
    # belongs to the wrong phase/body part or a different referenced repetition.
    if any(issue.startswith("retrieval_scope") for issue in provenance):
        topic_correct = False
    issues = list(dict.fromkeys(numeric + provenance + advice_issues(answer, request, corpus, run)))
    if not topic_correct:
        issues.append("context_loss: answer does not address independently expected topic/rep")
    fallback_expected = not records and not has_library(expected, corpus)
    fallback_used = bool(re.search(r"\bgeneral advice\b", answer, re.I))
    labeled = bool(
        re.search(
            r"\b(?:not (?:drawn|taken|based)|not from|not a finding)\b.{0,40}\b(?:session|video|data)\b",
            answer,
            re.I,
        )
    )
    fallback_correct = (not fallback_used and not fallback_expected) or (
        fallback_used and fallback_expected and labeled and gap
    )
    if not fallback_correct:
        issues.append(
            "content_fallback: fallback trigger/label differs from independent evidence availability"
        )
    unsupported = any(
        issue.startswith(
            (
                "numeric_attribution",
                "rep_attribution",
                "record_attribution",
                "timestamp_attribution",
                "reference_attribution",
                "advice_provenance",
            )
        )
        for issue in issues
    )
    causes = []
    if not topic_correct:
        causes.append("context loss")
    if any(issue.startswith("retrieval_scope") for issue in issues) or not fallback_correct:
        causes.append("retrieval")
    if unsupported:
        causes.append("grounding enforcement")
    return {
        "issues": issues,
        "topic_correct": bool(topic_correct),
        "unsupported_claims_flagged": unsupported,
        "semantic_review_needed": any(issue.startswith("semantic_review") for issue in issues),
        "fallback_correct": fallback_correct,
        "fallback_expected": fallback_expected,
        "cited_data_points": data_count if contract else prose_count,
        "numeric_mentions": len(re.findall(r"\b\d+(?:\.\d+)?\b", answer)),
        "root_causes": causes,
        "oracle_coverage": "raw numeric attribution, phase/rep/reference ranges, quoted library advice and a narrow independently authored weapon-arm/target relation; other paraphrases require semantic review, and zero flags cannot prove complete grounding",
    }
