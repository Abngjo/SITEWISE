# A6 fine-tuned SigLIP2 compatibility

Checkpoint: `mfjbrr/team-QH045-sitewise`. Real local stage-one inference; provider calls disabled.

| Stage-one setup | Accuracy | Macro F1 | Mean latency | Errors |
|---|---:|---:|---:|---|
| Captain zero-shot baseline | 91.89% | 0.921 | 0.0248s | other (9).jpg, wall (2).jpg, wall.jpg |
| Person D fine-tuned | 97.30% | 0.973 | 0.0400s | other (9).jpg |

## Compatibility checks

- Pipeline kind: `ft`; device: `cuda:0`; model_id: `mfjbrr/team-QH045-sitewise`.
- Labels: `door, wall, ceiling, other` with normalized scores summing to one.
- Production threshold remains 0.80; 1/37 development photos would escalate.
- Real low-confidence case: `test/other/other_005.jpg` at 0.531979 from previously evaluated A7 held-out example (routing check only); routed via offline VLM stub.
- Category mismatch case: `door (1).jpg` declared `wall`; routed via offline VLM stub.
- Repeating the low-confidence photo produced a SHA-256 inference cache hit with no second VLM stub call.
- Duplicate detection remained compatible (`exact`); embedding length 768.
- Cost logs identify the fine-tuned repo as the stage-one model; review/certification flags remain safe.
- Existing provider order remains `google/gemma-4-31B-it` then `Qwen/Qwen2.5-VL-72B-Instruct`.

No production environment setting, threshold, routing model, contract, or API response shape was changed.

## Acceptance and limitations

- A6 acceptance passes: setting `SITEWISE_FINETUNED_MODEL=mfjbrr/team-QH045-sitewise` selects the real
  `image-classification` path, preserves the four canonical labels, and returns that Hub repository in `model_id`.
- The existing A7 held-out measurement remains 32/32; this A6 task did not retune on the held-out split.
- The one development error is `other (9).jpg` predicted as `door` at 0.814791. It escalates at threshold 0.80
  only through declared-category mismatch, so missing or incorrect declarations remain a reliability limitation.
- The fine-tuned classifier and base SigLIP2 embedding encoder are separate loaded models. This preserves the
  captain's duplicate behavior but has a larger memory footprint than stage-one classification alone.
- The low-confidence and VLM paths used an offline stub. Existing Gemma-to-Qwen behavior is covered by the A2
  mock suite; no provider availability or billing was tested here.
