"""Fetch per-file diffs from Overleaf and cache to diff_cache.json.

On each run:
  1. Pull fresh updates from the /updates API, paginating until we reach
     versions already in usage.json (incremental — no duplicate fetches).
  2. Persist the merged updates list back to usage.json.
  3. Fetch only diff entries missing from diff_cache.json.

Configuration is read from config.json (copy config.example.json to get started).
The session cookie can also be supplied via the OVERLEAF_COOKIE environment variable,
which takes precedence over the value in config.json.
"""
import json, os, time, urllib.parse, requests
from pathlib import Path

CONFIG_FILE  = Path("config.json")
CACHE        = Path("diff_cache.json")
USAGE_FILE   = Path("usage.json")

# ── Load config ───────────────────────────────────────────────────────────────
if not CONFIG_FILE.exists():
    raise SystemExit(
        f"'{CONFIG_FILE}' not found. "
        "Copy config.example.json → config.json and fill in your values."
    )

cfg     = json.loads(CONFIG_FILE.read_text())
BASE    = cfg["base_url"].rstrip("/")
PROJECT = cfg["project_id"]
COOKIE  = os.environ.get("OVERLEAF_COOKIE") or cfg["cookie"]

if not COOKIE or COOKIE == "YOUR_OVERLEAF_SESSION_COOKIE":
    raise SystemExit(
        "No session cookie found. Set 'cookie' in config.json "
        "or export OVERLEAF_COOKIE=<value>."
    )

# ── HTTP session ──────────────────────────────────────────────────────────────
session = requests.Session()
session.cookies.set("overleaf.sid", COOKIE,
                    domain=urllib.parse.urlparse(BASE).hostname)
session.headers["Accept"] = "application/json"

# ── 1. Load existing updates and find the highest known version ───────────────
existing_updates: list = []
if USAGE_FILE.exists():
    existing_updates = json.loads(USAGE_FILE.read_text()).get("updates", [])

known_versions: set[tuple] = {(u["fromV"], u["toV"]) for u in existing_updates}
highest_known_toV: int = max((u["toV"] for u in existing_updates), default=-1)

# ── 2. Fetch new updates from the API until we overlap with known ones ────────
print("Fetching update list from Overleaf…")
new_updates: list = []
params: dict = {}

while True:
    url = f"{BASE}/project/{PROJECT}/updates"
    r = session.get(url, params=params, timeout=15)
    r.raise_for_status()
    page = r.json().get("updates", [])
    if not page:
        break

    for u in page:
        if (u["fromV"], u["toV"]) not in known_versions:
            new_updates.append(u)

    oldest_toV_on_page = page[-1]["toV"]
    if oldest_toV_on_page <= highest_known_toV:
        break

    params = {"before": oldest_toV_on_page}
    time.sleep(0.2)

print(f"  {len(new_updates)} new update(s) found.")

# ── 3. Merge and persist usage.json ──────────────────────────────────────────
if new_updates:
    merged = new_updates + existing_updates
    USAGE_FILE.write_text(json.dumps({"updates": merged}, indent="\t"))
    all_updates = merged
else:
    all_updates = existing_updates

# ── 4. Load diff cache ────────────────────────────────────────────────────────
cache: dict = json.loads(CACHE.read_text()) if CACHE.exists() else {}

# ── 5. Build job list and fetch only missing diffs ────────────────────────────
jobs = [
    (u["fromV"], u["toV"], path)
    for u in all_updates
    for path in u.get("pathnames", [])
]

total = len(jobs)
fetched = skipped = errors = 0

for i, (fv, tv, path) in enumerate(jobs):
    key = f"{fv}:{tv}:{path}"
    if key in cache:
        skipped += 1
        continue

    url = (f"{BASE}/project/{PROJECT}/diff"
           f"?from={fv}&to={tv}&pathname={urllib.parse.quote(path)}")
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        cache[key] = r.json()
        fetched += 1
        print(f"[{i+1}/{total}] {fv}->{tv} {path}")
    except Exception as e:
        print(f"[{i+1}/{total}] ERROR {fv}->{tv} {path}: {e}")
        errors += 1

    CACHE.write_text(json.dumps(cache))
    time.sleep(0.25)

print(f"\nDone. fetched={fetched}, skipped={skipped}, errors={errors}")
print(f"Cache entries: {len(cache)}")
