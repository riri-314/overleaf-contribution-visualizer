"""Load and parse Overleaf cached data into analysis-ready dataframes."""
import json, re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
]


def _count_words(text: str) -> int:
    t = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", text)
    t = re.sub(r"\\[a-zA-Z]+", " ", t)
    t = re.sub(r"[{}]", " ", t)
    return len(t.split())


def short_name(path: str) -> str:
    return (path.replace("LaTeX/chapters/", "")
                .replace("LaTeX/", "")
                .replace(".tex", "")
                .replace(".bib", " (bib)"))


def is_chapter(path: str) -> bool:
    if not path.endswith(".tex"):
        return False
    if "chapters/" in path:
        return True

    filename = Path(path).name.lower()
    excluded_names = {
        "main.tex",
        "preamble.tex",
        "macros.tex",
        "commands.tex",
        "packages.tex",
        "settings.tex",
    }
    excluded_fragments = ("cover", "template", "titlepage")
    return (
        filename not in excluded_names
        and not any(fragment in filename for fragment in excluded_fragments)
    )


def _hex_to_rgba(hex_color: str, alpha: float = 0.12) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _user_id(user: dict) -> str:
    return str(user.get("id") or _user_name(user))


def _user_name(user: dict) -> str:
    parts = [str(user.get("first_name", "")).strip(),
             str(user.get("last_name", "")).strip()]
    name = " ".join(part for part in parts if part)
    return name or str(user.get("email") or user.get("id") or "Unknown user")


def load_data(config_file: Path, usage_file: Path, cache_file: Path) -> dict | None:
    """Return parsed dataframes and author metadata, or None if data is missing."""
    if not usage_file.exists() or not cache_file.exists():
        return None

    cfg     = json.loads(config_file.read_text())
    updates = json.loads(usage_file.read_text()).get("updates", [])
    cache   = json.loads(cache_file.read_text())

    if not updates:
        return None

    # ── Resolve authors ───────────────────────────────────────────────────────
    cfg_users   = cfg.get("users", [])
    if cfg_users:
        user_labels = [u["name"] for u in cfg_users]
        colors      = {u["name"]: u["color"] for u in cfg_users}
    else:
        seen: dict[str, str] = {}
        for u in updates:
            for usr in u["meta"]["users"]:
                seen.setdefault(_user_id(usr), _user_name(usr))
        user_labels = list(seen.values())
        colors      = {name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(user_labels)}

    # ── Per-file-per-session dataframe ────────────────────────────────────────
    rows = []
    for u in updates:
        start = datetime.fromtimestamp(u["meta"]["start_ts"] / 1000)
        end   = datetime.fromtimestamp(u["meta"]["end_ts"]   / 1000)
        session_users = {_user_id(usr): _user_name(usr)
                         for usr in u["meta"]["users"]}

        for path in u.get("pathnames", []):
            key       = f"{u['fromV']}:{u['toV']}:{path}"
            diff_data = cache.get(key, {}).get("diff", [])

            words_ins: dict[str, int] = defaultdict(int)
            words_del: dict[str, int] = defaultdict(int)

            for chunk in diff_data:
                if "i" in chunk:
                    chunk_users = {_user_id(usr): _user_name(usr)
                                   for usr in chunk["meta"]["users"]}
                    w = _count_words(chunk["i"])
                    for uname in chunk_users.values():
                        words_ins[uname] += w
                elif "d" in chunk:
                    chunk_users = {_user_id(usr): _user_name(usr)
                                   for usr in chunk["meta"]["users"]}
                    w = _count_words(chunk["d"])
                    for uname in chunk_users.values():
                        words_del[uname] += w

            all_contributors = set(words_ins) | set(words_del) | set(session_users.values())
            for name in all_contributors:
                rows.append({
                    "name":      name,
                    "file":      short_name(path),
                    "chapter":   is_chapter(path),
                    "start":     start,
                    "end":       end,
                    "words_ins": words_ins.get(name, 0),
                    "words_del": words_del.get(name, 0),
                })

    df = pd.DataFrame(rows)
    df["day"]     = df["start"].dt.floor("D")
    df["week"]    = df["start"].dt.to_period("W").apply(lambda p: p.start_time)
    df["weekday"] = df["start"].dt.day_name()
    df["hour"]    = df["start"].dt.hour
    df["net"]     = df["words_ins"] - df["words_del"]

    # ── Session-level dataframe ───────────────────────────────────────────────
    srows = []
    rng = np.random.default_rng(42)
    for u in updates:
        start = datetime.fromtimestamp(u["meta"]["start_ts"] / 1000)
        end   = datetime.fromtimestamp(u["meta"]["end_ts"]   / 1000)
        for usr in u["meta"]["users"]:
            srows.append({
                "name":  _user_name(usr),
                "start": start,
                "end":   end,
            })

    sdf = pd.DataFrame(srows)
    sdf["day"]     = sdf["start"].dt.floor("D")
    sdf["week"]    = sdf["start"].dt.to_period("W").apply(lambda p: p.start_time)
    sdf["weekday"] = sdf["start"].dt.day_name()
    sdf["hour"]    = sdf["start"].dt.hour
    # stable per-author jitter for the timeline strip
    sdf["jitter"]  = rng.uniform(-0.3, 0.3, size=len(sdf))

    return {
        "df":          df,
        "sdf":         sdf,
        "user_labels": user_labels,
        "colors":      colors,
        "colors_rgba": {n: _hex_to_rgba(c) for n, c in colors.items()},
        "title":       cfg.get("title", "Overleaf Project"),
    }
