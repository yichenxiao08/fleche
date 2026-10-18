# fewshot-v7.2 capacity review — owner decision required

Only the two approved input changes are implemented. Generation is blocked by the requested <6200-token preflight. No Groq requests or Gemini generation calls; 36 owner-authorized Gemini countTokens calls, no retries. No live chain restarted, default edit, commit, push, schedule change, output checker or reply rewrite. Existing v7.1 L01-T1 retained, with copies of cases/assessment/status/full report in work/live_acceptance_v7/v71_archive. L10-T4 is now "why does that matter?".

## Tokenizer and evidence limits

The previous tokenizer was gemini-3.8-flash remote countTokens. Counts below are exact for the supplied text under that endpoint, not Qwen tokenization and not message-wrapper/admission overhead. Old actual Groq L01-T1 input6929 and pendingT2 admission7029 use different provider accounting; this Gemini T2 text count7096 must not be relabeled actual Groq usage. Separately counted parts can differ at join boundaries; combined requests were counted independently. Full request parts, exact excerpts, raw count responses and SHA256s: work/live_acceptance_v7/capacity_v72/gemini_counts.json.

L01-T4 has no saved v7.1 T2/T3 replies, so an exact future v7.2 request cannot exist yet. The T4 replay uses actual archived v7 three-reply state/history and the current unchanged persona/reference on the real copied-session snapshot. It is capacity/protocol evidence only, not model-quality evidence. L02/L04/L06 have no saved live reply prefixes; their state is deterministically replayed from the planned questions on that saved snapshot and their empty-history counts are LOWER BOUNDS. No assistant reply was fabricated or stored as completed.

## Request components before the approved changes

| Part | L01-T2 saved request | L01-T4 archived-state replay |
|---|---:|---:|
| Persona | 1376 | 1376 |
| Writer KB | 3236 | 3236 |
| Map | 935 | 935 |
| Examples | 538 | 538 |
| Static reminder | 137 | 137 |
| Standalone reminder | 137 | 137 |
| Packet | 602 | 635 |
| History | 87 | 185 |
| Question | 5 | 5 |
| Combined text request | 7096 | 7227 |

The unchanged static reference alone is6265tokens (component texts6222 plus labels/separators and join effects43). It already exceeds6200 before any packet, history or question.

## Approved changes and measured savings

- Remove standalone reminder:137tokens saved on T2 and T4 replay; identical reminder remains at the end of static reference.
- Last two completed exchanges: T4 history185→103, saving82; unchanged packet already_said adds66 (packet635→701), so net16 additional tokens saved. Earlier replies remain in saved state/record/UI. No packet/resolver change.
- Combined T2:7096→6959; combined T4 replay:7227→7074, net153. To reach strictly under6200 the T4 replay still needs at least875tokens saved.

## Offline packet checks

| Input | Before | After a+b | Packet scope | Measurements | Capacity result |
|---|---:|---:|---|---:|---|
| L01T4 | 7227 | 7074 | ['recovery']; reps[]; ['active_recovery'] | 16 | BLOCKED (>6200) |
| L02T3 | 6887 | 6750 | ['rear_leg']; reps[]; ['lunge_finish'] | 7 | BLOCKED (>6200) |
| L04T4 | 6910 | 6773 | ['arm']; reps[2]; ['lunge_finish'] | 2 | BLOCKED (>6200) |
| L06T3 | 7007 | 6870 | ['torso']; reps[]; ['lunge_finish'] | 14 | BLOCKED (>6200) |

L01 recovery selects all available recovery reps; L02 retains rear leg; L04 returns to arm/rep2 after the knee topic; L06 resets the rep/topic and selects torso across the session. Snapshot measurements remain unchanged. These protocol checks do not establish live state carry-over or replace L10.

## Candidate deletions — PROPOSED ONLY; none applied

These are whole writer-copy excerpts for owner review; the authored KB remains unchanged. Power/force teaching, knee safety and pain referral, all measured-topic cues, all drills, examples, persona/map/reminder are retained. Even all candidates below together do not achieve the required margin. Savings are the exact difference in separately counted full T4 text, not a sum of isolated section counts.

| Candidate | Isolated tokens | Whole-request saving |
|---|---:|---:|
| metadata_purpose_compiled | 54 | 53 |
| historical_firm_footed | 39 | 38 |
| general_mobility | 38 | 37 |
| general_muscle_imbalance | 43 | 42 |
| weapon_research_background | 115 | 114 |

Combined candidates save284:7074→6790, still needing591more tokens to reach6199. I cannot identify a sufficient deletion set within the protected coaching criteria without further owner direction; no unsupported claim that a safe qualifying minimum set exists.

### metadata_purpose_compiled

```text
**Purpose:** Reference material for a coaching agent giving feedback on the fencing lunge (foil, épée, sabre).
**Compiled:** October 2026 from web research. All content is paraphrased from the sources listed at the end.
```

### historical_firm_footed

```text
- **Firm-footed lunge** (historical Italian rapier): the front foot stays planted while the body extends. Mostly of historical interest in modern sport fencing. `[MED]`
```

### general_mobility

```text
- **Mobility:** Hips, hip flexors, hamstrings, groin, lower back and ankles. Flexibility helps but technique matters more than raw range. `[MED]`
```

### general_muscle_imbalance

```text
- **Muscle imbalance:** Repeated lunging loads the lead and rear sides asymmetrically. A study of elite fencers used targeted training to reduce this imbalance. Suggest balanced strength work. `[MED]`
```

### weapon_research_background

```text
- **Foil / épée:** Both are taught the lunge in the same way, but a 2024 study of 16 foil and 16 épée fencers found different arm-leg and shoulder-hip coordination between them, which the authors tie to each weapon's rules. A small EMG study (8 subjects) found higher rectus femoris activity in foil lunges, and noted that épée fencers also train the fléche heavily. Treat both as suggestive, not definitive. `[LOW–MED]`
```

## Validation and stop

45focused unittest tests PASS (writer, packet core, citation iteration), including a new capture regression proving last-two-exchange history, one retained static reminder, correct arm/rep2 measurements despite a dropped earlier exchange, unchanged saved history/trace and verbatim output. Ruff check and format check PASS for both edited files. Initial new test used an invalid fixture scope literal; corrected the fixture to the existing session scope, with no product scope change.

Exact text comparison confirms core_packet.py differs from v7.1 by only the revision label and approved a/b changes. New frozen fewshot-v7.2 manifests exist for qwen and gemini, explicitly capacity-BLOCKED; all other frozen file hashes match v7.1. Original v7/v7.1 manifests retained. The live harness still targets v7.1 and must not be invoked against this source while preparation is blocked. No manifests bypassed or falsely marked ready.

No new live replies: criterion7 remains existing input-only PASS; criteria1–6 and8 remain PENDING globally. Old v7 criterion2FAIL and owner-approved v7.1T1 retained. L01 what-should-I-change reply is UNRUN, so no new full quote or timing/locked judgment exists. Stop before step4 under owner step2c; wait for approval of further writer-copy capacity reductions. No additional run will start autonomously.
