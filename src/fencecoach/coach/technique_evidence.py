"""Expose automatic per-rep rubric findings to the conversational coach."""

import json
import re

from fencecoach.schemas import KnowledgeSource


def selected_evaluation(request):
    evaluation = request.technique_evaluation
    reps = evaluation.get("reps", [])
    named = re.search(r"\brep(?:etition)?\s*(\d+)\b", request.question, re.I)
    if named:
        reps = [r for r in reps if r["rep_number"] == int(named[1])]
    words = set(re.findall(r"[a-z]+", request.question.lower()))
    findings = [f for r in reps for f in r["findings"]]
    findings.sort(key=lambda f: -len(words & set(re.findall(r"[a-z]+", f["observation"].lower()))))
    return {
        "version": evaluation.get("version"),
        "status": evaluation.get("status"),
        "findings": findings[:3],
        "rep_measurements": [
            {
                "rep_number": r["rep_number"],
                "selected_frame_ms": r.get("selected_frame_ms"),
                "measurements": r["measurements"],
                "unavailable": r["unavailable"],
            }
            for r in reps[:2]
        ],
        "timing_summary": evaluation.get("timing_summary"),
        "capture": evaluation.get("capture_requirements"),
        "limits": evaluation.get("limitations", []),
    }


def evaluation_source(request):
    return KnowledgeSource(
        source_id=f"technique:{request.session_id}:{request.technique_evaluation.get('version')}",
        source="Automatic basic-lunge rubric evaluation (unvalidated heuristics)",
        text=json.dumps(selected_evaluation(request), separators=(",", ":")),
    )


def evaluation_fallback(request):
    selected = selected_evaluation(request)
    findings = selected["findings"]
    if findings:
        f = findings[0]
        return f"The clearest check is rep {f['rep_number']} at {f['evidence_ms'] / 1000:.2f}s: {f['observation']} {f['cue']} Try a slow set and compare the same finish frame afterward. This is a basic-drill review flag, not a confirmed fault or a universal technique rule."
    unavailable = [gap for r in selected["rep_measurements"] for gap in r["unavailable"]]
    return (
        "The available measurements did not trigger a basic-drill flag. That doesn't establish that the lunge is correct. "
        + (
            unavailable[0]
            if unavailable
            else "Compare the selected finish and return frames against your intended drill and target height."
        )
    )


def evaluation_issues(request, reply, metrics):
    from fencecoach.coach.grounding import unsupported_claims

    findings = selected_evaluation(request)["findings"]
    rules = {f["rule"] for f in findings}
    allowed = set()
    if "front_knee_shallow" in rules:
        allowed.add("Knee-depth corrections are not established by these measurements.")
    issues = [i for i in unsupported_claims(reply, metrics) if i not in allowed]
    if "A reported measurement or timestamp is absent from supplied evidence." in issues:
        values = [float(m.value) for m in metrics]
        values += [float(m.value) / 1000 for m in metrics if m.unit == "ms"]
        values += [t / 1000 for m in metrics for t in (m.start_ms, m.end_ms) if t is not None]
        for rep in request.technique_evaluation.get("reps", []):
            for m in rep["measurements"].values():
                values.extend([m["value"], m["time_ms"] / 1000])
                if m["unit"] == "ms":
                    values.append(m["value"] / 1000)
        numbers = re.findall(
            r"(?<![\w-])(\d+(?:\.\d+)?)\s*(?:degrees?|deg\b|°|ratio\b|milliseconds|ms\b|seconds|s\b)",
            reply.lower(),
        )
        if all(any(abs(float(n) - v) <= max(0.1, abs(v) * 0.01) for v in values) for n in numbers):
            issues.remove("A reported measurement or timestamp is absent from supplied evidence.")
    if re.search(
        r"\b(?:perfect|flawless|definitely correct|proves|too slow|too fast|lost balance|heel lifted|heel lifts)\b",
        reply,
        re.I,
    ):
        issues.append(
            "Automatic rubric findings do not establish a global verdict, speed target, balance or foot contact."
        )
    return issues
