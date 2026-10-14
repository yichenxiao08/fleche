"""Retrieve and attribute submitted human feedback without inventing new faults."""

import json
import re

from fencecoach.schemas import KnowledgeSource


def select_feedback(request, limit=None):
    from fencecoach.coach.intent import corrected_subject

    review = request.reviewed_feedback
    if review.get("status") != "submitted":
        return []
    reps = sorted(review.get("reps", []), key=lambda rep: rep["rep_number"])
    question = corrected_subject(request.question).lower()
    named = re.search(r"\brep(?:etition)?\s*(\d+)\b", question)
    if named:
        selected = [r for r in reps if r["rep_number"] == int(named[1])]
        return selected[:limit] if limit is not None else selected
    if re.search(r"\b(?:last|final)\s+(?:rep|lunge|one)\b|\bmy last\b", question):
        return reps[-1:]
    if re.search(r"\b(?:first|opening)\s+(?:rep|lunge|one)\b|\bmy first\b", question):
        return reps[:1]
    topics = {
        "arm": ("arm", "hand", "sword", "target", "extension"),
        "knee": ("knee", "bend", "leg", "depth", "lower", "short"),
        "recovery": (
            "recovery",
            "recover",
            "guard",
            "return",
            "rear leg",
            "back leg",
            "rear foot",
            "heel",
        ),
        "torso": ("torso", "lean", "balance", "upright", "body"),
    }
    terms = {
        term for group in topics.values() if any(t in question for t in group) for term in group
    }

    def text_for(rep):
        text = " ".join(
            str(rep.get(k, ""))
            for k in ("main_issue", "evidence_description", "cue", "improvement", "done_well")
        ).lower()
        return text

    def score(rep):
        text = text_for(rep)
        return (
            sum(term in text for term in terms) * 4
            + (2 if rep.get("rating") == "correction" else 0)
            + bool(rep.get("main_issue"))
        )

    if (
        re.search(
            (
                r"\b(?:best|worst|strongest|weakest|compare|comparison)\b|"
                r"\bwhich (?:rep|lunge)\b|\bwhich of my lunges\b"
            ),
            question,
        )
        and limit is None
    ):
        return reps
    if terms and not any(any(term in text_for(rep) for term in terms) for rep in reps):
        return []
    ranked = sorted(reps, key=score, reverse=True)
    return ranked[: (2 if limit is None else limit)]


def feedback_source(request, reps):
    review = request.reviewed_feedback
    data = {
        "reviewer": review.get("reviewer"),
        "role": review.get("reviewer_role"),
        "role_verified": False,
        "provenance_policy": "These are submitted human observations for this source clip only. Statements about power, explosiveness or short distance are reviewer judgments, not measured force, speed or calibrated distance. Attribute them to the review; never transfer them to a different clip as observed facts.",
        "weapon": review.get("weapon"),
        "intended_drill": review.get("intended_drill"),
        "target_height": review.get("target_height"),
        "reps": [
            {
                k: (v[:700] if isinstance(v, str) else v)
                for k, v in rep.items()
                if k != "measurements"
            }
            for rep in reps
        ],
    }
    return KnowledgeSource(
        source_id=f"coach-review:{review.get('job_id', request.session_id)}:revision-{review['revision']}",
        source="Submitted technique feedback (reviewer role self-declared)",
        text=json.dumps(data, separators=(",", ":")),
    )


def reviewed_fallback(request):
    selected = select_feedback(request, 1)
    if not selected:
        return None
    rep = selected[0]
    when = rep.get("evidence_ms")
    if when is None:
        window = (request.reviewed_feedback.get("integration") or {}).get("corrected_windows", [])
        if len(window) >= rep["rep_number"]:
            when = window[rep["rep_number"] - 1]["start_ms"]
    anchor = f" at {when / 1000:.1f}s" if when is not None else ""
    issue = rep.get("main_issue") or rep.get("done_well") or "the reviewed movement"
    cue = (
        rep.get("cue") or "Repeat the intended drill and compare its finish with this reviewed rep."
    )
    check = rep.get("improvement") or "Compare the finish and full return to guard."
    intention = (
        " You marked this as deliberate, so treat it as a drill variation rather than an accidental habit."
        if rep.get("intentional") == "yes"
        else ""
    )
    return f"{cue.strip()} {check.strip()}\n\nYour review flags {issue.strip().rstrip('.')} in rep {rep['rep_number']}{anchor}.{intention}"


def reviewed_claim_issues(request, reply, metrics):
    """Human labels support their stated corrections, not unrelated diagnoses.

    Retain the original guard for injury, invented measurements and direct visual
    claims. Relax only categories explicitly represented in the submitted feedback.
    """
    from fencecoach.coach.grounding import unsupported_claims

    reps = select_feedback(request, 5)
    text = " ".join(
        str(r.get(k, ""))
        for r in reps
        for k in ("main_issue", "evidence_description", "cue", "improvement")
    ).lower()
    allowed = set()
    if "knee" in text or "leg" in text:
        allowed.add("Knee-depth corrections are not established by these measurements.")
        allowed.add("No validated angle target or depth verdict is available.")
    if "arm" in text and any(t in text for t in ("timing", "before", "early", "late")):
        allowed.add("Arm shape alone does not establish a timing fault.")
    # Review labels can establish a rep count; an exact count still has to match.
    count = len(request.reviewed_feedback.get("reps", []))
    if re.search(rf"\b{count}\s+(?:lunges|reps|repetitions)\b", reply):
        allowed.add("Describe measured intervals, not a verified action count.")
    issues = [issue for issue in unsupported_claims(reply, metrics) if issue not in allowed]
    # Feedback timestamps and nominal drill angles are not sampled pose values.
    if "A reported measurement or timestamp is absent from supplied evidence." in issues:
        known = [float(m.value) for m in metrics]
        known += [float(m.value) / 1000 for m in metrics if m.unit == "ms"]
        known += [t / 1000 for m in metrics for t in (m.start_ms, m.end_ms) if t is not None]
        known += [
            r[k] / 1000
            for r in reps
            for k in ("evidence_ms", "action_start_ms", "lunge_ms", "guard_ms")
            if r.get(k) is not None
        ]
        numbers = re.findall(
            r"(?<![\w-])(\d+(?:\.\d+)?)\s*(?:degrees?|deg\b|°|ratio\b|milliseconds|ms\b|seconds|s\b)",
            reply.lower(),
        )
        if all(any(abs(float(n) - v) <= max(0.1, abs(v) * 0.01) for v in known) for n in numbers):
            issues.remove("A reported measurement or timestamp is absent from supplied evidence.")
    if re.search(r"\b(?:perfect|flawless|always|never)\b", reply, re.I):
        issues.append(
            "Avoid absolute technique judgments or universal rules from this small reviewed clip."
        )
    return issues
