# /// script
# requires-python = ">=3.10"
# dependencies = ["transformers>=4.49", "datasets", "torch", "accelerate", "evaluate", "scikit-learn", "huggingface_hub", "pillow"]
# ///
"""Fine-tune SigLIP2 for SITEWISE visual classes on HF Jobs (owner: Dev D).

Dataset (Hub, imagefolder layout):  CAPTAIN/team-NN-sitewise-photos
  train/door/*.jpg  train/wall/*.jpg  train/ceiling/*.jpg  train/other/*.jpg
  test/door/...     (split by SOURCE/project where possible, not random photos of the same site)

Launch (check flags with `hf jobs uv run --help`):
  hf jobs uv run --flavor a10g-small --timeout 1h --secrets HF_TOKEN \
     finetune/train_siglip2.py --dataset CAPTAIN/team-NN-sitewise-photos --push CAPTAIN/team-NN-sitewise

The job disk is wiped at the end: the model is pushed to the Hub from inside the job.
NOTE: written before the event data existed; run a 1-epoch smoke test first.
"""
import argparse
import json

import numpy as np
from datasets import load_dataset
from sklearn.metrics import classification_report
from transformers import (AutoImageProcessor, AutoModelForImageClassification, Trainer,
                          TrainingArguments)

p = argparse.ArgumentParser()
p.add_argument("--dataset", required=True)
p.add_argument("--push", required=True)
p.add_argument("--base", default="google/siglip2-base-patch16-224")
p.add_argument("--epochs", type=int, default=5)
p.add_argument("--lr", type=float, default=5e-5)
args = p.parse_args()

ds = load_dataset(args.dataset)
labels = ds["train"].features["label"].names
id2label = dict(enumerate(labels))
label2id = {v: k for k, v in id2label.items()}

proc = AutoImageProcessor.from_pretrained(args.base)
model = AutoModelForImageClassification.from_pretrained(
    args.base, num_labels=len(labels), id2label=id2label, label2id=label2id, ignore_mismatched_sizes=True)


def tf(batch):
    out = proc([im.convert("RGB") for im in batch["image"]], return_tensors="pt")
    out["labels"] = batch["label"]
    return out


ds = ds.with_transform(tf)
eval_split = "test" if "test" in ds else "validation"


def metrics(ev):
    pred = np.argmax(ev.predictions, axis=1)
    return {"accuracy": float((pred == ev.label_ids).mean())}


trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir="out", per_device_train_batch_size=16, per_device_eval_batch_size=32,
        num_train_epochs=args.epochs, learning_rate=args.lr, eval_strategy="epoch",
        save_strategy="epoch", load_best_model_at_end=True, metric_for_best_model="accuracy",
        remove_unused_columns=False, logging_steps=10, report_to="none",
        push_to_hub=True, hub_model_id=args.push, hub_strategy="end", fp16=True),
    train_dataset=ds["train"], eval_dataset=ds[eval_split], compute_metrics=metrics,
)
trainer.train()

pred = trainer.predict(ds[eval_split])
report = classification_report(pred.label_ids, np.argmax(pred.predictions, 1),
                               target_names=labels, output_dict=True)
print(json.dumps(report, indent=1))
trainer.push_to_hub(commit_message="SITEWISE fine-tuned SigLIP2")
proc.push_to_hub(args.push)
# Paste the printed per-class precision/recall/F1 into the model card (finetune/MODEL_CARD.md).
