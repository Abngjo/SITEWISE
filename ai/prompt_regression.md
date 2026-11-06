# A1 prompt regression

Compared the captain's current prompts with the pre-sync descriptive prompts on exactly 37 development photos. Person D's held-out A7 test split was not read. Both sets used the same model instance, RGB/768px preprocessing, label order, normalized scoring, and randomized repeated timing. No provider was reachable.

| Prompt set | Accuracy | Macro F1 | Mean latency | Median latency | Errors |
|---|---:|---:|---:|---:|---|
| captain_current | 91.89% (34/37) | 0.921 | 0.0250s | 0.0249s | other (9).jpg, wall (2).jpg, wall.jpg |
| previous_descriptive | 100.00% (37/37) | 1.000 | 0.0252s | 0.0251s | none |
| minimal_wall_other | 100.00% (37/37) | 1.000 | 0.0252s | 0.0251s | none |

## Exact prompt differences

| Class | Captain current | Previous descriptive |
|---|---|---|
| door | a photo of an installed interior door in a building under construction | a photo of a building door or door frame |
| wall | a photo of a concrete blockwork wall under construction | a photo of a masonry wall made of bricks or concrete blocks |
| ceiling | a photo of a suspended ceiling being installed | a photo of a suspended ceiling with panels or tiles |
| other | a photo of a construction site with no door, wall or ceiling work visible | a photo of construction equipment, stairs or another building element |

## Error ablations

- `other (9).jpg`: current `door` vs truth `other`; smallest fixing prompt swap: `other`. The truth-label raw match rose from 0.00009291 to 0.00347514 while the door match remained 0.00031583.
- `wall (2).jpg`: current `other` vs truth `wall`; either `wall` or `other` alone fixes it. In the minimal two-string candidate, the wall raw match rose from 0.00066128 to 0.11473475 and the competing other match fell from 0.00075845 to 0.00029315.
- `wall.jpg`: current `other` vs truth `wall`; smallest fixing prompt swap: `wall`. In the minimal candidate, the wall raw match rose from 0.00047818 to 0.01276034 and the competing other match fell from 0.00490908 to 0.00008976.

## Recommendation

The previous prompts consistently outperform the current set on this development regression. The exhaustive error ablations show that no one-string edit fixes all three errors; the validated two-string `minimal_wall_other` candidate reaches the same 37/37 result. Change only `wall` and `other`, then rerun this regression before touching routing or thresholds.

Reproduce with:

```powershell
.\.venv\Scripts\python.exe -m ai.evaluate_prompt_regression --repeats 3
```
