# Five-stage finish status

Updated October 9, 2026. Implementation was performed in plan order using existing footage, as requested. Stage completion does not mean every external acceptance criterion has passed.

| Stage | Implemented and checked | Missing acceptance evidence |
|---|---|---|
| 1 / scope and QA | Three verdict levels, filming tips, solo-only gate, experimental feature labels, coaching gate on old/new sessions | 0/8 existing golden clips supported; five clean supported clips including three flèche examples are absent |
| 2 / video regression | Source/label pins, contact sheets, coverage and reviewed-interval rep metrics, explicit regression baseline, disagreements kept uncertain | Accepted-clip correct-athlete tracking and validated flèche repetitions |
| 3 / coach | Cached evidence, compact relevant evidence, bounded replies and checked early completion; historical 1.5b checks at 2.04s median / 3.15s p95; now 3b default with cited clarification guidance and repeated-answer checks; beta flèche metrics | Expert usefulness/semantic grounding; 19/27 historical diagnostic answers needed conservative replacements; the newer 3b clarification check is narrow and broader performance remains unverified; hosted Claude comparison unavailable |
| 4 / full flow | Desktop/mobile smoke green on two clips with synthetic inference; five real MCP protocol tool calls; live local model traces reach actual Phoenix | Claude Desktop/Code not installed/authenticated; 30-case vision harness prepared but frontier comparison not executed; independent technique answers absent |
| 5 / packaging | One-command Compose definition, pinned public image tags, three attributed preprocessed archival examples, README/benchmarks, recorded demo, CI wiring | Docker absent locally; fresh-machine under-ten-minute run and CI execution for this revision unverified |

The archived examples deliberately demonstrate an unsupported state. The synthetic measurement example demonstrates workflow wiring. Neither is evidence of excellent personal coaching.

Gemini Developer API chat was connected on October 9 with `gemini-3.8-flash`. A generic arm-role question completed through the actual conversation and retrieval workflow in 3.63 seconds with one reference consulted. This confirms access and workflow wiring for that request; a hosted/local quality comparison, tool-heavy latency and expert coaching usefulness remain unmeasured. The key stays in the ignored server `.env` file.

## Next priorities

1. Obtain several full-body fixed-camera modern solo clips that pass QA and inspect the overlays. Existing public footage can be used if it meets those conditions and has appropriate reuse rights.
2. Get a qualified coach to identify a small set of visible issues, appropriate cues, and “no correction” cases. Automate preparation and review forms; reserve human time for correctness judgments.
3. Lock evaluation recordings apart from development clips and compare pipeline observations and coaching usefulness against those independent references.
4. Run the Docker stack and MCP in the intended external client; authenticate hosted models for speed and vision comparisons.

No expert accuracy, generalized gesture recognition, autonomous ground-truth labeling, validated flèche detector, or production cloud scale is claimed.
