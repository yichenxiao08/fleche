"""Small provenance-bound answer units, selected before either model is called.

Models select units, not arbitrary claims. Units retain feature, phase, rep, units
and source together so a valid number cannot be moved to a different measurement.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from fencecoach.coach.analysis import _rep_key
from fencecoach.coach.grounding import unsupported_claims
from fencecoach.coach.intent import (
    arm_roles,
    mentioned_rep_numbers,
    question_topics,
    wants_all_reps,
    wants_rep_comparison,
)
from fencecoach.coach.reviewed import reviewed_claim_issues, select_feedback
from fencecoach.coach.technique_evidence import (
    current_session_context,
    question_scoped_session_context,
    rep_comparison_result,
    requested_feature_names,
)
from fencecoach.comparisons import comparable_capture
from fencecoach.rag.knowledge import search_knowledge
from fencecoach.schemas import CoachRequest

LABELS = {
    "weapon_elbow_angle": "sword-elbow angle",
    "non_weapon_elbow_angle": "non-sword elbow angle",
    "weapon_arm_direction": "sword-arm direction relative to the image horizontal",
    "non_weapon_arm_direction": "non-sword arm direction relative to the image horizontal",
    "projected_torso_tilt": "torso lean from upright in the image",
    "rear_knee_angle": "rear-knee angle",
    "front_knee_angle": "front-knee angle",
    "estimated_active_recovery_time": "estimated active recovery duration",
    "finish_to_guard_time": "finish-to-guard interval, including any hold",
    "action_to_lunge_time": "action-to-lunge interval",
    "feet_separation_leg_lengths": "feet separation",
}

RULE_FEATURES = {
    "front_knee_shallow": ("front_knee_angle", "lunge_finish"),
    "rear_knee_bent": ("rear_knee_angle", "lunge_finish"),
    "torso_pitch_change": ("forward_torso_pitch_change", "lunge_finish"),
    "knee_past_toe": ("front_knee_ahead_of_toe", "lunge_finish"),
    "arm_direction": ("weapon_arm_direction", "lunge_finish"),
    "guard_not_restored": ("guard_stance_change", "returned_guard"),
}


@dataclass
class Unit:
    id: str
    text: str
    kind: str
    evidence: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


@dataclass
class Packet:
    question: str
    units: list[Unit]
    sources: dict
    has_measurements: bool
    has_library: bool
    content_fallback: bool

    def contract(self):
        return {
            "units": [asdict(u) for u in self.units],
            "has_measurements": self.has_measurements,
            "has_library": self.has_library,
            "content_fallback": self.content_fallback,
        }


def number(value):
    return f"{float(value):.1f}".rstrip("0").rstrip(".")


def time_number(value):
    return f"{float(value):.1f}"


def label(feature):
    return LABELS.get(
        feature, feature.replace("_", " ").replace(" at peak", " at the detected peak")
    )


def _sentence(record):
    value, unit = record["value"], record.get("unit", "")
    if unit == "ms":
        value, unit = value / 1000, "seconds"
    unit = {"deg": "degrees", "s": "seconds"}.get(unit, unit)
    rep = record.get("rep")
    where = f" in rep {rep}" if rep is not None else " in this session"
    phase = record.get("phase")
    if phase:
        where += " during " + phase.replace("_", " ")
    timestamp = record.get("time_seconds")
    if timestamp is not None:
        where += f" ({time_number(timestamp)} seconds)"
    name = label(record["feature"])
    value_text = time_number(value) if unit in {"s", "seconds", "second"} else number(value)
    observed = f"your {name} measured {value_text} {unit}{where}"
    ref = record.get("reference_range")
    if ref:
        match = min(ref) <= record["value"] <= max(ref)
        direction = "lower" if record["value"] < min(ref) else "higher"
        shape = {
            "rear_knee_angle": ("rear leg was more bent", "rear leg was straighter"),
            "front_knee_angle": ("front knee was more bent", "front knee was straighter"),
            "projected_torso_tilt": ("torso was more upright", "torso leaned farther from upright"),
            "weapon_elbow_angle": ("sword elbow was more bent", "sword elbow was straighter"),
            "non_weapon_elbow_angle": (
                "non-sword elbow was more bent",
                "non-sword elbow was straighter",
            ),
            "estimated_active_recovery_time": (
                "active recovery interval was shorter",
                "active recovery interval was longer",
            ),
            "finish_to_guard_time": (
                "finish-to-guard interval was shorter",
                "finish-to-guard interval was longer",
            ),
        }.get(record["feature"])
        prefix = (
            f"Your {name} matched the reference range"
            if match
            else f"Your {shape[direction == 'higher']} than in the reference examples"
            if shape
            else f"Your {name} was {direction} than the reference range"
        )
        current_range = record.get("current_range")
        if (
            not match
            and current_range
            and max(current_range) >= min(ref)
            and min(current_range) <= max(ref)
        ):
            prefix = f"Your median {name} was {direction} than the reference range, although the sampled ranges overlapped"
        return prefix + "; " + observed + "."
    if "elbow_angle" in record["feature"]:
        role = (
            "non-sword"
            if record["feature"].startswith("non_weapon")
            else "sword"
            if record["feature"].startswith("weapon")
            else record["feature"].split("_")[0]
        )
        bend = "had some bend" if float(value) < 180 else "was straight in the image"
        return f"Your {role} elbow {bend}{where}; the included angle was {value_text} {unit}."
    return observed[0].upper() + observed[1:] + "."


def _guidance_variants(doc, excerpt, question):
    """Small authored paraphrases whose predicates occur in the retrieved entry.

    These are voice choices, not new rules or generated technique claims.
    """
    text = " ".join(excerpt.lower().split())
    roles = arm_roles(question)
    if "reaches forward toward the target" in text and roles != ("non_weapon",):
        return ["For a simple lunge, reach your sword arm toward the target."]
    if "extends back behind the fencer" in text or "extends behind you" in text:
        return ["In the traditional lunge finish, the non-sword arm extends behind you."]
    if "en garde" in text and "ready for the next action" in text:
        return ["Recovery brings you back to en garde, ready for the next action."]
    return []


@lru_cache(maxsize=24)
def _snapshot(serialized):
    request = CoachRequest.model_validate_json(serialized)
    return current_session_context(request)


def canonical_snapshot(request):
    """Content-keyed cache invalidates on measurements, review or capture changes."""
    clean = request.model_copy(
        update={
            "question": "How did I do?",
            "conversation_history": [],
            "dialogue_state": None,
            "training_history": [],
            "session_history": [],
            "previous_reviews": [],
        }
    )
    return _snapshot(clean.model_dump_json())


def _guidance(question, topics):
    # Unknown named actions must match meaningful words, not conversational filler.
    query = " ".join(topics).replace("rear_leg", "rear knee").replace("front_leg", "front knee")
    special = re.findall(
        r"\b(?:blade|parry|force|injury|fl[eè]che|advance|retreat|guard|speed)\b", question, re.I
    )
    if not query:
        stop = {
            "how",
            "was",
            "is",
            "are",
            "my",
            "your",
            "the",
            "a",
            "an",
            "what",
            "why",
            "did",
            "do",
            "does",
            "give",
            "me",
            "from",
            "library",
            "coaching",
            "session",
            "this",
            "in",
            "at",
            "of",
            "for",
            "with",
            "can",
            "you",
            "should",
            "i",
            "that",
            "it",
            "one",
            "rep",
            "drill",
            "cue",
            "please",
            "exactly",
            "sure",
            "measured",
            "regarding",
            "control",
            "generate",
            "much",
            "were",
        }
        words = [w for w in re.findall(r"[a-z]+", question.lower()) if w not in stop]
        query = " ".join(dict.fromkeys(words))
    if special:
        query = " ".join(dict.fromkeys(special))
    named_drill = re.search(r"\b(?:a|an|the)\s+([a-z -]+?)\s+drill\b", question, re.I)
    drill_terms = set(re.findall(r"[a-z]+", named_drill.group(1).lower())) if named_drill else set()
    if drill_terms:
        query = " ".join(sorted(drill_terms))
    if not query:
        return []
    docs = search_knowledge(query, limit=3)
    relevant = []
    terms = set(re.findall(r"[a-z]+", query))
    roles = arm_roles(question)
    candidates = []
    for doc in docs:
        if drill_terms and not drill_terms.issubset(set(re.findall(r"[a-z]+", doc.text.lower()))):
            continue
        if not topics and not terms.issubset(set(re.findall(r"[a-z]+", doc.text.lower()))):
            continue
        paragraphs = [
            p.strip()
            for p in doc.text.split("\n\n")
            if p.strip() and not p.lstrip().startswith(("#", "Source", "http"))
        ]
        for paragraph in paragraphs:
            text = " ".join(paragraph.split())
            if roles == ("non_weapon",) and not re.search(
                r"\b(?:non[- ](?:weapon|sword)|rear|free|unarmed) arm\b", text, re.I
            ):
                continue
            if (
                roles == ("weapon",)
                and re.search(r"\b(?:non[- ](?:weapon|sword)|rear) arm\b", text, re.I)
                and not re.search(r"(?<!non-)(?<!non )\b(?:weapon|sword) arm\b", text, re.I)
            ):
                continue
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                wrong_role = (
                    roles == ("non_weapon",)
                    and re.search(r"(?<!non-)(?<!non )\b(?:weapon|sword) arm\b", sentence, re.I)
                    and not re.search(r"\b(?:non[- ](?:weapon|sword)|rear) arm\b", sentence, re.I)
                )
                if (
                    30 <= len(sentence) <= 350
                    and terms.intersection(re.findall(r"[a-z]+", sentence.lower()))
                    and not wrong_role
                    and not re.search(
                        r"\b(?:answer|describe|someone asks|do not infer|coach must|also called|different roles)\b",
                        sentence,
                        re.I,
                    )
                ):
                    score = len(terms.intersection(re.findall(r"[a-z]+", sentence.lower())))
                    score += 3 * bool(
                        re.search(
                            r"\b(?:toward|target|return|en garde|because|helps|means)\b",
                            sentence,
                            re.I,
                        )
                    )
                    if re.search(r"\b(?:why|matter)\b", question, re.I):
                        score += 4 * bool(
                            re.search(
                                r"\b(?:because|helps|means|ready|purpose|allows|does not|cannot)\b",
                                sentence,
                                re.I,
                            )
                        )
                    if re.search(r"\b(?:drill|change|cue|practice)\b", question, re.I):
                        score += 4 * bool(
                            re.search(
                                r"\b(?:try|practice|drill|repeat|push|reach|return|extend)\w*\b",
                                sentence,
                                re.I,
                            )
                        )
                    candidates.append((score, doc, sentence))
    if candidates:
        _, doc, sentence = max(candidates, key=lambda item: item[0])
        relevant.append((doc, sentence))
    return relevant[:1]


def build_packet(request):
    question = request.question
    topics = question_topics(question)
    if (
        "recovery" in topics
        and "speed" in topics
        and re.search(r"\b(?:it|that|this)\s+(?:fast|slow|quick)\w*\b", question, re.I)
    ):
        topics = [topic for topic in topics if topic != "speed"]
    explicit_general = bool(
        re.search(r"\b(?:in general|generally|not (?:my|this) (?:session|video))\b", question, re.I)
    )
    if request.dialogue_state and request.dialogue_state.scope == "general":
        explicit_general = True
    forbidden = bool(
        re.search(
            r"\b(?:blade|force|injury|real.world|metres per second|extension (?:onset|timing)|extend\w* .{0,20}before .{0,20}foot)\b",
            question,
            re.I,
        )
    )
    broad = bool(
        re.search(
            r"\b(?:how did i do|overall|whole session|all reps|every rep|best one|best rep)\b",
            question,
            re.I,
        )
    )
    if wants_rep_comparison(question) and not topics:
        broad = True
    # This cache is shared across provider failover; no provider-specific evidence session exists.
    valid_metrics = [m for m in request.metrics if m.confidence >= 0.65]
    evaluation = dict(request.technique_evaluation)
    evaluation["reps"] = [
        r
        for r in evaluation.get("reps", [])
        if r.get("status") not in {"unsupported", "unavailable"}
        and r.get("geometry_available", True)
    ]
    usable = request.model_copy(
        update={"metrics": valid_metrics, "technique_evaluation": evaluation}
    )
    if request.evidence_unavailable_reason:
        usable = usable.model_copy(
            update={"metrics": [], "technique_evaluation": {}, "reviewed_feedback": {}}
        )
    packet = json.loads(
        question_scoped_session_context(usable, snapshot=canonical_snapshot(usable))
    )
    original_reps = {r["rep_number"]: r for r in usable.technique_evaluation.get("reps", [])}
    duration_requested = bool(
        re.search(
            r"\b(?:how long|duration|elapsed|time|seconds|fast|slow|shortest|longest)\b",
            question,
            re.I,
        )
    )
    rows = []
    if (topics or broad) and not (forbidden or explicit_general):
        for rep in packet["per_rep_measurements"]:
            refs = {
                (r.get("metric"), r.get("phase")): r
                for r in rep["reference_comparisons"]
                if rep.get("reference_context", {}).get("status") == "available"
            }
            for record in rep["measures"].values():
                phase = record.get("phase")
                original = (
                    original_reps.get(rep["rep"], {})
                    .get("measurements", {})
                    .get(record["feature"], {})
                )
                timestamp = original.get("time_ms")
                ref = refs.get(
                    (
                        record["feature"],
                        "finish" if phase in {"lunge_finish", "lunge_hold"} else phase,
                    )
                )
                rows.append(
                    {
                        **record,
                        "time_seconds": timestamp / 1000
                        if isinstance(timestamp, (int, float))
                        else None,
                        **(
                            {
                                "reference_range": ref["reference_range"],
                                "reference_id": ref["evidence_id"],
                                "supported_change": ref.get("supported_change"),
                                "current_range": ref.get("current_range"),
                                "reference_record": {
                                    **ref,
                                    "reference_context": rep.get("reference_context", {}),
                                },
                            }
                            if ref and ref.get("reference_range")
                            else {}
                        ),
                    }
                )
            for phase in rep["phases"].values():
                for feature, value in phase["values"].items():
                    ref = refs.get((feature, phase["phase"]))
                    rows.append(
                        {
                            "evidence_id": phase["evidence_id"] + ":" + feature,
                            "feature": feature,
                            "value": value,
                            "unit": phase["units"].get(feature),
                            "phase": phase["phase"],
                            "rep": rep["rep"],
                            "time_seconds": phase["interval_seconds"][0],
                            **(
                                {
                                    "reference_range": ref["reference_range"],
                                    "reference_id": ref["evidence_id"],
                                    "supported_change": ref.get("supported_change"),
                                    "current_range": ref.get("current_range"),
                                    "reference_record": {
                                        **ref,
                                        "reference_context": rep.get("reference_context", {}),
                                    },
                                }
                                if ref and ref.get("reference_range")
                                else {}
                            ),
                        }
                    )
        rows.extend(
            {
                **record,
                "time_seconds": record.get("start_ms") / 1000
                if record.get("start_ms") is not None
                else None,
            }
            for record in packet["session_measurements"]
        )
        # Interval features have definitions even in older saved records without
        # an explicit phase field. Keep their exact value/event timestamp; never
        # replace a duration request with a posture reference just because of that.
        if duration_requested:
            timing_features = (
                ("estimated_active_recovery_time", "finish_to_guard_time")
                if "recovery" in topics
                else ("action_to_lunge_time",)
            )
            allowed_reps = {r["rep"] for r in packet["per_rep_measurements"]}
            for rep_number, original_rep in original_reps.items():
                if rep_number not in allowed_reps:
                    continue
                for feature in timing_features:
                    measurement = original_rep.get("measurements", {}).get(feature)
                    if measurement is None:
                        continue
                    identifier = f"rep:{rep_number}:measurement:{feature}"
                    if any(row["evidence_id"] == identifier for row in rows):
                        continue
                    value = (
                        measurement["value"] / 1000
                        if measurement["unit"] == "ms"
                        else measurement["value"]
                    )
                    rows.append(
                        {
                            "evidence_id": identifier,
                            "feature": feature,
                            "rep": rep_number,
                            "value": value,
                            "unit": "seconds"
                            if measurement["unit"] == "ms"
                            else measurement["unit"],
                            "phase": measurement.get("phase"),
                            "meaning": measurement.get("note", ""),
                            "time_seconds": measurement["time_ms"] / 1000
                            if measurement.get("time_ms") is not None
                            else None,
                        }
                    )
    # Preserve scalar evidence with explicit selection when canonical phase tags are unavailable.
    if not rows and not (forbidden or explicit_general or request.evidence_unavailable_reason):
        features = requested_feature_names(usable)
        for m in valid_metrics:
            relevant = m.name in features or ("recovery" in topics and "recovery" in m.name)
            if broad or relevant:
                rep = _rep_key(m)
                rep = int(rep.rsplit(":", 1)[-1]) if rep else None
                requested = request.dialogue_state.rep_numbers if request.dialogue_state else []
                if requested and rep not in requested:
                    continue
                rows.append(
                    {
                        "evidence_id": m.metric_id,
                        "feature": m.name,
                        "value": m.value,
                        "unit": m.unit,
                        "rep": rep,
                        "time_seconds": m.start_ms / 1000 if m.start_ms is not None else None,
                    }
                )
    requested_reps = set(
        request.dialogue_state.rep_numbers if request.dialogue_state else ()
    ) or mentioned_rep_numbers(question)
    if requested_reps:
        rows = [r for r in rows if r.get("rep") in requested_reps]
    rows = [
        r
        for r in rows
        if isinstance(r.get("value"), (int, float))
        and not isinstance(r["value"], bool)
        and math.isfinite(r["value"])
    ]
    wants_extension = "arm" in topics and bool(re.search(r"\bextension|\belbow", question, re.I))
    duration_requested = bool(
        re.search(
            r"\b(?:how long|duration|elapsed|time|seconds|fast|slow|shortest|longest)\b",
            question,
            re.I,
        )
    )

    def priority(row):
        ref = row.get("reference_range")
        gap = max(min(ref) - row["value"], row["value"] - max(ref), 0) if ref else 0
        extension = wants_extension and (
            "elbow" in row["feature"] or "arm_extension" in row["feature"]
        )
        return (
            not ("time" in row["feature"] or "duration" in row["feature"])
            if duration_requested
            else False,
            row["feature"] != "estimated_active_recovery_time"
            if duration_requested
            and "recovery" in topics
            and not re.search(r"\bfinish.to.guard|\bhold\b", question, re.I)
            else False,
            not extension if wants_extension else False,
            not bool(ref),
            -gap,
            row.get("rep") or 0,
        )

    rows.sort(key=priority)
    all_reps = wants_all_reps(question)
    selected = []
    topic_labels = {
        "arm": "sword arm",
        "front_leg": "front knee",
        "rear_leg": "rear leg",
        "torso": "torso",
        "recovery": "recovery",
        "speed": "speed",
        "distance": "distance",
        "lunge": "whole lunge",
    }
    groups = []
    for topic in topics:
        subjects = (
            [
                "non-sword arm"
                if role == "non_weapon"
                else f"{role} arm"
                if role in {"left", "right"}
                else "sword arm"
                for role in arm_roles(question)
            ]
            if topic == "arm"
            else [topic_labels.get(topic, topic)]
        )
        for subject in subjects:
            atom = usable.model_copy(update={"question": subject})
            features = requested_feature_names(atom)
            groups.append(
                [
                    r
                    for r in rows
                    if r["feature"] in features
                    or (topic == "recovery" and "recovery" in r["feature"])
                ]
            )
    groups = groups or [rows]
    scopes = (
        sorted(requested_reps)
        if len(requested_reps) > 1
        else sorted({r.get("rep") for r in rows if r.get("rep") is not None})
        if all_reps
        else [None]
    )
    for rep_number in scopes:
        for group in groups:
            choice = next(
                (r for r in group if rep_number is None or r.get("rep") == rep_number), None
            )
            if choice is not None and choice not in selected:
                selected.append(choice)
    if all_reps:
        selected.sort(key=lambda row: row.get("rep") or 0)
    units, sources = [], {}
    ranking = (
        rep_comparison_result(usable) if wants_rep_comparison(question) and not forbidden else None
    )
    if (
        ranking
        and wants_extension
        and not any(t in ranking["metric"] for t in ("elbow", "extension"))
    ):
        ranking = None
    if wants_rep_comparison(question) and not ranking:
        # A ranking needs a well-defined comparable measurement, not a global skill score.
        units.append(
            Unit(
                "scope",
                "I can compare a named measurement, but these records don't establish an overall best repetition.",
                "limit",
            )
        )
    if ranking:
        pick = (
            ranking["fastest"]
            if re.search(r"\b(?:fastest|quickest|shortest)\b", question, re.I)
            else ranking["slowest"]
            if re.search(r"\bslowest\b", question, re.I)
            else ranking["worst"]
            if re.search(r"\bworst\b", question, re.I)
            else ranking["best"]
        )
        if pick:
            text = (
                f"Rep {pick['rep']} is the {'farthest' if re.search(r'\bworst\b', question, re.I) else 'closest'} match on {ranking['scope']} among the supplied comparisons."
                if ranking["basis"] == "reference_similarity"
                else f"Rep {pick['rep']} has the requested extreme for {ranking['scope']}; this ranks that measurement, not overall technique."
            )
            key = "ranking:" + ranking["metric"]
            units.append(Unit("ranking", text, "observation", [key], [ranking]))
            sources[key] = ranking
            ranked_selected = [
                r for r in rows if r.get("rep") == pick["rep"] and r["feature"] == ranking["metric"]
            ][:1]
            if ranked_selected and not all_reps and len(requested_reps) < 2:
                selected = ranked_selected
            if request.dialogue_state and not all_reps and len(requested_reps) < 2:
                request.dialogue_state.rep_numbers = [pick["rep"]]
    for i, row in enumerate(selected):
        ids = [row["evidence_id"]] + ([row["reference_id"]] if row.get("reference_id") else [])
        text = _sentence(row)
        where = f"Rep {row['rep']}" if row.get("rep") is not None else "This session"
        variant = f"{where}: {text[0].lower() + text[1:]}"
        units.append(Unit(f"fact{i}", text, "observation", ids, [row], [variant]))
        sources[row["evidence_id"]] = row
        if row.get("reference_id"):
            sources[row["reference_id"]] = row["reference_record"]
    latest = question.rsplit("in this session:", 1)[-1]
    assessment_requested = bool(
        re.search(r"\b(?:good|bad|correct|better|fault|change|fix|should)\b", latest, re.I)
    )
    if (
        selected
        and assessment_requested
        and not any(row.get("reference_range") for row in selected)
    ):
        units.append(
            Unit(
                "limit",
                "I can't grade that or prescribe a correction without a matching approved reference.",
                "limit",
            )
        )
    if not selected and not explicit_general and not any(u.id == "ranking" for u in units):
        detail = (
            "The tracking confidence is too low for a personal correction."
            if request.metrics and not valid_metrics
            else "I don't have a reliable matching measurement for that in this session."
        )
        if forbidden:
            if re.search(r"\bblade\b", question, re.I):
                detail = "The pose records don't track the blade, so they can't assess your blade control."
            elif re.search(r"\b(?:real.world|metres per second)\b", question, re.I):
                detail = "The session has relative image-plane motion, but no calibration for real-world speed."
            elif re.search(r"\bforce\b", question, re.I):
                detail = "These pose measurements don't establish physical force."
            elif re.search(r"\bextension|\bextend", question, re.I):
                detail = "Arm shape is recorded, but extension onset relative to foot landing isn't measured."
        units.append(Unit("gap", detail, "gap"))
    # Authored feedback is stronger than an automatic rubric. Only exact scoped
    # submitted text can supply a cue; no inferred replacement drill is added.
    reviewed = select_feedback(usable, limit=1) if not explicit_general else []
    if reviewed:
        review_rep = reviewed[0]
        text = review_rep.get("main_issue") or review_rep.get("done_well")
        cue = review_rep.get("cue")
        matching_topics = question_topics(
            " ".join(str(review_rep.get(k, "")) for k in ("main_issue", "done_well", "cue"))
        )
        if not topics or set(topics).intersection(matching_topics):
            key = f"coach-review:{usable.reviewed_feedback.get('job_id', usable.session_id)}:revision-{usable.reviewed_feedback.get('revision')}:rep-{review_rep['rep_number']}"
            sources[key] = {"submitted_review": usable.reviewed_feedback, "rep": review_rep}
            if text and not reviewed_claim_issues(usable, str(text), []):
                units = [u for u in units if u.kind != "gap"]
                units.insert(
                    0,
                    Unit(
                        "review",
                        f"Your submitted review says, for rep {review_rep['rep_number']}: “{str(text).strip()}”",
                        "review",
                        [key],
                        [review_rep],
                    ),
                )
            if cue and not reviewed_claim_issues(usable, str(cue), []):
                units.append(
                    Unit(
                        "review_cue",
                        "Your reviewer’s cue is: “" + str(cue).strip() + "”",
                        "cue",
                        [key],
                        [review_rep],
                    )
                )
    for row in selected:
        if (
            row.get("supported_change")
            and not forbidden
            and not any(u.kind == "cue" for u in units)
        ):
            text = str(row["supported_change"]).strip()
            units.append(
                Unit(
                    "cue",
                    "The matched reference feedback suggests: " + text,
                    "cue",
                    [row["reference_id"]],
                    [row],
                )
            )
            break
    if (
        not any(u.kind == "cue" for u in units)
        and usable.technique_evaluation.get("coaching_mode") != "reference_comparison"
    ):
        for row in selected:
            finding = next(
                (
                    f
                    for r in usable.technique_evaluation.get("reps", [])
                    if r["rep_number"] == row.get("rep")
                    for f in r.get("findings", [])
                    if RULE_FEATURES.get(f.get("rule")) == (row["feature"], row.get("phase"))
                    and f.get("measurement", {}).get("value") == row["value"]
                    and f.get("measurement", {}).get("unit") == row["unit"]
                    and f.get("cue")
                ),
                None,
            )
            if finding:
                key = finding["id"]
                sources[key] = finding
                units.append(
                    Unit(
                        "rule_cue",
                        "The provisional solo-drill rule suggests: “" + finding["cue"] + "”",
                        "cue",
                        [key],
                        [finding],
                    )
                )
                break
    needs_library = (
        bool(re.search(r"\b(?:why|matter|change|drill|cue|good|should|explain)\b", question, re.I))
        or not selected
    )
    docs = (
        _guidance(question, topics)
        if needs_library and not any(u.kind == "cue" for u in units)
        else []
    )
    for doc, excerpt in docs:
        variations = _guidance_variants(doc, excerpt, question)
        canonical_text = (
            variations[0] if variations else "From the coaching library: “" + excerpt + "”"
        )
        units.append(
            Unit(
                "guidance",
                canonical_text,
                "guidance",
                [doc.source_id],
                [{"excerpt": excerpt}],
                ["The teaching cue is to reach your sword arm toward the target."]
                if variations and "sword arm toward" in canonical_text
                else [],
            )
        )
        sources[doc.source_id] = doc.model_dump()
    reviewed_available = any(u.kind == "review" for u in units)
    if (
        not selected
        and not docs
        and not reviewed_available
        and not any(u.id == "ranking" for u in units)
    ):
        units.append(
            Unit(
                "missing",
                "General advice, not drawn from this session: use a measurement designed for that aspect before drawing a technique conclusion."
                if forbidden
                else "General advice, not drawn from this session: film the relevant movement clearly from a fixed camera, with the whole body visible, so that reliable matching measurements can be collected.",
                "general",
            )
        )
    if re.search(r"\b(?:previous|last session|last practice|progress)\b", question, re.I):
        comparison = _history(usable, selected)
        units.append(comparison)
        sources.update(
            {key: record for key, record in zip(comparison.evidence, comparison.records)}
        )
    if (
        re.search(r"\b(?:baseline|usual|normal for me)\b", latest, re.I)
        and selected
        and not any(r.get("reference_range") for r in selected)
    ):
        metric = next(
            (
                m
                for m in valid_metrics
                if m.metric_id == selected[0]["evidence_id"] and m.baseline_value is not None
            ),
            None,
        )
        if metric:
            key = "baseline:" + metric.metric_id
            record = metric.model_dump(mode="json")
            value = metric.baseline_value / 1000 if metric.unit == "ms" else metric.baseline_value
            unit = "seconds" if metric.unit in {"ms", "s"} else metric.unit
            sources[key] = record
            units.append(
                Unit(
                    "baseline",
                    f"The supplied scalar baseline is {number(value)} {unit}; its capture provenance isn't recorded, so it doesn't establish a technique verdict or improvement.",
                    "comparison",
                    [key],
                    [record],
                )
            )
    if re.search(
        r"\b(?:practice history|training history|practice logs|how much did i practice|what did i practice)\b",
        latest,
        re.I,
    ):
        logs = usable.training_history[:1]
        if logs:
            log = logs[0]
            key = f"practice:{log.get('log_id', log.get('practiced_on', 'latest'))}"
            sources[key] = log
            units = [
                Unit(
                    "practice",
                    f"Your latest practice log records {log.get('duration_minutes')} minutes on {log.get('practiced_on')}, focused on {log.get('focus', 'the recorded drill')}. That's self-reported practice, not measured technique.",
                    "history",
                    [key],
                    [log],
                )
            ]
    latest = question.rsplit("in this session:", 1)[-1]
    if re.search(r"^\s*why\b", latest, re.I) and selected:
        feature = selected[0]["feature"]
        meaning = packet.get("feature_meanings", {}).get(feature) or selected[0].get("meaning")
        if meaning:
            key = "meaning:" + feature
            spoken_meanings = {
                "weapon_elbow_angle": "That angle tells us how bent your sword elbow was. It doesn't tell us when you started extending the arm.",
                "non_weapon_elbow_angle": "That angle describes the bend in your non-sword elbow. It doesn't assess your sword-arm extension.",
                "projected_torso_tilt": "This tells us how far your torso leaned from upright in the image. It doesn't establish your balance.",
                "rear_knee_angle": "The rear-knee angle describes how straight that leg was. It doesn't tell us how much force you produced.",
                "front_knee_angle": "The front-knee angle describes the bend in that leg. A different angle alone doesn't grade the whole lunge.",
                "weapon_arm_direction": "This describes where the sword arm pointed relative to the image horizontal. It's different from elbow bend or extension timing.",
                "non_weapon_arm_direction": "This describes the non-sword arm's direction. Its role is different from the arm holding your weapon.",
            }
            explanation = Unit(
                "meaning",
                spoken_meanings.get(feature, str(meaning)),
                "explanation",
                [key],
                [{"meaning": meaning}],
            )
            sources[key] = {"meaning": meaning}
            units = [explanation] + [u for u in units if u.kind in {"guidance", "cue"}]
    # Retain known protections independently of the model selection contract.
    # Only explicitly authorized submitted or measurement-triggered cues can
    # relax a corresponding technique rule; other warnings discard that unit.
    checked = []
    for unit in units:
        issues = unsupported_claims(unit.text, [])
        if unit.id in {"review", "review_cue"}:
            issues = reviewed_claim_issues(usable, unit.text, [])
        if unit.id == "rule_cue":
            issues = [
                i
                for i in issues
                if i != "Knee-depth corrections are not established by these measurements."
            ]
        if unit.id == "cue" and any(row.get("supported_change") for row in unit.records):
            issues = [
                i
                for i in issues
                if i != "Knee-depth corrections are not established by these measurements."
            ]
        if not issues:
            checked.append(unit)
    if not checked:
        checked = [
            Unit(
                "unverified",
                "I couldn't verify a supported answer for that request from the available records.",
                "gap",
            )
        ]
    return Packet(
        question,
        checked,
        sources,
        bool(selected) or reviewed_available,
        bool(docs),
        not selected and not docs and not reviewed_available,
    )


def _history(request, selected):
    for current in selected:
        for previous in request.session_history:
            comparable, reason = comparable_capture(
                request.capture_profile, previous.get("capture_profile", {})
            )
            if not comparable:
                continue
            match = next(
                (
                    m
                    for m in previous.get("metrics", [])
                    if m["name"] == current["feature"]
                    and m["unit"] == current["unit"]
                    and m.get("confidence", 0) >= 0.65
                    and m.get("phase") == current.get("phase")
                    and (
                        _rep_key_metric(m) == current.get("rep")
                        if current.get("rep") is not None
                        else _rep_key_metric(m) is None
                    )
                ),
                None,
            )
            if match:
                name = request.capture_profile.get("camera_setup_id", "the declared setup")
                identifier = f"previous:{previous['session_id']}:{match['metric_id']}"
                text = f"For the same declared camera setup, {name}, the previous session recorded {number(match['value'])} {match['unit']} for {label(current['feature'])}; a difference alone doesn't establish improvement."
                return Unit("history", text, "comparison", [identifier], [match])
    return Unit(
        "history",
        "I don't have a matching reliable measurement from a previous session with the same named camera setup, so I can't establish a change.",
        "gap",
    )


def _rep_key_metric(metric):
    match = re.search(
        r"(?:^|-)rep-(\d+)(?:-|$)|(?:^|-)recovery-(\d+)(?:-|$)", metric.get("metric_id", "")
    )
    return int(match.group(1) or match.group(2)) if match else None


def verify_rendered(text, units):
    """Exact unit allow-list, stronger than a bag-of-numbers check.

    No model-authored free text, altered unit, cue, dose, timestamp or attribution
    can be published even when its digits happen to exist elsewhere in the packet.
    """
    return text == " ".join(u.text for u in units)
