"""Step 2 of the D1 build: turn hand-picked pool images into data/d1_photos (owner: Dev D).

picks.json = {"door": ["003.jpg", ...], "wall": [...], "ceiling": [...], "other": [...]}
Splits by photographer across all classes (one photographer is never in both train and test), balances classes,
then writes train/<class>/, test/<class>/, sources.csv and README.md (the dataset card).
Usage: python scripts/build_d1.py --pool DIR --picks picks.json [--train 50] [--test 12]
"""
import argparse, collections, csv, glob, json, os, random, re, shutil, time
from PIL import Image

OUT = "data/d1_photos"; CLASSES = ["door", "wall", "ceiling", "other"]
ap = argparse.ArgumentParser(); ap.add_argument("--pool", required=True); ap.add_argument("--picks", required=True)
ap.add_argument("--train", type=int, default=50); ap.add_argument("--test", type=int, default=12); args = ap.parse_args()
random.seed(7)
index = json.load(open(f"{args.pool}/pool.json", encoding="utf-8")); picks = json.load(open(args.picks, encoding="utf-8"))
chosen = []
for lab in CLASSES:
    by_file = {r["file"]: r for r in index[lab]}
    for f in picks.get(lab, []):
        r = dict(by_file[f]); Image.open(f"{args.pool}/{lab}/{f}").verify(); r["label"] = lab; chosen.append(r)

# Split by photographer across all classes, taking test images from small groups first.
groups = collections.defaultdict(list)
for r in chosen: groups[r["author"]].append(r)
names = sorted(groups); random.shuffle(names); names.sort(key=lambda a: len(groups[a]))
test_n = collections.Counter()
for a in names:
    c = collections.Counter(r["label"] for r in groups[a])
    to_test = all(test_n[l] + n <= args.test for l, n in c.items()) and any(test_n[l] < args.test for l in c)
    for r in groups[a]: r["split"] = "test" if to_test else "train"
    if to_test: test_n.update(c)

# Balance: every class gets the same train and test size, limited by the smallest class.
avail = {s: {l: [r for r in chosen if r["label"] == l and r["split"] == s] for l in CLASSES} for s in ("train", "test")}
n_train = min(args.train, *[len(v) for v in avail["train"].values()]); n_test = min(args.test, *[len(v) for v in avail["test"].values()])
for f in glob.glob(f"{OUT}/*/*/*.jpg"): os.remove(f)
rows = []
for split, n in (("train", n_train), ("test", n_test)):
    for lab in CLASSES:
        os.makedirs(f"{OUT}/{split}/{lab}", exist_ok=True)
        for i, r in enumerate(avail[split][lab][:n]):
            rel = f"{split}/{lab}/{lab}_{i:03d}.jpg"; shutil.copyfile(f"{args.pool}/{lab}/{r['file']}", f"{OUT}/{rel}")
            rows.append([rel, split, lab, "commons-" + re.sub(r"\W+", "-", r["author"]).strip("-").lower()[:40], r["url"], r["license"],
                         r["author"], time.strftime("%Y-%m-%d"), r["title"]])
with open(f"{OUT}/sources.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["file", "split", "label", "source_group", "source_url", "license", "author", "retrieved", "title"]); w.writerows(rows)

lic = collections.Counter(r[5] for r in rows); n_groups = len({r[3] for r in rows})
lic_lines = "\n".join(f"- {k}: {v}" for k, v in lic.most_common())
card = f"""---
license: other
license_name: mixed-see-sources-csv
license_link: https://huggingface.co/datasets/mfjbrr/team-QH045-sitewise-photos/blob/main/sources.csv
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
""" + "".join(f"| {l} | {n_train} | {n_test} |\n" for l in CLASSES) + f"""
## Split
Split by photographer across all classes, so no photographer appears in both train and test. There are {n_groups} photographers in total.

## Sources and licences
All images come from Wikimedia Commons and were picked by hand from search and category results. The licence is **mixed, see `sources.csv`**, which gives the author, source URL and licence of every image.

{lic_lines}

CC BY and CC BY-SA images require attribution, and CC BY-SA images must be shared under the same licence. Images are thumbnails up to 500px wide.

## Limitations
- Most photos are not from Qatar or the Gulf, and many show finished rather than in-progress work, so accuracy on real Qatar site photos may be lower than the test score.
- The dataset is small and labels were assigned by one person looking at thumbnails. A photo can show more than one class; its label is the main subject.
- It is not suitable for measuring installed quantity, quality or compliance.
"""
open(f"{OUT}/README.md", "w", encoding="utf-8").write(card)
print("train", n_train, "test", n_test, "per class; photographers", n_groups, "; available", {s: {l: len(v) for l, v in d.items()} for s, d in avail.items()})
