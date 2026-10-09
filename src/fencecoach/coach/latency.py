"""Small reply budgets and representative evidence for routine chat turns."""

import re


def wants_detail(question: str) -> bool:
    return bool(
        re.search(
            r"\b(detailed?|thorough|comprehensive)\b|in depth|step[ -]by[ -]step|all (?:reps|measurements)",
            question,
            re.I,
        )
    )


def compact_measurements(rows, question, profile, focus_id=None, limit=6, preferred_ids=()):
    """Keep actual source IDs and extrema; never invent an aggregate measurement."""
    question = question.lower()
    if "arm" in question or "hand" in question:
        terms, side = ("arm_extension", "elbow_angle"), profile.get("weapon_arm")
    elif "knee" in question or "leg" in question:
        terms, side = ("knee_angle", "knee_flexion"), profile.get("front_leg")
    elif "recover" in question or "return" in question:
        terms, side = ("recovery",), None
    else:
        terms, side = ("knee_angle", "arm_extension", "elbow_angle", "torso_tilt"), None
    focused = [r for r in rows if r["metric_id"] == focus_id]
    relevant = [r for r in rows if any(t in r["name"] for t in terms)]
    if side in {"left", "right"}:
        relevant = [
            r
            for r in relevant
            if not r["name"].startswith(("left_", "right_")) or r["name"].startswith(side + "_")
        ]
    relevant = relevant or rows
    relevant = sorted(relevant, key=lambda r: r["metric_id"] not in preferred_ids)
    groups = {}
    for row in relevant:
        groups.setdefault(row["name"], []).append(row)
    selected = list(focused)
    for group in groups.values():
        ordered = sorted(group, key=lambda r: r["value"])
        for row in (ordered[0], ordered[-1]):
            if row not in selected:
                selected.append(row)
    return [
        {
            k: r[k]
            for k in ("metric_id", "name", "value", "unit", "confidence", "start_ms", "end_ms")
            if k in r
        }
        for r in selected[:limit]
    ]


def compact_guidance(text, limit=650):
    """Keep complete leading sentences rather than cutting a recommendation halfway."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    ends = list(re.finditer(r"[.!?](?=\s|$)", head))
    return head[: ends[-1].end()] if ends else head.rsplit("\n", 1)[0]
