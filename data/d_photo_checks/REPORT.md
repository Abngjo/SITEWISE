# SITEWISE photo checks: what works and what doesn't

Tested on 2026-11-07 with `google/gemma-4-31B-it` through `scripts/evaluate_photo_checks.py`. Raw results are in `results.csv` and `summary.json`. The test images are not in git. Samples are small, so read these as a first check, not as accuracy figures.

**Main finding: Gemma doesn't catch AI-generated photos.** It called all 8 AI images real. Don't claim that SITEWISE detects AI-generated photos.

## Authenticity question

| Photos | Flagged as edited or AI-generated | Meaning |
|---|---|---|
| AI-generated with Z-Image Turbo, 8 | 0 of 8 | All 8 missed |
| Crude cut-and-paste edits, 6 | 4 of 6 | Catches some obvious edits |
| Real photos, test split, 32 | 1 of 32 | One real photo (`door_005`) wrongly flagged |

The cut-and-paste images were made by pasting a door photo onto a wall photo, so a careful edit would be harder to spot. Because the model misses fakes, the app never shows "looks real" as reassurance. It only raises a review flag when the model is suspicious.

The app also flags files whose metadata names an AI generator or editing software. That only works if the metadata is still in the file.

## Dedicated detectors from the Hub

We tested three Apache-2.0 detectors on the same AI images and 39 real photos, using a 0.5 cut-off. None was added, because each one flags too many real photos, misses most fakes, or both.

| Model | AI images flagged | Real photos wrongly flagged |
|---|---|---|
| `dima806/ai_vs_real_image_detection` | 7 of 8 | 32 of 39 |
| `Hemg/AI-VS-REAL-IMAGE-DETECTION` | 8 of 8 | 24 of 39 |
| `NYUAD-ComNets/NYUAD_AI-generated_images_detector` | 1 of 8 | 10 of 39 |

NYUAD's repo wouldn't load on its own, so it was run with a manually set image processor (224 px, mean and std 0.5). That setting is our assumption.

## Completion and stage of work

Both real photos of a door frame with no leaf came back `partial`, stage `frame_only`, which is correct. There are no labelled stages for the other photos, so stage accuracy is otherwise unmeasured. "About 50%" is set by code from `partial`, not measured from the photo. Neither value changes payment.

AI images pass this check too: 2 of the 8 were judged `complete`.

## Effect on A's validated prompt

| Check | Before | After |
|---|---|---|
| Labels, test split, not claimed | 32 of 32 | 32 of 32 |
| Labels, door, wall and ceiling photos, claimed complete | 24 of 24 | 24 of 24 |
| Completion answers on those 24 (complete, partial, not started) | 15, 8, 1 | 15, 8, 1 |
| Tokens per claimed call, input and output (6 photos, run one at a time) | 257 and 37 | 371 and 73 |
| Median Gemma time per claimed call (same 6 photos) | 2.2 s | 3.2 s |

The first version of the new prompt, with the authenticity instruction last, mislabelled `ceiling_004` as a wall 3 times out of 3. Putting the contractor's claim last again fixed it (3 correct out of 3). Keep that order.

Across all photo groups, a Gemma call now costs an estimated $0.00015 to $0.00017, using token counts and the rates in `data/a7_evaluation`. A7's table used the earlier prompt, at $0.000084 for each Gemma call. The cascade row hasn't been re-measured with this prompt, and A7's cascade numbers still exclude completion checks.

## Full uploads

Fresh uploads through the local app, with the fine-tuned model and real Gemma on a laptop CPU, took 5 to 6.5 s, plus one at 14 s. One browser upload took 53 s while its Gemma call took 3 s. It didn't happen again, but a fair timing on the Space is still needed.

## Not tested

- A real phone. Browsers often strip GPS from photos, so `/m` also asks for the phone's location. How much EXIF survives on real iPhones and Android phones is unknown.
- Photos made by other AI generators, or careful edits.

## What the metadata checks can and can't prove

Dates and GPS in a file can be edited, and phone location comes from the uploader's device. These checks catch careless reuse and raise questions for the engineer. They don't prove that a photo is genuine.
