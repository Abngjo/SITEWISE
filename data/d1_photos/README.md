---
license: other
license_name: mixed-see-sources-csv
license_link: sources.csv
task_categories:
  - image-classification
tags:
  - qai-hf-hackathon-2026
  - construction
  - qatar
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: train/**/*.jpg
      - split: test
        path: test/**/*.jpg
---

# SITEWISE construction photos

A small labelled photo set for fine-tuning the first-stage classifier in SITEWISE, an AI auditor for construction payment claims in Qatar.
The model's output is an observation for an engineer to review. It is not a certification of work.

## Classes
- `door`: doors and door frames
- `wall`: concrete blockwork and masonry walls, some under construction
- `ceiling`: suspended, tiled or gypsum ceilings
- `other`: site photos where none of the above is the subject

## Counts
| Class | Train | Test |
|---|---|---|
| door | 28 | 8 |
| wall | 28 | 8 |
| ceiling | 28 | 8 |
| other | 28 | 8 |

## Split
Split by photographer across all classes, so no photographer appears in both train and test. There are 111 photographers in total.

## Sources and licences
All images come from Wikimedia Commons and were picked by hand from search and category results. The licence is **mixed, see `sources.csv`**, which gives the author, source URL and licence of every image.

- CC BY-SA 4.0: 42
- CC BY-SA 3.0: 32
- CC BY 2.0: 20
- Public domain: 18
- CC BY 3.0: 11
- CC BY-SA 2.0: 10
- CC0: 6
- CC BY 4.0: 4
- CC BY 2.5: 1

CC BY and CC BY-SA images require attribution, and CC BY-SA images must be shared under the same licence. Images are thumbnails up to 500px wide.

## Limitations
- Most photos are not from Qatar or the Gulf, and many show finished rather than in-progress work, so accuracy on real Qatar site photos may be lower than the test score.
- The dataset is small and labels were assigned by one person looking at thumbnails. A photo can show more than one class; its label is the main subject.
- It is not suitable for measuring installed quantity, quality or compliance.
