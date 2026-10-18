# Coach failure diagnosis — Layer 1

Read-only diagnosis, 2026-10-14: all 9 sessions, 113 runs, 121 coaching_jobs, 9 coaching_jobs_v2 and saved histories in data/fencecoach.sqlite3; data logs, evals/results, evals/coach_audit, work/coach-audit logs; Codex thread 01a138b9-5e3f-75f3-8512-f968ba7825ec (confirms review failures, adds no athlete chat). Audit fixtures and fast scripted DB smoke runs are excluded.

**10 historical failure episodes, 34 turns, exactly 4 identifiable saved session chat streams** retained; fewer than 10 independent conversations in this selection. Overlapping context is not independent history. Fill the gap with explicitly labeled **replays of these same sequences** on both providers. Original turns, complete old summaries/errors, requests and IDs: `evals/layer1/historical_inputs.json`. The DB lacks an author flag: human provenance is conservatively inferred from saved context, timings, script matches and the user-confirmed October 14 sequence.

| Episode | Original excerpt / old behavior | Failure tag | DB table + job source |
|---|---|---|---|
| H01 | “what about my knees and legs” → “Focus on the arm extension for now.” | lost topic | coaching_jobs:aad1cf338a3d45e18995a07f7c1cf390 (full chain in inputs) |
| H02 | “which arm” → repeats “extend your arm to the side” without naming the arm. | lost topic | coaching_jobs:9853845b1c6a4594a2a9dbb9e20883c9 (full chain in inputs) |
| H03 | General “at what angle should i extend my sword arm and non sword arm” → tracking refusal. | router misclassification | coaching_jobs:b54f11b07a2a4e60bbfcf5b7a98258a3 (full chain in inputs) |
| H04 | Flèche follow-up → “After executing the lunge…” loses the action. | lost topic | coaching_jobs:267f2c4bd73d4561a7cc40a1e3ef5464 (full chain in inputs) |
| H05 | “so what should i do” → generic explosive-drive advice drops measured rep/hold context. | lost topic | coaching_jobs:544032a6a94c4f6f945a9598bc27f375 (full chain in inputs) |
| H06 | “what about my last rep” → provider error, then treats rep 2 as last in a five-rep clip. | provider error | coaching_jobs:350a36c9dc4d4692ac12384ebc263f3c (full chain in inputs) |
| H07 | “what about torso” → “I don't have usable movement evidence”; next torso reply gives knee angle. | lost topic | coaching_jobs:1c9e6a5a109944748f0e060d4d26f434 (full chain in inputs) |
| H08 | “was it good” after rear-leg question → answers about front knee. | lost topic | coaching_jobs:1e5facfad0664c35b289e2161d445a15 (full chain in inputs) |
| H09 | “so is this good” / “so its good to have it upright correct?” → repeats torso measurement; straighter/bent later times out. | prompt pushing refusal | coaching_jobs_v2:a9f7a72a021f493b93f198d5a7f9ba8f (full chain in inputs) |
| H10 | “how is my arm extension” → reach ratio 1.0 only; “is this good or bad, do i need to make any changes” → CoachAnswerError. | check blocking reply | coaching_jobs_v2:daeb1c0cf2b84dfabc37ddaa0aa15bc0 (full chain in inputs) |

Mechanism: routing/retrieval narrows evidence prematurely; selectors repeat numbers instead of interpreting follow-ups; review/repair rejects prose after a partial answer. Empty-retrieval/prompt-refusal causes are suspected, not proven where traces are missing. Layer 1 must supply session context and recent messages every turn, let the model choose evidence and answer, and expose provider errors. Preserve the old production safeguards.
