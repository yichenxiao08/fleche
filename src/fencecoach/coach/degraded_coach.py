"""Offline packet templates: no local-model inference or invented interpretation."""

import json
import re

from langchain_core.messages import AIMessage

from fencecoach.coach.claim_check import sentences


class DegradedCoach:
    experimental = True

    def invoke(self, messages):
        packet = json.loads(messages[0].content.split("TURN PACKET:\n", 1)[1])
        rows = []

        def add(text, kind="claim", ids=(), library=(), **extra):
            rows.append(
                dict(
                    type=kind, text=text, evidence_ids=list(ids), library_ids=list(library), **extra
                )
            )

        kind = packet.get("turn_type")
        if kind in {"greeting", "acknowledgment", "restart"}:
            text = {
                "greeting": "Hi—let’s look at your session.",
                "acknowledgment": "Got it.",
                "restart": "Let’s start fresh.",
            }[kind]
            add(text, "reset" if kind == "restart" else "acknowledgment")
        elif packet.get("clarification"):
            q = packet["clarification"]
            add(
                q["question"].rstrip("?")
                + ": "
                + " or ".join(o["label"] for o in q["options"])
                + "?",
                "clarification",
            )
        else:
            table = packet["measurements"]
            measures = [dict(zip(table["columns"], r, strict=True)) for r in table["rows"]]
            if measures:
                row = measures[0]
                meaning = packet["measurement_definitions"][row["feature"]]["definition"]
                if (
                    packet["requested_operation"].startswith("explain")
                    or packet["conversation_memory"]["already_given"]
                ):
                    add(meaning, ids=[row["evidence_id"]])
                else:
                    add(
                        f"Your {row['feature'].replace('_', ' ')} measured {row['display']} in rep {row['rep']}.",
                        ids=[row["evidence_id"]],
                    )
                relative = [
                    r
                    for a in packet["assessments"]
                    for r in a.get("relative", [])
                    if r["feature"] == row["feature"]
                ]
                if relative and packet["requested_operation"].startswith("assess"):
                    r = relative[0]
                    add(
                        f"Across the measured reps, the spread was {r['spread']}; that compares {r['relative_axis']}, rather than overall technique.",
                        ids=[r["evidence_id"]],
                    )
                    add(
                        "The library gives a cue, not an approved pass/fail number.",
                        ids=["packet:policy"],
                    )
            elif packet.get("general_guidance"):
                guide = packet["general_guidance"][0]
                text = re.sub(r"(?m)^#.*$", "", guide["text"]).strip()
                cue = sentences(text)[0]
                add(
                    "As general guidance: " + cue,
                    library=[guide["source_id"]],
                    claim_kind="technique",
                    cue=cue,
                    library_quotes=[dict(source_id=guide["source_id"], quote=cue)],
                )
            else:
                add(
                    "There is no measurement or retrieved cue for this requested subject; we can review a saved rep together.",
                    ids=["packet:availability"],
                )
        return AIMessage(
            content=json.dumps({"sentences": rows}),
            response_metadata={"degraded": True, "experimental": True, "model_inference": False},
        )
