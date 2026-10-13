"""Athlete-facing presentation; evidence and stored measurements stay unchanged."""

import re

ADVICE_FIRST_POLICY = """Reply like a coach giving a useful next step. For a personal
review, lead with what the athlete should TRY or CHANGE in ordinary movement language.
Then explain the relevant observed pattern and how to check the change on the next rep.
Default to 2–4 short sentences and one main focus. Address both topics if two are asked.
For a short follow-up, continue the current rep and cue; do not restart a generic lesson.
Supporting evidence comes AFTER the advice: use at most one useful timestamp by default.
Do not recite angles, elbow values, knee values, ranges, confidence, or raw measurements
unless the athlete explicitly asks for numbers. Never start by listing measurements.
Write ALL times and durations in seconds with exactly one decimal: 10.9 seconds, 0.8 seconds.
Never show milliseconds or many decimal places. Keep measurement precision in the evidence
panel, not the spoken answer. No boilerplate disclaimers, rubric explanations, camera/2D
caveats, or statements about being an AI in the answer; those belong in report details.
Still ground personal advice in the supplied findings: do not invent a fault, an ideal
angle, an unseen event, or a promise of improvement. When no correction is supported,
lead with a qualitative observation or answer the requested explanation. Offer a clearly
optional practice experiment only when useful to the athlete's question and drill goal.
Evidence references and limitations are separate from the conversational answer.
"""

_NUMBER = r"(?<![\w.])(-?\d+(?:\.\d+)?)"
_TIME = re.compile(_NUMBER + r"\s*(milliseconds?|msecs?|ms|seconds?|secs?|s)\b", re.I)
_BOILERPLATE = re.compile(
    r"^(?:note that\b|keep in mind\b|remember that\b|as an ai\b|"
    r"(?:this|these|the)\s+(?:2d|2-d|image-plane|pose|tracking)\s+(?:measurement|measurements|estimate|estimates|value|values)\b|"
    r"(?:this|that) (?:is|does not|doesn't) (?:a basic|a review|a provisional|a confirmed|establish|prove)|"
    r"(?:these|the) (?:are|findings are) (?:2d|2-d|provisional|review flags)|"
    r"(?:automatic|automated) (?:findings|flags|checks) (?:are|do not)|"
    r"(?:no flags|no issues) (?:does not|doesn't)|"
    r"the reviewer role is\b)",
    re.I,
)


def format_timings(text):
    def convert(match):
        value = float(match[1])
        if match[2].lower().startswith(("ms", "millisecond")):
            value /= 1000
        return f"{value:.1f} seconds"

    ranges = re.compile(
        _NUMBER + r"\s*[–—-]\s*(-?\d+(?:\.\d+)?)\s*(milliseconds?|msecs?|ms|seconds?|secs?|s)\b",
        re.I,
    )
    text = ranges.sub(
        lambda m: (
            f"{float(m[1]) / (1000 if m[3].lower().startswith(('ms', 'millisecond')) else 1):.1f}–{float(m[2]) / (1000 if m[3].lower().startswith(('ms', 'millisecond')) else 1):.1f} seconds"
        ),
        text,
    )
    text = re.sub(
        r"(?<![\w.])(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)(?!\d)",
        lambda m: f"{int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3]):.1f} seconds",
        text,
    )
    return _TIME.sub(convert, text)


def format_answer(text):
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", format_timings(text)):
        sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        kept = [s for s in sentences if s and not _BOILERPLATE.search(s)]
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs)


def style_issues(question, reply, personal=False):
    if not personal or re.search(
        r"\b(angle|degrees|numbers?|measurements?|timings?|timestamps?|values?)\b", question, re.I
    ):
        return []
    numbers = re.findall(_NUMBER + r"\s*(?:degrees?|deg\b|°|ratio\b|torso lengths?)", reply, re.I)
    if numbers:
        return [
            "Unrequested angle/ratio numbers belong in evidence details; give qualitative movement feedback in the reply."
        ]
    first = re.split(r"(?<=[.!?])\s+", reply.strip())[0]
    if re.search(
        r"\d+(?:\.\d+)?\s*(?:degrees?|deg\b|°|seconds?|ms\b)", first, re.I
    ) and not re.search(
        r"\b(?:try|keep|focus|aim|reach|push|drive|return|bend|extend|straighten|practice|choose|hold|avoid|reduce|bring|relax)\b",
        first,
        re.I,
    ):
        return ["Lead with the practice cue; supporting numbers belong after the advice."]
    return []
