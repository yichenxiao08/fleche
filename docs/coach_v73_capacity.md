# fewshot-v7.3 — capacity blocked before generation

Owner accepted L01underfewshot-v7.2; it will not be rerun. Owner confirmedv7.2L06-T1criterion3FAIL and unsupported aimed well above horizontal from18.2degree direction (criterion2). Prior reply and original manual/owner assessments are preserved in capacity_v73/v72_cases.json,v72_assessment.json and docs/live_acceptance_v72_archive.md. No v7.3reply, fresh chain or model-quality result exists.

## Exact authorized clarification

When the athlete names a topic or rep ('my arm on the second rep', 'my torso') and a coaching cue and readings exist, open with the plain verdict for it ('That's solid', 'That's inconsistent'), then give the supporting observation. A description of the readings is not the verdict. Arm direction describes where the wrist sits relative to the shoulder; do not say the arm is 'aimed' or 'on target' from it.

Appended reminder: Named topic or rep with cue and readings: verdict first, then observation; arm direction shows wrist relative to shoulder, never aim or target alignment.

AST comparison proves all other product code is identical to frozenv7.2. Persona equals original plus exactly the paragraph above; previous reminder retained in full. No examples, KB author/source/writer filtering, map, packet/projection, resolver, default, checker/guard/template or output rewriting changed.

## Capacity recount

Same tokenizer: gemini-3.8-flash countTokens, exact counts for supplied message TEXT joined in original order; excludes message framing and is not Qwen usage. Five preflight count calls plus ten proposal count calls; 15total count-only calls, zero generation/Groq calls, no retries. Raw request text/hash/response retained in capacity_v73/gemini_counts.json.

| Input | v7.2 | v7.3 | ≤6700 |
|---|---:|---:|---|
| L01T4 | 6695 | 6818 | NO |
| L04T4 | 6547 | 6670 | Yes for constructed input |
| L05T1 | 6648 | 6771 | NO |
| L06T3 | 6557 | 6680 | Yes for constructed input |
| L10T3 | 6503 | 6626 | Yes for constructed input |

L01-T4 now uses its EXACT savedv7.2 actualT1–T3history/state request, with only the new static reference substituted. It replaces the older future-history estimate; no L01regeneration. L05-T1needs no history and is an actual initial-input reconstruction. L04/L06/L10 remain capacity estimates based on the previous savedv7.1T1reply model; repeated content can deduplicate already_said and is not a guarantee for unknown future replies. Scope/readings unchanged: L01recovery/allreps;L04arm/rep2;L05unresolvedwithoverview_then_clarifyandoptions;L06torso/reset;L10rearleg/rep2.

All five requests gain123tokens. L01needs at least118tokens saved andL05at least71to meet6700. Under owner step2, STOP before any generation.

## Packet-side proposals — none applied

No sufficient lossless reduction was demonstrated. The smallest measured saving is9tokens per request by omitting the duplicate current_question value from writer projection while retaining its exact value in the final human message and the full saved packet. This is only proposed: gap_scope_note still names current_question, so writer instruction-following must be reviewed if approved.

A shared measurement table factors feature/phase/definition/unit into columns and aligns displayed-value strings to scope.available_reps; string decimals (including trailingzero precision) are preserved. Each unit and definition remains explicit; absent cells are null, not zero. Offline inverse reconstruction reproduces every original per-rep reading and definition exactly, with all other fields unchanged. This saves55tokens forL01T4 and80forL05T1, still insufficient forL01. It changes representation/reading burden and requires owner approval.

| Proposal | L01T4 saving / result | L05T1 saving / result |
|---|---:|---:|
| Omit duplicate question | 9 / 6809 | 9 / 6762 |
| Shared measurement table | 55 / 6763 | 80 / 6691 |
| Both above | 64 / 6754 | 89 / 6682 |
| Lossless YAML flow (counterproductive) | -44 / 6862 | -55 / 6826 |
| Lossless YAML block (counterproductive) | -125 / 6943 | -162 / 6933 |

Best measured combination saves64/89and yields6754/6682. L01still54over; this is NOT a sufficient qualified capacity change. No recommendation to approve it as if it unblocked acceptance. YAML round-trips preserve exact packet dictionaries but increase token counts, so those are rejected proposals. Full projected packets are in capacity_v73/packet_proposals.json; no candidate was applied to product code.

## Validation, manifests and stop

46focused writer/packet/citation unittest tests PASS; scoped Ruff check/formatPASS. Both newv7.3frozen manifests explicitlyBLOCKED, with exact source hash and parentv7.2manifest; originalv7/v7.1/v7.2manifests intact. All non-core frozen hashes matchv7.2, including authoredKB/map/examples/packet/resolver. Existing harness still targetsv7.2 and must not run againstv7.3until capacity is approved/ready; no mismatch bypass. No fresh chain/session was created.

Acceptance status remains anchored to generatedv7.2evidence:1PENDING,2FAIL(ownerL06T1directionclaim),3FAIL(L06T1lateverdict),4PENDING,5PENDING,6PENDING,7PASS(existinginput-only),8PENDING. L01v7.2explicitlyOWNER-PASS; v7.3isPENDING with zero live replies, so no globalpass or claimed fix. No v7.3what-should-I-change reply exists to quote; the full acceptedv7.2L01T3quote remains in the archived/current report.

Stop and wait for owner capacity direction. No L06rerun/L05/L07/L04/L10, no readings or probes, no generation, defaultflip, commit, push, billing/account/key change, localconversationmodel or schedule/automation change. The planned future order is freshL06v7.3,L05,L07,L04,thenL10GroqT1/T2→forcedGroqfailure→realGeminiT3/T4; L10T4why does that matter?. L01stays acceptedv7.2.
