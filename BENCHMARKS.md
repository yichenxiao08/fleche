# Flèche Benchmarks

Generated from recorded results. Missing results are not success claims.

## Video regression

| Clip | QA | Tracking coverage | Lunge precision | Lunge recall |
|---|---|---:|---:|---:|
| commons/dourdan-04 | unsupported | 81.9% | not measured | 0.0% |
| footwork-clips/rigin-meinhardt-2016-t8-175000-185000 | unsupported | 74.2% | not measured | not measured |
| footwork-clips/rigin-meinhardt-2016-t8-416000-424000 | unsupported | 95.8% | not measured | 0.0% |
| mit-ocw/advance_lunge | unsupported | 0.0% | not measured | 0.0% |
| mit-ocw/jumpe_lunge | unsupported | 94.5% | 100.0% | 100.0% |
| mit-ocw/jump_forward_jump_back | unsupported | 74.0% | not measured | not measured |
| mit-ocw/jump_lunge_group | unsupported | 77.3% | not measured | 0.0% |
| mit-ocw/parry_4_repost | unsupported | 83.5% | 100.0% | 100.0% |

Coverage is landmark usability, not correct-athlete accuracy. Rep scores use partially reviewed intervals and permissive boundary matching; they are not general action-recognition accuracy.
Regression baseline is explicit; a passing engineering regression is not proof that a clip is supported or correctly coached.

## Coach model comparison (before reply-speed changes)

| Model | Answers | Evidence traceability | Unsupported-claim flags | p50 / p95 ms | Cost USD |
|---|---:|---:|---:|---:|---:|
| qwen2.5:1.5b | 25 | 100.0% | 0.0% | 9770 / 16636 | 0 |
| qwen2.5:3b | 25 | 100.0% | 0.0% | 17781 / 25456 | 0 |
| AWS Bedrock Claude | unavailable: Not executed: authenticated model access and cost configuration are required. | — | — | — | — |

Unsupported-claim flags are automated heuristics, not expert ratings. Local provider cost is zero API fees; hardware/energy cost is not included.
Traceability checks reference IDs and explicit measurement numbers; citation presence alone is not semantic grounding. Topic and answer-shape checks below are keyword proxies, not human usefulness ratings.

```json
[
  {
    "model": "qwen2.5:1.5b",
    "evidence_citation_coverage": 1.0,
    "question_topic_rate": 1.0,
    "assessment_shape_proxy_rate": 0.8,
    "grounding_replacement_rate": 0.4,
    "failures": 0,
    "first_text_samples": 25,
    "first_text_p50_ms": 1059.6253000112483,
    "first_text_p95_ms": 8723.500220006099
  },
  {
    "model": "qwen2.5:3b",
    "evidence_citation_coverage": 1.0,
    "question_topic_rate": 1.0,
    "assessment_shape_proxy_rate": 0.84,
    "grounding_replacement_rate": 0.52,
    "failures": 0,
    "first_text_samples": 25,
    "first_text_p50_ms": 3492.565199994715,
    "first_text_p95_ms": 18081.446719999076
  }
]
```

First-text latency measures the first checked text callback; it excludes browser polling/render time and missing callbacks. Full-answer latency is reported in the model table.
The preceding two-model comparison is historical. The newer reply-speed checks below use the updated routine-answer path and must not be treated as a new two-model quality comparison.

## Routine reply speed

| Run | Requests | Completion p50 / p95 ms | First checked text p50 ms | Grounding replacements |
|---|---:|---:|---:|---:|
| before | 8 | 2709 / 5088 | 1473 | 3/8 |
| after | 8 | 1684 / 2913 | 1029 | 5/8 |
| after-full | 27 | 2040 / 3148 | 1184 | 19/27 |
| http | 4 | 2294 / 2933 | 1196 | 1/4 |

Before/after use the same eight warmed requests on the same local qwen2.5:1.5b model. After-full covers 25 offline diagnostic questions plus two conversational follow-ups. Unsupported footage is used only for offline checks; production coaching remains gated. HTTP uses synthetic demo measurements, the real queue, accumulating conversation history, and 100ms polling.
These checks do not cover cold starts, queue contention, multi-tool plans, or expert usefulness. Nineteen of the 27 wider diagnostic answers required conservative grounding replacement: speed is improved, but reliable personal corrections are not established. Zero heuristic flags does not imply semantic correctness.
Shorter prompts, representative source measurements, relevant tool schemas, and a 112-token default ordinary-reply budget reduce generation work. Checked complete routine answers can end early; detailed answers and tool workflows retain larger budgets. Counters may be unavailable when streams close before the provider's final usage chunk; zero is not proof of zero tokens.

## VLM versus pose evidence

```json
{
  "status": "not_run",
  "questions": 30,
  "independent_action_labels": 16,
  "technique_accuracy": null,
  "reason": "No authenticated frontier vision models configured. Joint geometry and recovery calculations are pipeline proxies, not independently reviewed technique truth."
}
```

Full question-level pose proxies and any executed vision answers are saved in `data/evals/vision.json`. No technique accuracy is available without independent references.

## Flèche beta

Precision and recall are not measured until reviewed flèche examples and negatives exist. Lean, foot crossing, travel, and timing are image-plane proxies; end-of-action balance is not directly measured.

## UI, MCP, and tracing

```json
{
  "browser": {
    "status": "passed",
    "clips": 2,
    "recording": "fake browser camera exercised",
    "upload_job_review_coach_log_reload": true,
    "unsupported_save_disabled": true,
    "mobile_width": 390,
    "page_errors": [],
    "analysis_and_llm": "Synthetic test fixtures; real HTTP, queue, persistence, and UI. Does not validate pose inference or coaching correctness."
  },
  "mcp": {
    "status": "passed",
    "transport": "real stdio subprocess",
    "tools": [
      "get_session_measurements",
      "list_reps",
      "compare_to_baseline",
      "get_practice_history",
      "search_coaching_library"
    ],
    "read_only_annotations": true,
    "unknown_session_error": true,
    "client": "official Python MCP SDK",
    "claude_desktop_code": "Not exercised: Claude is not installed/authenticated on this machine."
  },
  "phoenix": {
    "status": "passed",
    "trace_id": "938fcb1be28ea9d41b152db5c79713c1",
    "model": "qwen2.5:1.5b",
    "latency_ms": 2392.23,
    "input_tokens": 1043,
    "output_tokens": 83,
    "token_usage_available": true,
    "cost_usd": 0.0,
    "spans": [
      "get_session_metrics",
      "search_coaching_library",
      "model_response",
      "coaching_turn"
    ],
    "input": "Synthetic sample measurements; live local model, tools, and actual Phoenix collector."
  },
  "packaging": {
    "status": "definition_and_local_seed_checked",
    "docker_runtime": "not_run: Docker is not installed",
    "compose_services": [
      "ollama",
      "model-init",
      "phoenix",
      "fencecoach"
    ],
    "public_image_tags": "ollama 0.35.1 and Phoenix version-15.0.0 verified HTTP 200 on official Docker Hub API",
    "seeded_examples": 3,
    "seed_idempotency": "unit test passed; unsupported coaching gate preserved",
    "fresh_machine_under_ten_minutes": null,
    "ci": "workflow configured, not executed for this revision"
  }
}
```
