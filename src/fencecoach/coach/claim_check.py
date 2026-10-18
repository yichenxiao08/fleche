"""Verify explicit sentence citations; do not infer claims from lexical patterns.

This validates provenance and exact numeric/quoted support, not semantic entailment.
Wrong type labels, body parts, spatial reversals and causal meaning require review.
"""

import json
import re

from fencecoach.coach.number_trace import trace_numbers

STOP = set(
    [
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "and",
        "or",
        "for",
        "with",
        "your",
        "my",
        "you",
        "i",
        "it",
        "is",
        "are",
        "be",
        "at",
        "as",
        "this",
        "that",
        "these",
        "those",
        "should",
        "can",
        "could",
        "would",
        "will",
        "have",
        "has",
        "on",
        "from",
        "into",
        "than",
        "how",
        "what",
        "when",
        "while",
        "rather",
        "there",
        "by",
        "does",
        "do",
        "not",
        "no",
        "only",
        "general",
        "advice",
        "teaching",
        "material",
        "suggests",
        "measured",
        "measurements",
        "measurement",
        "degrees",
        "degree",
        "seconds",
        "second",
        "rep",
        "reps",
        "repetition",
        "repetitions",
        "target",
        "toward",
        "keep",
        "keeping",
    ]
)


def stems(text):
    words = re.findall(r"[a-z]+", text.lower())
    return {re.sub(r"(?:ing|ed|es|s)$", "", w) for w in words if w not in STOP and len(w) > 2}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])|\n+", text) if s.strip()]


def normalized(text):
    return " ".join(text.split())


TYPES = {"claim", "clarification", "acknowledgment", "reset", "summary"}


def citation_index(packet):
    index = {
        "packet:availability": packet.get("availability", {}),
        "packet:scope": packet.get("scope", {}),
        "packet:policy": {
            "text": packet.get("policy", ""),
            "assessment_basis": "Library cues are teaching material, not an approved pass/fail number.",
        },
    }
    for p in [packet, *packet.get("supplemental_packets", [])]:
        for row in p.get("measurements", []):
            index[row["evidence_id"]] = row
        for assessment in p.get("assessments", []):
            for row in assessment.get("relative", []):
                index[row["evidence_id"]] = row
    return index


def check_sentence(sentence, packet):
    """No lexical detection of anatomy, advice, assessment, priority or units."""
    reasons = []
    if not isinstance(sentence, dict):
        return {"text": str(sentence), "passed": False, "reasons": ["invalid_sentence_record"]}
    text, kind = sentence.get("text", ""), sentence.get("type")
    evidence = citation_index(packet)
    library = {
        g["source_id"]: g
        for p in [packet, *packet.get("supplemental_packets", [])]
        for g in p.get("general_guidance", [])
    }
    ids = sentence.get("evidence_ids", [])
    source_ids = sentence.get("library_ids", [])
    if kind not in TYPES or not isinstance(text, str) or not text.strip():
        reasons.append("invalid_sentence_record")
    # Non-claim turns deliberately bypass claim verification. The writer's type
    # labels are visible in traces and are not a semantic safety guarantee.
    if kind != "claim":
        return {**sentence, "passed": not reasons, "reasons": reasons, "numbers": None}
    if not isinstance(ids, list) or not isinstance(source_ids, list):
        return {**sentence, "passed": False, "reasons": ["invalid_citation_lists"]}
    if not ids and not source_ids:
        reasons.append("claim_has_no_citation")
    if any(i not in evidence for i in ids) or any(i not in library for i in source_ids):
        reasons.append("unknown_citation_id")
    cited = [evidence[i] for i in ids if i in evidence] + [
        library[i] for i in source_ids if i in library
    ]
    numeric = trace_numbers(text, cited)
    if not numeric["exact_only_passed"]:
        reasons.append("number_not_in_cited_evidence")
    quotes = sentence.get("library_quotes", [])
    for source_id in source_ids:
        supports = [
            q.get("quote", "")
            for q in quotes
            if isinstance(q, dict) and q.get("source_id") == source_id
        ]
        if not supports or not all(
            q and normalized(q) in normalized(library.get(source_id, {}).get("text", ""))
            for q in supports
        ):
            reasons.append("library_quote_not_in_cited_entry")
    # Explicitly tagged technique sentences must render their authored cue/drill
    # verbatim. No stem-overlap score, forbidden-word list or guessed entailment.
    if sentence.get("claim_kind") == "technique":
        cue = sentence.get("cue", "")
        if (
            not cue
            or normalized(cue) not in normalized(text)
            or not any(
                normalized(cue) in normalized(library[i]["text"])
                for i in source_ids
                if i in library
            )
        ):
            reasons.append("technique_not_in_cited_entry")
    return {**sentence, "passed": not reasons, "reasons": sorted(set(reasons)), "numbers": numeric}


def missing_next_step(packet):
    topic = (
        ", ".join(packet.get("scope", {}).get("topics", [])).replace("_", " ") or "that question"
    )
    if packet.get("clarification"):
        q = packet["clarification"]
        return q["question"] + " " + " or ".join(o["label"] for o in q.get("options", [])) + "?"
    if packet.get("measurements") and packet["measurements"][0].get("display"):
        row = packet["measurements"][0]
        return f"I can verify {row['display']} for {row['feature'].replace('_', ' ')} in rep {row.get('rep')}. Let's compare the same phase across reps."
    guidance = packet.get("general_guidance", [])
    if guidance:
        # A literal source sentence is a useful partial answer even if the
        # writer's unsupported interpretation was removed.
        cue = sentences(guidance[0]["text"])[0]
        return "As general guidance: " + cue
    return f"I don't have a verified measurement or library cue for {topic}. We can review a saved rep on that subject."


def filter_reply(answer, packet):
    parse_error = None
    try:
        if isinstance(answer, str):
            payload = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip()))
        else:
            payload = answer
        rows = payload["sentences"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("No sentence records")
    except (ValueError, KeyError, TypeError) as exc:
        rows = [{"type": "invalid", "text": str(answer)}]
        parse_error = type(exc).__name__
    checks = [check_sentence(row, packet) for row in rows]
    kept = [row["text"].strip() for row in checks if row["passed"]]
    return " ".join(kept) or missing_next_step(packet), {
        "sentences": checks,
        "removed": sum(not r["passed"] for r in checks),
        "all_removed": not bool(kept),
        "parse_error": parse_error,
        "check": "explicit-citations-exact-numbers-and-authored-technique",
    }
