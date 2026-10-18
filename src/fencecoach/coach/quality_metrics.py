"""Transparent conversation-level proxies; semantic acceptance still needs review."""

import re

from fencecoach.coach.claim_check import sentences, stems
from fencecoach.coach.number_trace import mentions


def repetition(turns):
    values, advice = [], []
    pairs = 0
    for previous, current in zip(turns, turns[1:]):
        if not previous.get("answer") or not current.get("answer"):
            continue
        pairs += 1

        def cited(row):
            supplied = {float(m["value"]) for m in row.get("packet", {}).get("measurements", [])}
            return {
                float(m["value"]) for m in mentions(row["answer"]) if float(m["value"]) in supplied
            }

        shared = cited(previous) & cited(current)
        if shared:
            values.append({"turn": current["turn"], "shared_values": sorted(shared)})

        def cues(row):
            return [
                stems(s)
                for s in sentences(row["answer"])
                if re.search(
                    r"\b(?:general|teaching|try|keep|practice|focus|aim|should|guidance)\b", s, re.I
                )
            ]

        if any(
            len(a & b) / max(1, len(a | b)) >= 0.55 for a in cues(previous) for b in cues(current)
        ):
            advice.append(current["turn"])
    return {
        "consecutive_pairs": pairs,
        "repeated_value_pairs": len(values),
        "repeated_advice_pairs": len(advice),
        "value_details": values,
        "advice_turns": advice,
        "definition": "Exact shared measurement values; advice content-word Jaccard >=0.55. Includes requested repeats/comparisons; inspect context before treating as a fault.",
    }


def response_kind(turn):
    answer, packet = turn.get("answer") or "", turn.get("packet", {})
    parts = sentences(answer)
    if not answer:
        return "provider_error"
    if parts and all(s.endswith("?") for s in parts):
        clarification = packet.get("clarification") or {}
        options = clarification.get("options", [])
        concrete = len(options) >= 2 and all(o["label"].lower() in answer.lower() for o in options)
        return "question_with_concrete_options" if concrete else "bare_question"
    decline = re.search(
        r"\b(?:cannot|can't|don't have|do not have|not assessed|unavailable|unsupported|cannot judge|lack)\b",
        answer,
        re.I,
    )
    partial = bool(mentions(answer)) or bool(
        re.search(
            r"\b(?:general advice|general guidance|general teaching|teaching material|reference material)\b",
            answer,
            re.I,
        )
    )
    if decline:
        return "useful_partial_proxy" if partial else "decline_without_partial_proxy"
    return "direct_or_other"


def verdict_without_basis(turn):
    answer = turn.get("answer") or ""
    if re.search(r"\b(?:not|cannot|can't|doesn't|do not)\b", answer, re.I):
        return False
    supported = any(
        a.get("status") in {"consistent", "inconsistent"}
        for a in turn.get("packet", {}).get("assessments", [])
    )
    personal = re.search(
        r"\byour\b.{0,80}\b(?:looks? good|is good|correct|perfect|ideal|on track|within.*expected)\b",
        answer,
        re.I,
    )
    return bool(personal and not supported)
