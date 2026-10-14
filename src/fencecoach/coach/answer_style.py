"""Athlete-facing presentation; evidence and stored measurements stay unchanged."""

import re

ADVICE_FIRST_POLICY = """Answer the latest question directly, like a conversational coach.
For a personal analysis, lead with the relevant qualitative assessment or supported change
in ordinary movement language. Explain what matched or differed from the references.
Give a practice cue when a change is supported and useful; do not prescribe one on every turn.
When the athlete asks for a direct verdict (for example, whether reps were good or bad),
answer that first against the requested reference feature, then give a cue if needed.
Default to 2–4 short sentences and one main focus. Address both topics if two are asked.
For a short follow-up, continue the current subject, phase and rep; do not restart a generic lesson.
For analysis or a question about how a movement was, give the assessment or useful cue first,
then ONE concrete supporting example: a named rep with its relevant observed difference, or
a measured statistic compared with the same feature in the reference. A representative example
supports the pattern; it does not establish that every rep had that difference.
Choose one representative rep, usually the clearest difference, instead of listing both ends
of the set. Expand examples only when the request explicitly asks to compare or break down reps.
Make that example support the main assessment: if you discuss a deviation, illustrate the
deviating rep rather than an earlier rep that matched. The packet's representative_support is
an available evidence record, not a generated verdict; use it when it supports your observation.
When explicitly asked for numbers, statistics or quantifiable evidence, provide an actual
measured value with units and explain what it supports. One useful example is enough unless
the athlete asks for every rep or a full table. A qualitative restatement does not answer this.
Avoid a dump of angles, timings or confidence values. Supporting evidence follows the answer;
use at most one useful timestamp by default. Requests to analyze all reps still cover each rep.
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
_NUMERIC_REQUEST = re.compile(
    r"\b(?:numbers?|numerical|numeric|quantif(?:iable|ied|y|ication)|stats?|statistics?|"
    r"values?|measurements?|angles?|degrees?|timings?|timestamps?|percentages?)\b|"
    r"\bhow (?:much|many)\b",
    re.I,
)
_STATISTIC = re.compile(
    _NUMBER + r"\s*(?:degrees?|deg\b|°|milliseconds?|ms\b|seconds?|secs?\b|s\b|"
    r"%|percent\b|inches|inch\b|feet\b|foot\b|cm\b|meters?|metres?|"
    r"leg lengths?|torso lengths?|ratio\b|reps?\b|lunges?\b|recoveries\b)|"
    r"\b\d+\s+(?:of|out of)\s+\d+\b",
    re.I,
)


def requests_numbers(question):
    """One definition of numerical evidence requests for context, prompts and validation."""
    return bool(_NUMERIC_REQUEST.search(question))


def response_evidence_issues(question, reply, available=False):
    """Require a concrete example without turning a concise answer into a data dump."""
    if not available:
        return []
    if requests_numbers(question):
        if not _STATISTIC.search(reply):
            return [
                "The athlete requested numerical evidence; give a measured value with its units or a supported count comparison, not just a qualitative restatement."
            ]
        return []
    assessment = re.search(
        r"\banaly[sz]e\b|\bassess\b|\breview\b|\bhow (?:was|were|did)\b|"
        r"\bwhat (?:needs|should i|can i)\b.{0,35}\b(?:work|improve|fix|change)\b",
        question,
        re.I,
    )
    if assessment and not (
        re.search(r"\brep(?:s|etition(?:s)?)?\s*#?\s*\d+\b", reply, re.I)
        or _STATISTIC.search(reply)
    ):
        return [
            "Support this analysis with one relevant named rep and observed difference, or one measured statistic, after the assessment or cue."
        ]
    return []


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
    if not personal or requests_numbers(question):
        return []
    from fencecoach.coach.intent import wants_all_reps, wants_rep_comparison

    if (
        wants_all_reps(question)
        or wants_rep_comparison(question)
        or re.search(r"\b(?:compare|comparison|versus)\b", question, re.I)
    ):
        return []
    evidence_sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", reply.strip())
        if re.search(_NUMBER + r"\s*(?:degrees?|deg\b|°|ratio\b|torso lengths?)", sentence, re.I)
    ]
    statistics = re.findall(
        _NUMBER + r"\s*(?:degrees?|deg\b|°|ratio\b|torso lengths?)", reply, re.I
    )
    example_reps = {
        number
        for sentence in evidence_sentences
        for number in re.findall(r"\brep(?:s|etition(?:s)?)?\s*#?\s*(\d+)\b", sentence, re.I)
    }
    if len(example_reps) > 1 or len(evidence_sentences) > 2 or len(statistics) > 3:
        return [
            "Keep default analysis concise: one supporting statistical example is enough; put the full measurement list in evidence details."
        ]
    return []
