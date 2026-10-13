"""Resolve clarification intent and keep old assistant errors from becoming advice."""

import re
from difflib import SequenceMatcher


def _normal(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def last_answer(request):
    return next(
        (m.content for m in reversed(request.conversation_history) if m.role == "assistant"), ""
    )


def clarification(request):
    return bool(
        re.search(
            r"\bwhich (?:arm|hand|leg|foot)\b|describe (?:it )?better|explain (?:it |that )?(?:better|again|more|simply)|what (?:do you|does that) mean|be more specific",
            request.question,
            re.I,
        )
    )


def general_instruction(question):
    """A desired technique is not an observation of the athlete's recorded technique."""
    if re.search(r"\brep(?:etition)?\s*\d+\b", question, re.I):
        return False
    if re.search(
        r"\b(?:did i|was my|am i|is my|why did|what(?: is|'s) wrong|what should i (?:change|fix|improve)|analy[sz]e my|review my)\b",
        question,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:should|supposed to|proper|ideal|recommended|generally|usually|in general|how to)\b|\bhow (?:do|can) (?:i|you|we) (?:extend|hold|position|perform|do|recover|advance|retreat|lunge|stand)\b",
            question,
            re.I,
        )
    )


def contextual_question(request):
    """Carry only the immediately active rep into a follow-up, preserving its subject."""
    question = request.question.strip()
    # Resolve an elliptical subject before rep selection, using the latest
    # athlete question rather than trusting an earlier assistant's claims.
    users = [m.content for m in request.conversation_history if m.role == "user"]
    if users and re.search(r"^(?:and|what about|how about)\b", question, re.I):
        from fencecoach.coach.intent import question_topic

        if question_topic(question) is None and not re.search(
            r"\b(?:shoulder|hip|ankle|wrist|shin|head|blade|weapon)\b", question, re.I
        ):
            topic = question_topic(users[-1])
            if topic:
                question = f"Regarding {topic} in this session: {question}"
    followup = bool(
        re.search(
            r"^(?:so\s+)?(?:what should i do|what (?:do i|should i) (?:do|change|fix|work on)|"
            r"what about (?:my|the)|how (?:do|can|should) i (?:fix|improve|change) (?:it|that|this)|"
            r"is (?:it|that|this|the lunge) (?:fast|slow|powerful|explosive|long|far)|"
            r"can you (?:explain|describe) (?:it|that|this))\b",
            question,
            re.I,
        )
    )
    if not followup or re.search(r"\brep(?:etition)?\s*\d+\b", question, re.I):
        return question
    # Never scan older turns for a rep after the athlete changed the scope.
    # Do not inject the preceding body part into an explicit new question.
    previous = users[-1] if users else ""
    if re.search(r"\b(?:all|each|every|whole|entire|overall|drill|session)\b", question, re.I):
        return question
    named = re.search(r"\brep(?:etition)?\s*(\d+)\b", previous, re.I)
    broad_scope = re.search(r"\b(?:all|each|every)\s+(?:\d+\s+)?(?:reps|lunges)\b", previous, re.I)
    if named and not broad_scope:
        return f"Follow-up about rep {named[1]} in this session: {question}"
    return question


def motion_question(question):
    return bool(
        re.search(
            r"\b(?:speed|fast|faster|slow|slower|power|powerful|unpowerful|explosive|unexplosive|explosiveness|distance|disatnce|stride|reach|long|far)\b",
            question,
            re.I,
        )
    )


def history_instruction(question):
    """Recognize cross-session progress requests without treating generic tips as history."""
    return bool(
        re.search(
            r"\b(progress|trend|improved|improvement|improving|getting better|gotten better|doing better|more consistent|less consistent|over time|since (?:my )?(?:last|previous)|last (?:session|practice|time|week|month)|(?:previous|prior|earlier) (?:sessions?|practices?|week|month)|what (?:has )?changed|compare .{0,30}(?:last|previous|earlier|session|practice|week|month)|versus (?:my )?(?:last|previous))\b",
            question,
            re.I,
        )
    )


def general_guidance_query(request):
    topics = r"\b(arm|hand|lunge|recovery|footwork|en garde|advance|retreat|fleche|flèche)\b"
    current = request.question.lower()
    history = " ".join(m.content for m in request.conversation_history[-2:]).lower()
    if not re.search(topics, current) and not (
        clarification(request) and re.search(topics, history)
    ):
        return ""
    context = current + " " + history if clarification(request) else current
    terms = list(dict.fromkeys(re.findall(topics, context)))
    if "arm" in terms or "hand" in terms:
        return "sword weapon arm non-sword rear arm target simple lunge " + current
    if "recovery" in terms:
        return "recovery return lunge en garde starting guard position " + current
    return " ".join(terms) + " " + current


def conversation_issues(request, reply, partial=False):
    issues = []
    previous = _normal(last_answer(request))
    current = _normal(reply)
    if (
        not partial
        and general_instruction(request.question)
        and re.search(r"\b(?:arm|hand)\b", request.question, re.I)
        and re.search(
            r"\b(?:can't|cannot|unable|need a|need your)\b.{0,100}\b(?:video|clip|footage|determine|assess|angle)\b",
            reply,
            re.I,
        )
        and not re.search(r"\b(?:toward|towards|forward|behind|backward)\b", reply, re.I)
    ):
        issues.append("Missing video evidence must not replace a general arm-position explanation.")
    repeat_requested = re.search(
        r"repeat (?:that|it|your answer) (?:exactly|verbatim)|say (?:that|it) again",
        request.question,
        re.I,
    )
    if (
        not repeat_requested
        and len(current.split()) >= 12
        and previous
        and (
            previous.startswith(current) or SequenceMatcher(None, previous, current).ratio() >= 0.88
        )
    ):
        issues.append(
            "The answer repeats the previous reply instead of answering the new question."
        )
    old_sentences = re.split(r"(?<=[.!?])\s+", last_answer(request))
    if not repeat_requested and any(
        len(_normal(sentence).split()) >= 10
        and any(_normal(sentence) == _normal(old) for old in old_sentences)
        for sentence in re.split(r"(?<=[.!?])\s+", reply)
    ):
        issues.append("Copied a full sentence from the preceding answer rather than clarifying it.")
    if re.search(r"\bwhich (?:arm|hand)\b", request.question, re.I) and not re.search(
        r"\b(?:sword|weapon|non[ -]?(?:sword|weapon)|rear) (?:arm|hand)\b", reply, re.I
    ):
        issues.append("Identify the sword or non-sword arm explicitly for this clarification.")
    if re.search(
        r"extend (?:your |the )?(?:(?:sword|weapon) )?arm.{0,20}(?:to the side|sideways)|arm.{0,30}shoulder[ -]width",
        reply,
        re.I,
    ) and not re.search(r"\b(?:not|don't|wrong|incorrect)\b", reply, re.I):
        issues.append(
            "A simple-lunge weapon arm reaches toward the target, not sideways at shoulder width."
        )
    if (
        not partial
        and clarification(request)
        and re.search(r"arm to the side|shoulder[ -]width", last_answer(request), re.I)
        and not re.search(
            r"\b(?:wrong|incorrect|misleading|should have|rather than|not sideways)\b", reply, re.I
        )
    ):
        issues.append("Correct the earlier sideways-arm instruction explicitly.")
    if re.search(
        r"next stroke|after a stroke|integrity of (?:the )?fencing technique", reply, re.I
    ):
        issues.append("Replace generic stroke wording with the actual fencing action and purpose.")
    if (
        not partial
        and re.search(r"what (?:is|does).*recover", request.question, re.I)
        and not (
            re.search(r"\breturn\w*\b", reply, re.I) and re.search(r"en[ -]garde", reply, re.I)
        )
    ):
        issues.append("Define recovery as returning from the lunge to en garde.")
    return issues


def general_guidance_fallback(request, sources):
    """Answer a narrow vocabulary failure from a cited reference; never score a clip."""
    sources = list(sources)
    if re.search(r"\brecovery\b", request.question, re.I) and any(
        s.source == "recovery_basics.md" for s in sources
    ):
        return "Recovery is returning from the lunge to en garde, ready for the next action. In a basic recover-back drill, you release the rear knee and push from the front leg to return to guard."
    if not any(s.source == "lunge_arm_roles.md" for s in sources):
        return None
    context = request.question + " " + last_answer(request)
    if not re.search(r"\b(arm|hand)\b", context, re.I):
        return None
    earlier_wrong = bool(
        re.search(r"arm to the side|shoulder[ -]width apart", last_answer(request), re.I)
    ) and not re.search(r"\b(?:wrong|incorrect)\b", last_answer(request), re.I)
    if re.search(r"\bangles?\b", request.question, re.I):
        reply = (
            "In a basic lunge, reach your sword arm toward the target, while the non-sword arm "
            "extends behind you in the traditional finish. For arm direction, aim at your chosen "
            "target rather than forcing a fixed angle to the floor. Elbow bend is a different "
            "angle from the direction of the whole arm."
        )
    elif re.search(r"\bwhich (?:arm|hand)\b", request.question, re.I):
        reply = "I mean your sword arm—the one holding the weapon. In a simple lunge, reach that arm forward toward the target."
    elif re.search(r"non[ -]?(?:sword|weapon)|rear arm", request.question, re.I):
        reply = "The non-sword arm is your empty hand. In the conventional lunge teaching position, it extends behind you while the weapon arm reaches toward the target."
    else:
        reply = (
            "The sword arm—the arm holding your weapon—reaches forward toward the target in a simple lunge. "
            "The non-sword arm has a separate role: in the conventional teaching position it extends behind you. "
        )
    if earlier_wrong:
        reply = reply.rstrip() + " My earlier instruction to extend the arm sideways was wrong."
    return reply
