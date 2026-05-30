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
MAX_UPDATE_PAGES = 1000
REQUEST_TIMEOUT = float(os.environ.get("OVERLEAF_REQUEST_TIMEOUT", "30"))
UPDATE_ATTEMPTS = int(os.environ.get("OVERLEAF_UPDATE_ATTEMPTS", "3"))
DIFF_ATTEMPTS = int(os.environ.get("OVERLEAF_DIFF_ATTEMPTS", "3"))
RETRY_HTTP_STATUSES = {429, 500, 502, 503, 504}


def _read_json_file(path: Path, default):
    if not path.exists():
        return default

    try:
        text = path.read_text()
        if not text.strip():
            return default
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"WARNING: {path} is not valid JSON; starting from empty data.")
        return default


def _write_json_file(path: Path, data, **kwargs):
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data, **kwargs))
    temp.replace(path)


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


def _response_error(r: requests.Response, context: str) -> str:
    if r.status_code in (401, 403):
        return (
            "Overleaf rejected the session cookie. Refresh the overleaf.sid "
            "cookie in config.json or OVERLEAF_COOKIE."
        )
    if r.status_code == 429:
        return f"Overleaf rate limited the request while {context}."
    if r.status_code == 404:
        return (
            f"Overleaf returned 404 while {context}. Check base_url, "
            "project_id, and project access."
        )
    return f"Overleaf returned HTTP {r.status_code} while {context}: {r.reason}"


def _get_json(
    url: str,
    *,
    context: str,
    params: dict | None = None,
    attempts: int = UPDATE_ATTEMPTS,
) -> dict:
    last_error = None

    for attempt in range(1, attempts + 1):
        should_retry = False
        try:
            r = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            last_error = f"Timed out while {context}."
            should_retry = True
        except requests.RequestException as e:
            last_error = f"Could not reach Overleaf while {context}: {e}"
            should_retry = True
        else:
            if r.status_code >= 400:
                last_error = _response_error(r, context)
                should_retry = r.status_code in RETRY_HTTP_STATUSES
            else:
                try:
                    return r.json()
                except ValueError as e:
                    raise RuntimeError(
                        "Overleaf returned a non-JSON response. The session "
                        "cookie may be invalid or expired."
                    ) from e

        if not should_retry or attempt == attempts:
            raise RuntimeError(last_error)

        print(f"  Retry {attempt}/{attempts - 1}: {last_error}")
        time.sleep(min(attempt, 5))


# ── 1. Load existing updates and find the highest known version ───────────────
existing_updates: list = []
if USAGE_FILE.exists():
    existing_updates = _read_json_file(USAGE_FILE, {}).get("updates", [])

known_versions: set[tuple] = {(u["fromV"], u["toV"]) for u in existing_updates}
collected_versions: set[tuple] = set(known_versions)
highest_known_toV: int = max((u["toV"] for u in existing_updates), default=-1)

# ── 2. Fetch new updates from the API until we overlap with known ones ────────
print("Fetching update list from Overleaf…")
new_updates: list = []
params: dict = {}
seen_page_boundaries: set[int] = set()
pages_fetched = 0

while True:
    pages_fetched += 1
    if pages_fetched > MAX_UPDATE_PAGES:
        print("ERROR: Overleaf update pagination did not finish.")
        raise SystemExit(1)

    url = f"{BASE}/project/{PROJECT}/updates"
    try:
        page = _get_json(
            url,
            params=params,
            context="fetching the update list",
            attempts=UPDATE_ATTEMPTS,
        ).get("updates", [])
    except RuntimeError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)
    if not page:
        break

    page_added = 0
    for u in page:
        version = (u["fromV"], u["toV"])
        if version not in collected_versions:
            new_updates.append(u)
            collected_versions.add(version)
            page_added += 1

    oldest_toV_on_page = min(u["toV"] for u in page)
    if oldest_toV_on_page <= highest_known_toV:
        break
    if page_added == 0:
        break
    if oldest_toV_on_page in seen_page_boundaries:
        print("  Overleaf returned an overlapping update page; stopping pagination.")
        break

    seen_page_boundaries.add(oldest_toV_on_page)
    params = {"before": oldest_toV_on_page}
    time.sleep(0.2)

print(f"  {len(new_updates)} new update(s) found.")

# ── 3. Merge and persist usage.json ──────────────────────────────────────────
if new_updates:
    merged = new_updates + existing_updates
    _write_json_file(USAGE_FILE, {"updates": merged}, indent="\t")
    all_updates = merged
else:
    all_updates = existing_updates

if not USAGE_FILE.exists():
    _write_json_file(USAGE_FILE, {"updates": all_updates}, indent="\t")

# ── 4. Load diff cache ────────────────────────────────────────────────────────
cache: dict = _read_json_file(CACHE, {}) if CACHE.exists() else {}
if not CACHE.exists():
    _write_json_file(CACHE, cache)

# ── 5. Build job list and fetch only missing diffs ────────────────────────────
jobs = [
    (u["fromV"], u["toV"], path)
    for u in all_updates
    for path in u.get("pathnames", [])
]

total = len(jobs)
fetched = skipped = errors = 0
failed_jobs = []

for i, (fv, tv, path) in enumerate(jobs):
    key = f"{fv}:{tv}:{path}"
    if key in cache:
        skipped += 1
        continue

    url = (f"{BASE}/project/{PROJECT}/diff"
           f"?from={fv}&to={tv}&pathname={urllib.parse.quote(path)}")
    try:
        cache[key] = _get_json(
            url,
            context=f"fetching diff {fv}->{tv} {path}",
            attempts=DIFF_ATTEMPTS,
        )
        fetched += 1
        print(f"[{i+1}/{total}] {fv}->{tv} {path}")
    except RuntimeError as e:
        print(f"[{i+1}/{total}] WARNING {fv}->{tv} {path}: {e}")
        failed_jobs.append(f"{fv}->{tv} {path}")
        errors += 1

    _write_json_file(CACHE, cache)
    time.sleep(0.25)

empty_message = None
if total == 0:
    empty_message = (
        "No file diffs to fetch."
        if all_updates
        else "No Overleaf updates found yet."
    )
    print(f"\nDone. {empty_message}")
else:
    print(f"\nDone. fetched={fetched}, skipped={skipped}, errors={errors}")
print(f"Cache entries: {len(cache)}")
if errors:
    warning_summary = (
        f"Completed with {errors} diff request(s) not fetched. "
        "Run Fetch Updates again to retry missing diffs."
    )
    print("Missing diffs:")
    for job in failed_jobs:
        print(f"  {job}")
    print(warning_summary)
if empty_message:
    print(empty_message)
