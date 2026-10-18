# Runtime and request accounting

Observed new-phase Gemini model attempts: 314. Includes diagnostic runs, final passes, baseline holdout and live calls; excludes the earlier 57-call Layer 2 baseline and the uninstrumented invalid legacy-worker attempt.

All diagnostics remain saved. final_gemini and verified_gemini are incomplete diagnostics, never blended turn by turn into final scores. The first original_gemini pass identified checker/packet failures. Final original-set runs use whole coherent chains. Latest checker equivalence on all 56 Gemini original turns and all 48 holdout turns was established offline; no replacement API requests were needed. Completed 7B output in the failed rename temp file was recovered, not regenerated.

The quota-blocking evaluation loop stops on quota failure. Each evaluation wrapper spaces actual model calls by six seconds. A brief overlap of the obsolete diagnostic and final run was detected and stopped; no provider quota error occurred. There is no 429 retry loop. Billing was not configured or independently inspected; the user supplied a free-project key.

| Set | Raw provider TTFT median |
|---|---:|
| baseline_gemini | unavailable |
| baseline_3b | 1.62 s |
| baseline_gemini_holdout | unavailable |
| baseline_3b_holdout | 1.02 s |
| gemini_original | unavailable |
| qwen3b_original | 1.53 s |
| qwen7b_original | 2.46 s |
| gemini_holdout | unavailable |
| qwen3b_holdout | 1.34 s |

checkpoint_3b_final: {"prompt_tokens_max": 2455, "generation_tokens_max": 137, "generation_cap_completions": 0}

checkpoint_7b_final: {"prompt_tokens_max": 2693, "generation_tokens_max": 160, "generation_cap_completions": 2}
