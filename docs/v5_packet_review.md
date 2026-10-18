## Owner correction: invalid inputs, not quality evidence

The owner has excluded Gemini C01-T4 and C03-T4 from quality evaluation. They were generated after three unanswered user turns were incorrectly sent as history. Keep their raw outputs as diagnostic records, but do not use them to judge coaching quality or claim a packet/prompt quality improvement.

The product now sends only completed user/assistant pairs. Unanswered messages stay in the saved trace under stored_conversation_history and are omitted from model history. The runner stops on the first outage and resumes the same unanswered turn later; it never runs a later turn without all earlier stored assistant replies. A failed attempt no longer counts toward completion.

[Input-only C01-T4 regression proof](../evals/conversational_kb/model_review/fewshot-v5-history-clean/C01-T4-history_regression_INPUT_ONLY.json): three unanswered questions are retained in the record, writer_history is empty, and the sole HumanMessage sent is “and my recovery?”. This is an input/ordering test, not a generated quality result.

Tests in tests/test_conversational_writer.py and tests/test_v5_history_runner.py cover that exact case, preservation of answered pairs, omission of blank answers, atomic history budgeting, rejection of an orphaned saved T4, and stopping before T2 after a mocked 503 or 429 on either provider. All 38 focused tests passed. Persona, reminder, v5 packet fields, resolver and authored KB are unchanged.

---

> **Invalid evaluation inputs:** Gemini C01-T4 and C03-T4 were generated with three unanswered earlier user questions in history after 503 outages. Exclude both rows from quality evidence. Raw questions/replies and ratings are preserved; this is an input-validity annotation, not a rating.

# v5 review of the exact v4 inputs

The two v4 packets did not declare missing arm or torso data. Both had requested_statement=null, requested_scope=available, and available_session_topics explicitly including arm extension/direction and torso. Their only session_missing_topics entry was distance. The false statements were introduced by the model despite these positive availability facts. Omission of previous-topic values from the scoped packet plus unanswered earlier questions may have contributed; that causal explanation is an inference, not a proven model mechanism.

For both calls, turns1–3 had503outages, so the history contained three user questions and no assistant replies. The exact original requests, responses and errors remain archived. The system prompt is the unchanged [v4 full-KB prompt](../evals/conversational_kb/model_review/fewshot-v4-frozen-pass/gemini/writer_prompt.txt). Below are the exact writer packet and user-history messages sent; request links include every system/reminder/history message.

## C01-T4

Athlete: and my recovery?

[Exact original request/response](../evals/conversational_kb/model_review/fewshot-v5/v4_input_inspection/C01-T4-1.json)

Original raw coach reply:

I do not have your arm extension readings loaded in this turn to judge your arm or tell you what to change on it, though as general guidance many coaches teach extending the arm fully toward the target without locking the elbow before the feet launch. For your recovery, total time from finish to guard ranged from about 0.3 to 0.6 seconds across your reps. The coaching reference does not set a numerical time standard for recovery, and because these readings do not track whether your arm retracted after your body moved, duration alone cannot show if the recovery was good.

Exact v4 writer packet:

```json
{
  "session_overview": "This session has 8 recorded reps; usable measurements cover arm extension/direction, front knee, rear knee, torso, lunge timing/hip speed, recovery.",
  "overview_then_clarify": false,
  "availability": {
    "status": "measurements_available",
    "requested_statement": null,
    "available_session_topics": [
      "arm extension/direction",
      "front knee",
      "rear knee",
      "torso",
      "lunge timing/hip speed",
      "recovery"
    ],
    "gap_scope_note": "",
    "session_missing_topics": [
      "distance"
    ],
    "cause": "unknown",
    "verified_visibility_observations": [],
    "requested_scope": "available",
    "tracking_warning": ""
  },
  "scope": {
    "topics": [
      "recovery"
    ],
    "phases": [
      "active_recovery"
    ],
    "rep_numbers": [],
    "available_reps": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8
    ],
    "movement": ""
  },
  "capture": {
    "weapon": "epee",
    "weapon_arm": "right",
    "front_leg": "right",
    "facing": "left",
    "camera_view": "side"
  },
  "measurements": [
    {
      "feature": "estimated_active_recovery_time",
      "phase": null,
      "rep_readings": {
        "1": "0.066 seconds",
        "2": "0.100 seconds",
        "3": "0.167 seconds",
        "4": "0.167 seconds",
        "5": "0.067 seconds",
        "6": "0.167 seconds",
        "7": "0.166 seconds",
        "8": "0.066 seconds"
      }
    },
    {
      "feature": "finish_to_guard_time",
      "phase": null,
      "rep_readings": {
        "1": "0.500 seconds",
        "2": "0.500 seconds",
        "3": "0.267 seconds",
        "4": "0.500 seconds",
        "5": "0.567 seconds",
        "6": "0.500 seconds",
        "7": "0.433 seconds",
        "8": "0.500 seconds"
      }
    }
  ],
  "session_comparison": [
    {
      "feature": "estimated_active_recovery_time",
      "phase": null,
      "unit": "seconds",
      "range": [
        "0.066 seconds",
        "0.167 seconds"
      ]
    },
    {
      "feature": "finish_to_guard_time",
      "phase": null,
      "unit": "seconds",
      "range": [
        "0.267 seconds",
        "0.567 seconds"
      ]
    }
  ],
  "clarification": null,
  "resolution": {
    "confidence": "high",
    "assumption": ""
  },
  "turn_type": "coaching",
  "already_said": [],
  "measurement_meanings": {
    "estimated_active_recovery_time": "Elapsed interval from estimated backward hip-motion onset to guard-return bookmark; preceding hold excluded.",
    "finish_to_guard_time": "Elapsed lunge-finish to guard-return interval, including any hold."
  },
  "memory_note": "History and already_said are conversation, never measurement evidence."
}
```

Exact messages after the system/reference, packet and reminder (the last one is the current question):

```json
[
  {
    "role": "human",
    "content": "how's my arm extension?"
  },
  {
    "role": "human",
    "content": "is it good?"
  },
  {
    "role": "human",
    "content": "what should I change?"
  },
  {
    "role": "human",
    "content": "and my recovery?"
  }
]
```

v5 input-only inspection (no generation): same scope, measurements and ranges; current_question is explicit. Availability now contains only requested_missing_topics and never a list of other missing topics. Persona/reminder unchanged.

```json
{
  "status": "measurements_available",
  "requested_statement": null,
  "available_session_topics": [
    "arm extension/direction",
    "front knee",
    "rear knee",
    "torso",
    "lunge timing/hip speed",
    "recovery"
  ],
  "gap_scope_note": "Answer current_question and its resolved topics only. Earlier questions are history, not additional pending requests. Measurements omitted for another topic are filtered out, not missing. State a data gap only for requested_missing_topics; never imply a gap for an unrequested or previous topic.",
  "requested_missing_topics": [],
  "cause": null,
  "verified_visibility_observations": [],
  "requested_scope": "available",
  "tracking_warning": ""
}
```

## C03-T4

Athlete: and my rear leg?

[Exact original request/response](../evals/conversational_kb/model_review/fewshot-v5/v4_input_inspection/C03-T4-1.json)

Original raw coach reply:

There are no usable torso measurements in this turn's data, so I cannot judge your posture or tell you whether it needs changing. As general guidance, many coaches teach keeping the torso upright or only slightly tilted forward rather than leaning heavily. 

For your rear leg at the finish, every measured rep is consistent with the straight-leg cue, ranging from about 175 to 178 degrees. That part of your finish is solid, though this side view cannot show how your rear foot pressed into the floor or whether it rolled.

Exact v4 writer packet:

```json
{
  "session_overview": "This session has 8 recorded reps; usable measurements cover arm extension/direction, front knee, rear knee, torso, lunge timing/hip speed, recovery.",
  "overview_then_clarify": false,
  "availability": {
    "status": "measurements_available",
    "requested_statement": null,
    "available_session_topics": [
      "arm extension/direction",
      "front knee",
      "rear knee",
      "torso",
      "lunge timing/hip speed",
      "recovery"
    ],
    "gap_scope_note": "",
    "session_missing_topics": [
      "distance"
    ],
    "cause": "unknown",
    "verified_visibility_observations": [],
    "requested_scope": "available",
    "tracking_warning": ""
  },
  "scope": {
    "topics": [
      "rear_leg"
    ],
    "phases": [
      "lunge_finish"
    ],
    "rep_numbers": [],
    "available_reps": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8
    ],
    "movement": ""
  },
  "capture": {
    "weapon": "epee",
    "weapon_arm": "right",
    "front_leg": "right",
    "facing": "left",
    "camera_view": "side"
  },
  "measurements": [
    {
      "feature": "rear_knee_angle",
      "phase": "lunge_finish",
      "rep_readings": {
        "1": "177.6 deg",
        "2": "176.1 deg",
        "3": "177.1 deg",
        "4": "175.5 deg",
        "5": "176.8 deg",
        "7": "174.9 deg",
        "8": "177.2 deg"
      }
    }
  ],
  "session_comparison": [
    {
      "feature": "rear_knee_angle",
      "phase": "lunge_finish",
      "unit": "deg",
      "range": [
        "174.9 deg",
        "177.6 deg"
      ]
    }
  ],
  "clarification": null,
  "resolution": {
    "confidence": "high",
    "assumption": ""
  },
  "turn_type": "coaching",
  "already_said": [],
  "measurement_meanings": {
    "rear_knee_angle": "Included image-plane rear-knee angle; larger is straighter."
  },
  "memory_note": "History and already_said are conversation, never measurement evidence."
}
```

Exact messages after the system/reference, packet and reminder (the last one is the current question):

```json
[
  {
    "role": "human",
    "content": "how was my torso?"
  },
  {
    "role": "human",
    "content": "is it good?"
  },
  {
    "role": "human",
    "content": "what should I change?"
  },
  {
    "role": "human",
    "content": "and my rear leg?"
  }
]
```

v5 input-only inspection (no generation): same scope, measurements and ranges; current_question is explicit. Availability now contains only requested_missing_topics and never a list of other missing topics. Persona/reminder unchanged.

```json
{
  "status": "measurements_available",
  "requested_statement": null,
  "available_session_topics": [
    "arm extension/direction",
    "front knee",
    "rear knee",
    "torso",
    "lunge timing/hip speed",
    "recovery"
  ],
  "gap_scope_note": "Answer current_question and its resolved topics only. Earlier questions are history, not additional pending requests. Measurements omitted for another topic are filtered out, not missing. State a data gap only for requested_missing_topics; never imply a gap for an unrequested or previous topic.",
  "requested_missing_topics": [],
  "cause": null,
  "verified_visibility_observations": [],
  "requested_scope": "available",
  "tracking_warning": ""
}
```

