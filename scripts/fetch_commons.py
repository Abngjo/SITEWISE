"""Step 1 of the D1 build: download a review pool of licensed Wikimedia Commons photos (owner: Dev D).

Only CC0 / public domain / CC BY / CC BY-SA files are kept. Images are 500px thumbnails (the model reads 224px).
Writes <pool>/<class>/NNN.jpg and <pool>/pool.json. A person then picks images by eye; see build_d1.py.
Usage: python scripts/fetch_commons.py --pool DIR [--per-class 130] [--classes door other]
"""
import argparse, collections, concurrent.futures as cf, html, json, os, random, re, time
import requests

API = "https://commons.wikimedia.org/w/api.php"; MAX_PER_AUTHOR = 5
S = requests.Session(); S.headers["User-Agent"] = "SITEWISE-hackathon-dataset/0.2 (student hackathon project)"
OK_LIC = re.compile(r"^(cc0|public domain|pd\b|cc[- ]by(?![- ]n)(?:[- ]sa)?\b)", re.I)
SOURCES = {
    "door": {"cats": ["Interior doors", "Fire doors", "Door frames"],
             "search": ["interior door frame installed", "fire door corridor", "hospital door corridor", "office door interior",
                        "door frame construction", "new door installation"]},
    "wall": {"cats": ["Concrete block walls"],
             "search": ["blockwork under construction", "concrete block wall construction", "cinder block wall building site",
                        "laying concrete blocks", "masonry wall construction site", "hollow block wall"]},
    "ceiling": {"cats": ["Dropped ceilings"],
                "search": ["suspended ceiling installation", "drop ceiling grid", "gypsum ceiling installation",
                           "plasterboard ceiling", "acoustic ceiling tiles", "false ceiling"]},
    "other": {"cats": ["Construction in Qatar", "Construction sites in Qatar", "Construction in Dubai",
                       "Construction sites in the United Arab Emirates"],
              "search": ["construction site excavator", "rebar reinforcement construction", "tower crane construction site",
                         "scaffolding construction site", "concrete pouring construction", "formwork construction site"]},
}

# Second round: tighter searches for classes where the first round gave too few clean photos.
ROUND2 = {
    "door": {"cats": [], "search": ["white door room interior", "wooden interior door closed", "apartment door interior", "door handle interior door",
                                    "steel door frame", "corridor doors hospital", "school classroom door", "toilet door building"]},
    "wall": {"cats": [], "search": ["concrete masonry unit wall", "CMU block wall", "building a block wall", "concrete block house under construction",
                                    "hollow concrete blocks wall", "cinder block interior wall", "unfinished block wall", "blockwork wall"]},
    "ceiling": {"cats": [], "search": ["ceiling grid installation", "suspended ceiling office", "ceiling tiles office", "gypsum board ceiling",
                                       "ceiling under construction", "metal ceiling grid", "corridor ceiling lights", "drywall ceiling"]},
    "other": {"cats": [], "search": ["excavator digging site", "concrete mixer truck site", "building foundation construction", "steel beams construction",
                                     "construction materials pile", "tower crane", "reinforcement bars", "earthworks site"]},
}

def post(**p):
    p.update(action="query", format="json", formatversion=2, prop="imageinfo", iiprop="url|mime|size|extmetadata", iiurlwidth=500)
    for i in range(10):
        r = S.post(API, data=p, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 20)) + 2 + 3 * i); continue
        r.raise_for_status(); time.sleep(0.5); return r.json()
    raise RuntimeError("still rate limited")

def query(**gen):
    """All files for one generator, up to about 100; imageinfo can arrive across continuation pages."""
    pages, cont = {}, {}
    for _ in range(6):
        d = post(**gen, **cont)
        for pg in d.get("query", {}).get("pages", []):
            if pg.get("imageinfo"): pages[pg["title"]] = pg["imageinfo"][0]
        if "continue" not in d or len(pages) >= 100: break
        cont = d["continue"]
    return pages

def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()

def candidates(spec):
    lists = []
    for c in spec["cats"]:
        lists.append(("cat:" + c, query(generator="categorymembers", gcmtitle="Category:" + c, gcmtype="file", gcmlimit=50)))
    for q in spec["search"]:
        lists.append(("search:" + q, query(generator="search", gsrnamespace=6, gsrsearch=q + " filetype:bitmap", gsrlimit=50)))
    out, seen = [], set(); skipped = collections.Counter()
    for via, pages in lists:
        rows = []
        for t, ii in pages.items():
            if t in seen: continue
            seen.add(t); em = ii.get("extmetadata", {}); lic = clean(em.get("LicenseShortName", {}).get("value", ""))
            if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 640: skipped["format/size"] += 1; continue
            if not OK_LIC.match(lic): skipped["licence"] += 1; continue
            rows.append(dict(title=t, via=via, license=lic, author=clean(em.get("Artist", {}).get("value", ""))[:80] or "unknown",
                             url=ii["descriptionurl"], img=ii["thumburl"]))
        random.shuffle(rows); out.append(rows)
    return out, skipped

def fetch(job):
    r, path = job
    for i in range(8):
        x = S.get(r["img"], timeout=60)
        if x.status_code == 429:
            time.sleep(int(x.headers.get("Retry-After", 15)) + 2 + 3 * i); continue
        if x.status_code != 200: return None
        with open(path, "wb") as fh: fh.write(x.content)
        time.sleep(0.3); return r
    return None

ap = argparse.ArgumentParser(); ap.add_argument("--pool", required=True); ap.add_argument("--per-class", type=int, default=130)
ap.add_argument("--classes", nargs="*", default=list(SOURCES)); ap.add_argument("--round2", action="store_true"); args = ap.parse_args(); random.seed(7)
if args.round2: SOURCES = ROUND2
index_path = f"{args.pool}/pool.json"; index = json.load(open(index_path, encoding="utf-8")) if os.path.exists(index_path) else {}
for lab in args.classes:
    t0 = time.time(); lists, skipped = candidates(SOURCES[lab]); per_auth = collections.Counter(); picked = []
    old = index.get(lab, []); known = {r["title"] for r in old}; lists = [[r for r in rows if r["title"] not in known] for rows in lists]
    for r in old: per_auth[r["author"]] += 1
    while any(lists) and len(picked) < args.per_class:           # round robin over sources, for variety
        for rows in lists:
            while rows:
                r = rows.pop()
                if per_auth[r["author"]] < MAX_PER_AUTHOR:
                    per_auth[r["author"]] += 1; picked.append(r); break
    os.makedirs(f"{args.pool}/{lab}", exist_ok=True)
    jobs = [(r, f"{args.pool}/{lab}/{i + len(old):03d}.jpg") for i, r in enumerate(picked[:args.per_class])]
    with cf.ThreadPoolExecutor(2) as ex: list(ex.map(fetch, jobs))
    index[lab] = old + [dict(r, file=os.path.basename(p)) for r, p in jobs if os.path.exists(p)]
    json.dump(index, open(index_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(lab, "pool", len(index[lab]), "skipped", dict(skipped), f"{time.time()-t0:.0f}s", flush=True)
