# A2 VLM reliability

## Routing configuration

- Stage 1: `google/siglip2-base-patch16-224`
- Primary VLM: `google/gemma-4-31B-it`
- Fallback VLM: `Qwen/Qwen2.5-VL-72B-Instruct`
- Production escalation threshold: `0.80`

`.env.example` now matches these captain defaults and retains the existing environment-variable names.

## Validation and fallback behavior

Each Gemma and Qwen response must contain a JSON object with:

- `label`: `door`, `wall`, `ceiling`, or `other`
- `completion`: `complete`, `partial`, `not_started`, or `unclear`
- `reason`: a non-empty string

Plain JSON, fenced JSON, and a JSON object surrounded by short text are accepted. Empty responses, missing choices,
truncation, invalid JSON, invalid values, missing fields, blank reasons, timeouts, and provider exceptions are rejected.
Gemma is tried once. Qwen is tried once only if Gemma fails or returns an unacceptable answer. If both fail, the
SigLIP2 observation remains review-only and the failure is metered.

Every public path continues to return `requires_review=True` and `completion_certified=False`; even a VLM
`completion="complete"` observation cannot certify work or payment.

## Tests

- Focused A2 reliability tests: **12 passed**
- Full official suite: **34 passed**
- Existing warnings: two FastAPI `on_event` deprecation warnings
- Live model/provider calls: **0**

All AI-importing tests force `SITEWISE_DISABLE_MODELS=1`, `HF_HUB_OFFLINE=1`, and
`TRANSFORMERS_OFFLINE=1` before importing AI modules.

## Remaining limitations

- Timeout duration and transport retry behavior are controlled by the Hugging Face client/provider; SITEWISE handles
  timeout exceptions but does not impose a separate application-level deadline.
- Validation guarantees structure and allowed values, not the factual quality of a model's reason.
- Provider availability was not rechecked live in this offline reliability task.
- There is intentionally no automatic retry of the same model: one Gemma attempt, then at most one Qwen attempt.
