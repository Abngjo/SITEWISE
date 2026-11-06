"""Check that your HF token can call the SITEWISE models via Inference Providers.
Run from the repo root:  python scripts/test_hf_access.py  [optional path/to/photo.jpg]
Reads HF_TOKEN from the environment or .env. Costs a few cents at most.
"""
import base64
import io
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from huggingface_hub import InferenceClient, whoami
from PIL import Image

token = os.getenv("HF_TOKEN")
if not token:
    sys.exit("HF_TOKEN not set (put it in .env)")
print("Logged in as:", whoami(token=token).get("name"))

if len(sys.argv) > 1:
    raw = Path(sys.argv[1]).read_bytes()
else:  # tiny synthetic image if no photo given
    b = io.BytesIO()
    Image.new("RGB", (256, 256), (150, 120, 90)).save(b, format="JPEG")
    raw = b.getvalue()
img_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()

client = InferenceClient(token=token)
VISION = ["Qwen/Qwen3.5-9B", "google/gemma-4-31B-it", "Qwen/Qwen2.5-VL-72B-Instruct", "Qwen/Qwen2.5-VL-7B-Instruct"]
TEXT = ["Qwen/Qwen3.5-9B", "Qwen/Qwen2.5-7B-Instruct"]

print("\n--- Vision (photo -> JSON) ---")
for m in VISION:
    t = time.time()
    try:
        out = client.chat_completion(model=m, max_tokens=300, messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": img_url}},
            {"type": "text", "text": 'Answer ONLY with JSON: {"label": "door|wall|ceiling|other", '
                                     '"completion": "complete|partial|not_started|unclear", "reason": "<short>"}'}]}])
        print(f"OK   {m}  ({time.time()-t:.1f}s)  ->  {out.choices[0].message.content[:160]!r}")
    except Exception as e:
        print(f"FAIL {m}  ->  {str(e)[:160]}")

print("\n--- Text (Arabic letter paragraph) ---")
for m in TEXT:
    t = time.time()
    try:
        out = client.chat_completion(model=m, max_tokens=200, messages=[{"role": "user", "content":
              "Write one formal sentence in Modern Standard Arabic asking a contractor for updated site photos. No numbers."}])
        print(f"OK   {m}  ({time.time()-t:.1f}s)  ->  {out.choices[0].message.content[:160]!r}")
    except Exception as e:
        print(f"FAIL {m}  ->  {str(e)[:160]}")

print("\nUse the first OK vision model as SITEWISE_VLM_MODEL and the first OK text model as SITEWISE_LLM_MODEL.")
