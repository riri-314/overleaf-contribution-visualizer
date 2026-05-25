# Overleaf Contribution Visualizer

Fetches the edit history of an Overleaf project and produces contribution charts
broken down by author — words inserted/deleted, editing patterns, chapter ownership,
and more.

Works with **any** Overleaf instance (self-hosted or overleaf.com).

---

## Requirements

Python 3.10+

```bash
pip install -r requirements.txt
```

---

## Setup

### 1. Copy the example config

```bash
cp config.example.json config.json
```

### 2. Fill in `config.json`

```json
{
  "base_url":   "https://overleaf.example.com",
  "project_id": "YOUR_PROJECT_ID",
  "cookie":     "YOUR_OVERLEAF_SESSION_COOKIE",
  "title":      "My Thesis",
  "users": [
    {"name": "Alice Example", "color": "#4C72B0"},
    {"name": "Bob Example",   "color": "#DD8452"}
  ]
}
```

| Field | Description |
|---|---|
| `base_url` | Root URL of your Overleaf instance |
| `project_id` | The hex ID in your project's URL, e.g. `…/project/69afe042…` |
| `cookie` | Your `overleaf.sid` session cookie (see below) |
| `title` | Label shown in chart titles |
| `users` | *(optional)* List of authors with name and hex color. If omitted, authors are auto-detected from the data and assigned colors automatically. |

> **Security:** `config.json` is listed in `.gitignore` so the cookie is never
> accidentally committed. Alternatively, export `OVERLEAF_COOKIE=<value>` in your
> shell — that takes precedence over the value in the file.

### How to get the session cookie

1. Open your Overleaf project in a browser.
2. Open DevTools → **Application** tab → **Cookies**.
3. Copy the value of the `overleaf.sid` cookie.

> **WARNING: never share this cookie with anyone.**
> It grants full access to your Overleaf account — anyone who has it can read,
> edit, or delete all your projects. Treat it like a password.
> If you accidentally expose it (e.g. in a screenshot or a public repo), log out
> of Overleaf immediately to invalidate it.

---

## Usage

### Step 1 — fetch data (incremental)

```bash
python fetch_diffs.py
```

- Downloads the update list from the Overleaf API and saves it to `usage.json`.
- Downloads per-file diffs and caches them in `diff_cache.json`.
- **Re-running is safe and cheap**: only new updates and missing diffs are fetched.

### Step 2 — generate charts

```bash
python visualize_contributions.py
```

Produces six PNG files:

| File | Content |
|---|---|
| `contributions_overview.png` | Words inserted/deleted, pie share, cumulative curve, weekly bar, session counts |
| `contributions_temporal.png` | Heatmap (hour × weekday), hourly activity, sessions per week/day |
| `contributions_files.png` | Top-20 chapters stacked bar + per-chapter author scatter |
| `contributions_timeline.png` | Dot strip — one dot per edit session over time |
| `contributions_intensity.png` | Daily words-written bar chart with peak annotation |
| `contributions_patterns.png` | Insertions vs. deletions scatter + chapter ownership heatmap |

A text summary is also printed to the terminal.

### Web interface (alternative)

```bash
python app.py
```

Opens a local web dashboard at `http://localhost:5000` that lets you:
- See the tracked project (clickable link to Overleaf)
- See when data was last fetched and how many updates/diffs are cached
- Click **Fetch Updates** to pull only new changes and regenerate charts
- Click **Refetch All** to clear the diff cache and re-download everything
- Browse all six charts in a grid; click any to open it full-size

---

## File overview

```
config.example.json         ← template — copy to config.json
config.json                 ← your settings (gitignored)
app.py                      ← web dashboard (Flask)
templates/index.html        ← web UI
fetch_diffs.py              ← fetch & cache data from Overleaf
visualize_contributions.py  ← generate charts from cached data
usage.json                  ← cached update list (gitignored)
diff_cache.json             ← cached diffs (gitignored)
state.json                  ← last-fetch timestamp (gitignored)
requirements.txt
```

---

## Disclaimer

This code was written by [Claude Code](https://claude.ai/code), Anthropic's AI coding assistant.
