# A5 cost logging and SHA-256 inference cache

## Result

The captain's model choices, routing order, normalized-confidence threshold, public inference response,
and existing `/api/ai/costs` fields remain intact. Cost bookkeeping and cache eligibility were tightened.

## Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Record models actually called | Pass | `models_called` lists SigLIP2 and each attempted VLM; cache hits use `models_reused` and call no model. |
| Split SigLIP2 and VLM latency | Pass | Every log row has `siglip_latency_s` and `vlm_latency_s`, plus compatible total `latency_s`. |
| Record tokens only when supplied | Pass | Per-call input/output tokens remain `None` when absent; aggregate usage is `None` if any attempted call is unknown. |
| Separate estimates and confirmed billing | Pass | Estimated, provider-reported estimate, and explicitly confirmed billing fields and sources are distinct. No missing value is synthesized. |
| Record escalation and fallback reasons | Pass | `escalation_reason`, `fallback_reasons`, and per-call errors are retained. |
| Successful identical-photo cache | Pass | SHA-256 + declared category + completion claim reuses a deep-copied successful result with zero new provider calls. |
| Failed/incomplete responses excluded | Pass | Stage-1 failures, VLM failures, invalid/incomplete JSON, and incomplete observations are never cached as successes. |
| Cache savings | Pass | Cache rows record `avoided_provider_cost_usd`; summaries expose cache hits, avoided cost, and savings versus always-VLM. |
| Preserve cost-summary fields | Pass | All prior fields remain; additive fields provide detailed provenance and totals. |
| Local mock and official tests | Pass | 4 focused A5 tests and 20 full tests passed. |

## Remaining limitations

- Provider-confirmed billing is available only if a provider explicitly returns `actual_cost_usd`. Hugging Face
  commonly returns an estimate instead, which is recorded as `provider_reported_estimate`, not confirmed billing.
- The captain's cache and log remain process-local memory. They do not deduplicate simultaneous workers or survive
  restarts; adding persistence would be a separate architecture change.
- When token usage is missing, the configured `SITEWISE_VLM_COST_USD` estimate is retained rather than inventing tokens.

## Tests

```text
tests/test_cost_cache.py: 4 passed
full tests/: 20 passed, 2 existing FastAPI deprecation warnings
```

The final test configuration forces `SITEWISE_DISABLE_MODELS=1` before importing `ai.inference`, preventing model
or provider access regardless of pytest collection order.
