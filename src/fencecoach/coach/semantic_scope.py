"""One bounded semantic scope lookup shared by every answer provider.

Only unresolved scope goes here. This has no access to athlete measurements and
cannot supply an answer. Offline/unavailable lookup leaves concrete clarification.
"""

import json
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage

from fencecoach.coach.hosted_fallback import HostedFallback
from fencecoach.coach.turn_packet import FEATURES
from fencecoach.settings import settings


@lru_cache(maxsize=64)
def _lookup(question, previous_topic):
    messages = [
        SystemMessage(
            content="Resolve the subject of a fencing conversation, not the answer. Return JSON {topics: [ontology keys], phases: [phase keys], confidence: high|low}. Leave topics empty when genuinely ambiguous. Ontology: arm (weapon elbow/hand), rear_leg, front_leg, torso (trunk/back), speed (timing), recovery (return to guard), distance, overview, blade, force, fleche. Phases: starting_guard,lunge_drive,lunge_finish,lunge_hold,active_recovery,returned_guard. Do not choose between alternatives the user offered. No measurements or technique advice."
        ),
        HumanMessage(content=json.dumps(dict(question=question, previous_topic=previous_topic))),
    ]
    try:
        return json.loads(HostedFallback().invoke(messages).content)
    except Exception as exc:
        return {"error_type": type(exc).__name__}


def resolve_semantic_scope(request, state):
    if state.resolution_confidence != "low" or " or " in request.question.lower():
        return state, None
    if not settings.groq_api_key.get_secret_value():
        return state, {"status": "offline_clarification"}
    result = _lookup(request.question, state.current_topic)
    allowed = set(FEATURES) | {"blade", "force", "fleche"}
    topics = result.get("topics", [])
    phases = result.get("phases", [])
    allowed_phases = {
        "starting_guard",
        "lunge_drive",
        "lunge_finish",
        "lunge_hold",
        "active_recovery",
        "returned_guard",
    }
    if (
        result.get("confidence") == "high"
        and topics
        and set(topics) <= allowed
        and set(phases) <= allowed_phases
    ):
        state = state.model_copy(deep=True)
        state.topics, state.phases = topics, phases
        state.current_topic = ", ".join(topics)
        state.open_clarifying_question = None
        state.resolution_confidence = "moderate"
        state.assumption_note = "Assuming you mean " + state.current_topic.replace("_", " ") + "."
        return state, {"status": "resolved", **result}
    return state, {"status": "clarification_preserved", **result}
