"""Evaluation-only numeric presence tracing. Never gates or rewrites replies.

Presence is necessary, not sufficient: a matching value can still be assigned
to the wrong feature, rep or unit. Those semantic failures need manual review.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

WORDS = {
    word: i
    for i, word in enumerate(
        (
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
        )
    )
}
WORDS.update(
    dict(
        zip(
            ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"),
            range(20, 100, 10),
            strict=True,
        )
    )
)
ORDINALS = {
    word: i
    for i, word in enumerate(
        (
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
        ),
        1,
    )
}


def mentions(text):
    text = re.sub(r"https?://\S+", "", text)
    result = []
    for match in re.finditer(
        r"(?<![\w.])([-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?:st|nd|rd|th)?(?!\w|\.\d)", text
    ):
        result.append(
            {"token": match[0], "value": match[1].replace(",", ""), "offset": match.start()}
        )
    word = "(?:" + "|".join(WORDS) + "|hundred|thousand)"
    for match in re.finditer(r"\b" + word + r"(?:[ -]+(?:and[ -]+)?" + word + r")*\b", text, re.I):
        # 'The one holding the sword' is a pronoun, not a numerical claim.
        if match[0].lower() == "one" and (
            re.search(r"\bthe\s+$", text[: match.start()], re.I)
            or re.match(r"\s+(?:holding|who|that)\b", text[match.end() :], re.I)
        ):
            continue
        subtotal = total = 0
        for token in re.findall(r"[a-z]+", match[0].lower()):
            if token == "hundred":
                subtotal = max(1, subtotal) * 100
            elif token == "thousand":
                total += max(1, subtotal) * 1000
                subtotal = 0
            else:
                subtotal += WORDS.get(token, 0)
        result.append({"token": match[0], "value": str(total + subtotal), "offset": match.start()})
    for match in re.finditer(r"\b(" + "|".join(ORDINALS) + r")\s+(?:rep|lunge|one)\b", text, re.I):
        result.append(
            {"token": match[1], "value": str(ORDINALS[match[1].lower()]), "offset": match.start()}
        )
    return sorted(result, key=lambda m: m["offset"])


def _pool(value, path="packet"):
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [(str(value), path)]
    if isinstance(value, str):
        return [(m["value"], path) for m in mentions(value)]
    if isinstance(value, list):
        return [pair for i, row in enumerate(value) for pair in _pool(row, f"{path}[{i}]")]
    if isinstance(value, dict):
        ignored = {
            "source_id",
            "evidence_id",
            "session_id",
            "name",
            "feature",
            "core_version",
            "last_cited_evidence",
            "conversation_memory",
            "resolution",
            "scope_text",
            "feature_meanings",
            "definition",
            "does_not_indicate",
            "evidence_reused",
            "metric_id",
            "job_id",
            "model_id",
        }
        return [
            pair
            for key, row in value.items()
            if key not in ignored
            for pair in _pool(row, f"{path}.{key}")
        ]
    return []


def trace_numbers(answer, packet):
    pool = _pool(packet)
    result = []
    for mention in mentions(answer):
        wanted = Decimal(mention["value"])
        precision = max(0, -wanted.as_tuple().exponent)
        exact, rounded = [], []
        for supplied, path in pool:
            candidate = Decimal(supplied)
            if wanted == candidate:
                exact.append({"value": supplied, "path": path, "match": "exact"})
            elif (
                candidate.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP) == wanted
            ):
                rounded.append({"value": supplied, "path": path, "match": "rounded"})
        # Rounding integers below one to zero is misleading rather than a useful citation.
        matched = exact or ([m for m in rounded if abs(wanted) >= 1 or precision > 0])
        result.append({**mention, "supported": bool(matched), "packet_matches": matched[:5]})
    return {
        "mentions": result,
        "unsupported": [m for m in result if not m["supported"]],
        "passed": all(m["supported"] for m in result),
        "exact_only_passed": all(
            any(p["match"] == "exact" for p in m["packet_matches"]) for m in result
        ),
        "check": "numeric-presence-only; no response blocking",
    }
