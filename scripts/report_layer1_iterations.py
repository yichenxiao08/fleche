"""Summarize prompt iterations and render paired V0/V3 transcripts."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from fencecoach.coach.core_new import (
    EVIDENCE_TOOL_V0,
    EVIDENCE_TOOL_V3,
    LIBRARY_TOOL_V0,
    LIBRARY_TOOL_V3,
    PERSONA_V1,
)

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals/layer1"


def load_rows(directory: Path):
    rows = {}
    for path in sorted(directory.glob("*-*.json")):
        if path.name == "checkpoint.json":
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        rows[(row["id"], row["requested_provider"])] = row
    return rows


def metrics(rows, provider):
    turns = [turn for (_, p), row in rows.items() if p == provider for turn in row["turns"]]
    answers = [turn for turn in turns if turn.get("answer")]
    times = sorted(turn["latency_ms"] / 1000 for turn in turns)
    words = [len(turn["answer"].split()) for turn in answers]
    return {
        "cases": sum(p == provider for _, p in rows),
        "turns": len(turns),
        "answers": len(answers),
        "errors": len(turns) - len(answers),
        "tool_turns": sum(turn.get("contract", {}).get("tool_calls", 0) > 0 for turn in turns),
        "tool_calls": sum(turn.get("contract", {}).get("tool_calls", 0) for turn in turns),
        "median": round(statistics.median(times), 2) if times else None,
        "p95": round(times[math.ceil(len(times) * 0.95) - 1], 2) if times else None,
        "max": round(max(times), 2) if times else None,
        "mean_words": round(statistics.mean(words), 1) if words else None,
    }


def show(value):
    return value if value is not None else "—"


def transcript(case_id, provider, old_rows, new_rows):
    old = old_rows.get((case_id, provider))
    new = new_rows.get((case_id, provider))
    if not new:
        return []
    lines = [
        f"## {case_id} — {provider} — {new['name']}",
        "",
        f"Session `{new['session_id']}`; source: {new['origin']}.",
        "",
    ]
    if case_id == "H01":
        lines += [
            "Exact V3 persona:",
            "",
            "```text",
            new["persona"],
            "```",
            "",
            "Exact V3 standing briefing:",
            "",
            "```text",
            new["briefing"],
            "```",
            "",
            "Exact V3 evidence tool description:",
            "",
            "```text",
            EVIDENCE_TOOL_V3,
            "```",
            "",
            "Exact V3 library tool description:",
            "",
            "```text",
            LIBRARY_TOOL_V3,
            "```",
            "",
        ]
    old_turns = {turn["turn"]: turn for turn in old["turns"]} if old else {}
    for turn in new["turns"]:
        prior = old_turns.get(turn["turn"], {})
        old_answer = prior.get("answer")
        if not old_answer and prior.get("error"):
            old_answer = f"[Provider error: {prior.get('error_type')}] {prior.get('error')}"
        if not old_answer:
            old_answer = "[No matching V0 turn saved]"
        answer = turn.get("answer")
        if not answer:
            answer = f"[Provider error: {turn.get('error_type')}] {turn.get('error')}"
        lines += [
            f"### {case_id}-{provider}-T{turn['turn']} — {turn['model_id']}",
            "",
            f"User (verbatim): **{turn['question']}**",
            "",
            f"V0 answer ({prior.get('latency_ms', 0) / 1000:.2f}s):",
            "",
            f"> {old_answer.replace(chr(10), chr(10) + '> ')}",
            "",
            f"V3 answer ({turn['latency_ms'] / 1000:.2f}s):",
            "",
            f"> {answer.replace(chr(10), chr(10) + '> ')}",
            "",
        ]
    return lines


def main():
    baseline = load_rows(EVAL)
    variants = {name: load_rows(EVAL / "variants" / name) for name in ("V1", "V2", "V3")}
    providers = ("gemini", "local")

    report = [
        "# Layer 1 prompt iterations — review checkpoint",
        "",
        "Layer 2 has not started. `COACH_CORE` still defaults to `old`; these are direct scripted calls to the opt-in Layer 1 core. The same 13 conversation sequences (H01–H10, E11, E12, S11) were replayed per variant and pinned provider, using saved session data and actual preceding model replies. No measurements were invented in the fixtures. Provider errors are retained; evaluations do not fail over or retry.",
        "",
        "The historical inputs and original failures are preserved at `evals/layer1/historical_inputs.json` and in `docs/layer1_transcripts.md`. The source-selection caveat remains: the Step 0 report found 10 failure episodes from four identifiable saved chat streams, not 10 independent chats.",
        "",
        "## User review correction: H01-local T1–T3",
        "",
        "V3 regresses conversational relevance in all three turns raised by the user. V0 discusses the requested knees, back and speed; V3 repeatedly redirects to arm extension and asks the same generic question. V0 is better at engaging with the requested subject, but its 140/160-degree knees, 10-degree torso lean and 13.44–15.44-second interval are unsupported by the replay's saved evidence: that session has zero detected reps, no saved measurements and an explicit unsupported-tracking warning. V0 also misinterprets the larger included knee angle as more bend. Those replies are not acceptable accurate coaching.",
        "",
        "V3 correctly avoids those invented values, but incorrectly turns unavailable tracking into claims that the footage does not capture the athlete's back or legs. Its repeated arm redirection is an independent group B failure, not an improvement and not something to defer to explicit state. The desired response should stay on the requested subject, distinguish unavailable measurements from unseen footage, and use relevant retrieved general coaching when personal assessment is unavailable. These three pairs show neither version passes both usefulness and accuracy. Completion rate and shorter latency must not be presented as evidence of better coaching quality; no overall V3 quality win was established.",
        "",
        "## A) Shortcomings conversation state can address",
        "",
        "These are topic, rep, or clarification carry-over problems. They are recorded for a future Layer 2 decision; no explicit state object or state machine was added in this checkpoint.",
        "",
        "| Turn reference | Shortcoming | Best-cause guess |",
        "|---|---|---|",
        "| H10-gemini T3–T4 | Arm-extension follow-up shifts into a front-knee interpretation. | History handling: the antecedent is not represented explicitly, so the model latches onto another prominent session metric. |",
        "| H06-local T3 | “Last rep” is treated as rep 2 in a five-rep clip. | History handling: ordinal resolution has no deterministic link to detected rep count. |",
        "| H07-local T3 | Session-level arm question becomes another rep-1 answer. | History handling and briefing: the current scope (“across the session”) is not carried as an explicit target. |",
        "| H08-gemini T3; H08-local T3 | “Was it good?” after rear-leg discussion changes to front-knee or generic advice. | History handling: the model does not bind the short evaluative follow-up to the last metric. |",
        "| H05-local T3 | “So what should I do?” loses the measured rep/hold and returns generic advice. | History handling: actionable advice request does not inherit the active rep/phase. |",
        "| E11-local T5, T7 | Recovery question and later “anything else?” cite or request the wrong rep. | History handling: rep reference is not grounded in explicit conversation state. |",
        "| H04-local T1; H04-gemini T2–T3 | Fleche follow-ups do not consistently retain the action across the chain. | History handling: action topic is implicit in prose and competes with generic lunge advice. |",
        "| H09-gemini T5–T6 | “Straighter or bent?” follows rear-leg discussion; one reply is generic and the next errors. | History handling for the generic reply; provider error for the failed turn (the latter is not state-fixable). |",
        "| V1-gemini H06 T2–T3; V2-gemini E11 T3–T5; V3-gemini E11 T3–T5 | Some variants correctly retain “last rep”, second rep, and recovery through follow-ups. These are controls showing carry-over can work without explicit state in some turns. | No defect in those turns; reliability remains inconsistent and should be evaluated against the failures above. |",
        "",
        "## B) Shortcomings not solved by adding conversation state",
        "",
        "| Turn reference | Shortcoming | Best-cause guess |",
        "|---|---|---|",
        "| H03-gemini T1–T2 | Near-duplicate general answer; does not progress the conversation. | Persona prompt: no strong answer-first/non-repetition direction in V0; model also defaults to generic text. |",
        "| H07-gemini T5; H08-gemini T3; H08-local T1/T3; H10-local T3 | Claims there is no relevant evidence although saved features exist, or asks for data the tools can read. | Briefing and tool descriptions: athlete wording is not mapped to exact feature names; Qwen additionally ignores the tool affordance. |",
        "| E11-local T3–T7 | Announces retrieval or asks permission instead of retrieving and replying. | Persona prompt and tool descriptions: optionality is underspecified; weaker provider tool-use behavior. |",
        "| H10-local T2/T4; E11-local T2/T6–T7 | Repeats measurements and generic closers / lengthy report-like replies. | Persona prompt: no explicit ban on repeated evidence and unnecessary offers; local model limitation. |",
        "| H04-local T1; H07-local T2/T3 | Long answer trails off near the generation cap. | Persona prompt lacks a short response budget; local model generation behavior. |",
        "| H01-local T1; H09-local T2/T3; H10-local T2/T4; E11-gemini T2; E12-gemini T1; S11-gemini T2/T4/T5; S11-local T6/T7 | Invented measurements, universal ranges, unsupported causal/coaching claims, or treating a reach sample as timing / corrected reference text as athlete evidence. | Briefing and prompt: source boundaries and “reference is not a universal target” are too easy to ignore; provider limitation. |",
        "| H06-gemini T2; E11-gemini T1/T3/T6; plus recorded Gemini errors in V1/V2/V3 | HTTP 503/rate-limit/provider failures prevent answers. | Provider availability; no persona, briefing, tool description, or state change can fix this. |",
        "| E12-gemini T2–T5 (V0) | These item-specific missing-data answers were correct controls: blade, m/s, force, and absent drill are not in the session/library. | No defect. Keep these distinctions; the reply should still share known clip evidence. |",
        "| V1-gemini H05 T1–T3; V1-local H09 T5–T6; V1-local E12 T2 | Added fabricated “best/typical” values, a generic 135–145° target, or blade stability from an unrelated angle. | V1 persona: answer-first instruction increased directness without sufficiently distinguishing saved facts from unsupported norm/causality; Qwen limitation. |",
        "| V2-local H05 T1–T3; H06 T2–T3; H08 T1–T3; E12 T1–T2; V2-gemini H07 T3–T5 | Mislabels reference ranges as acceptable, confuses metrics, or overstates quality despite the expanded briefing. | Briefing: more evidence helps Gemini answer, but the expanded list increases Qwen's confusion; model limitations remain. |",
        "| V3-local H07 T4–T5; H08 T1–T3; H09 T4–T6; E12 T2–T4; E11/S11 T1–T7 | Reports torso tilt as 0 across reps, swaps front/rear knee values, claims blade stability from an arm ratio, conflates speed and force, or repeatedly asks for already-saved measurements. | Tool-use/model limitation: better descriptions do not ensure Qwen calls tools or interprets the returned evidence correctly. |",
        "| V3-local E12 T2–T3 | Two local responses took 182.83s and 203.21s; the first timed out, the next still took over three minutes. | Provider/runtime latency, not conversation state. This is unacceptable for live use. |",
        "",
        "## What the three variants changed",
        "",
        "- **V1 — persona only.** Kept the V0 briefing and tool descriptions, rewrote the voice to answer first, be brief, avoid tool narration, and handle unavailable facts item by item. Gemini continuity improved in places (H06 and H07), but fabricated judgments/ranges increased in H05/H09; Qwen still requested data or repeated itself. It did not meet the conversational or grounding goal.",
        "- **V2 — persona plus briefing.** Added common athlete-wording aliases, rep/phase labels, explicit measured-versus-interpretation language, and a note that references are not universal targets. Gemini used rep-specific evidence better in H07/H10 and E11. Qwen continued treating reference values as acceptable ranges, mixed features/reps, and made unsupported stability and quality claims (E12, H08, H06). Briefing was not sufficient on its own.",
        "- **V3 — persona, briefing, and tool descriptions.** Tool descriptions now say when to call each tool, how to inspect all evidence, preserve rep/phase, and distinguish library teaching material from athlete facts. Gemini handled E12 bait cleanly (T1–T5) and used recovery values; this is the best measured result. Qwen repeatedly failed to use tools, confused evidence, fabricated stability/typical ranges, and incurred 182.83s / 203.21s turns. Gemini also had intermittent provider errors in H08–H10. V3 is not reliable across both providers.",
        "",
        "Exact V1/V2/V3 persona text (same across those iterations):",
        "",
        "```text",
        PERSONA_V1,
        "```",
        "",
        f"V1 uses the original V0 standing briefing and tool descriptions: evidence — `{EVIDENCE_TOOL_V0}`; library — `{LIBRARY_TOOL_V0}`. V2 uses the persona above and the revised per-session briefing stored verbatim in each V2 trace JSON, with V0 tool descriptions. V3 uses the V2 briefing and the two exact V3 tool descriptions shown in the paired transcript at H01. V0's exact persona and briefing are retained in `docs/layer1_transcripts.md`.",
        "",
        "## Paired quantitative comparison",
        "",
        "The table compares identical 13-case sequences (56 turns per provider). `Answered` counts turns with a returned answer; provider failures are separate. Tool rate is turns with at least one call. Latencies include failures and measure full completion, not time to first token. Word count is descriptive only, not a tone score.",
        "",
        "| Variant | Provider | Cases | Answered / turns | Errors | Tool turns | Tool calls | Median s | p95 s | Max s | Mean answer words |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant_name, data in (
        ("V0", baseline),
        *((name, rows) for name, rows in variants.items()),
    ):
        for provider in providers:
            m = metrics(data, provider)
            report.append(
                f"| {variant_name} | {provider} | {m['cases']} | {m['answers']} / {m['turns']} | {m['errors']} | {m['tool_turns']} | {m['tool_calls']} | {show(m['median'])} | {show(m['p95'])} | {show(m['max'])} | {show(m['mean_words'])} |"
            )
    report += [
        "",
        "Measured V0→V3 effects: Gemini answered 45/56→47/56 (+3.6 percentage points), with 11→9 provider errors; median completion fell 5.44s→1.56s and tool use rose 30/56→40/56 turns. Qwen answered 56/56→55/56, with one timeout; median rose 6.47s→8.41s, p95 20.49s→160.75s, and tool use fell 6/56→3/56 turns. Mean Qwen answer length fell from 114.2 to 72.6 words, but remained long and did not fix relevance or grounding. Gemini's V3 errors included intermittent provider failures; its p95 was 11.70s.",
        "On the five E12 fabrication-bait questions per provider, manual review found 0/5 unsupported claims in V3 Gemini replies; it declined to assert blade tracking, calibrated m/s, force, or the absent named drill while sharing clip evidence. V3 Qwen produced one unsupported blade-stability claim (T3), one provider timeout (T2), and conflated force with speed at T4. These are manual classifications, not a deterministic fabrication metric. This is better than Qwen V0's unsupported blade/arm, speed and force inferences, but V3 still misses the zero-fabrication goal across providers.",
        "",
        "## Decision",
        "",
        "Group B remains unresolved after three prompt/briefing/tool variants. V3 has some better Gemini bait replies, but regresses relevance on H01-local and has not established an overall quality win. Its prompt is saved in the evaluation rows and paired transcript file; it is currently the internal default only when the opt-in new core is selected. The app-wide setting remains `COACH_CORE=old`. Do not start Layer 2 until the user approves this checkpoint. No commit or push was made.",
        "",
        "Full V1/V2/V3 provider traces, including exact per-turn prompts, tool calls, results, errors and latency, are in `evals/layer1/variants/`. Full V0 baseline answers remain in `docs/layer1_transcripts.md`.",
    ]
    (ROOT / "docs/layer1_iteration_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    transcript_lines = [
        "# Paired Layer 1 transcripts — V0 baseline vs V3",
        "",
        "Every transcript below replays the same saved request and user turns against V0 and V3 on the same pinned provider. It includes the full answers, including errors, verbosity, and awkward replies. V1/V2 complete transcripts are available in their raw per-turn trace JSON under `evals/layer1/variants/`; this paired file focuses on the V0-to-V3 change after the final prompt/tool iteration.",
        "",
    ]
    for case_id in (f"H{i:02d}" for i in range(1, 11)):
        for provider in providers:
            transcript_lines.extend(transcript(case_id, provider, baseline, variants["V3"]))
    for case_id in ("E11", "E12", "S11"):
        for provider in providers:
            transcript_lines.extend(transcript(case_id, provider, baseline, variants["V3"]))
    (ROOT / "docs/layer1_iteration_transcripts.md").write_text(
        "\n".join(transcript_lines) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: {provider: metrics(rows, provider) for provider in providers}
                for name, rows in (("V0", baseline), *variants.items())
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
