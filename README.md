# Overleaf Contribution Visualizer

Analyze an Overleaf project's edit history and see who contributed what over
time. The project includes:

- A Flask web dashboard with interactive Plotly charts
- An optional PNG report generator for static images
- Incremental caching so repeated fetches only download new diffs

It works with overleaf.com and self-hosted Overleaf instances.

## Quick Start

Requirements: Python 3.10+

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "base_url": "https://overleaf.example.com",
  "project_id": "YOUR_PROJECT_ID",
  "cookie": "YOUR_OVERLEAF_SESSION_COOKIE",
  "title": "My Thesis"
}
```

Then start the dashboard:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Click **Fetch Updates** the first time you open the dashboard.

## Config

| Field | Description |
|---|---|
| `base_url` | Root URL of your Overleaf instance, for example `https://www.overleaf.com` |
| `project_id` | The project ID from the Overleaf URL |
| `cookie` | Your `overleaf.sid` session cookie |
| `title` | Project name shown in the dashboard |

You can also provide the cookie through the environment:

```bash
export OVERLEAF_COOKIE="your-cookie-value"
```

`OVERLEAF_COOKIE` takes precedence over the value in `config.json`.

## Getting The Cookie

1. Open your Overleaf project in a browser.
2. Open DevTools.
3. Go to Application, then Cookies.
4. Select your Overleaf domain.
5. Copy the value of the `overleaf.sid` cookie.

Never share this cookie. It grants access to your Overleaf account. If it is
exposed, log out of Overleaf to invalidate it.

## Web Dashboard

Run:

```bash
python app.py
```

The dashboard lets you:

- Fetch only new project updates
- Refetch all diffs if you want to rebuild the cache
- View interactive charts by author, date, session, and chapter
- Toggle authors in chart legends
- Hover, zoom, and pan inside Plotly charts

Charts are grouped into tabs:

| Tab | Charts |
|---|---|
| Overview | Words inserted/deleted, share of words written, cumulative words over time |
| Timeline | Daily writing intensity, session timeline |
| Patterns | Sessions by hour and weekday, sessions per week, insertions vs deletions |
| Chapters | Top chapters, chapter ownership, per-chapter author split |

## Local Network Access

`app.py` listens on `0.0.0.0`, so another device on the same local network can
open the dashboard.

Find this machine's local IP:

```bash
hostname -I
```

Then open this URL from another device on the same Wi-Fi or LAN:

```text
http://YOUR_LOCAL_IP:5000
```

Only do this on a trusted network, because the dashboard can expose project
metadata and contribution data.

## Static PNG Reports

The PNG generator is optional but useful for reports, slides, or sharing static
figures.

First fetch data through either the web dashboard or the CLI:

```bash
python fetch_diffs.py
```

Then generate PNG files:

```bash
python visualize_contributions.py
```

It writes:

- `contributions_overview.png`
- `contributions_temporal.png`
- `contributions_files.png`
- `contributions_timeline.png`
- `contributions_intensity.png`
- `contributions_patterns.png`

The PNG workflow uses `matplotlib` and `seaborn`, so those dependencies are kept
in `requirements.txt`.

## Data Files

These files are generated locally and are ignored by git:

| File | Purpose |
|---|---|
| `config.json` | Your private Overleaf settings and cookie |
| `usage.json` | Cached Overleaf update list |
| `diff_cache.json` | Cached per-file diffs |
| `state.json` | Last successful dashboard fetch time |

## Project Files

| File | Purpose |
|---|---|
| `app.py` | Flask server and API routes |
| `templates/index.html` | Web dashboard UI |
| `data.py` | Parses cached Overleaf data |
| `charts.py` | Builds interactive Plotly charts |
| `fetch_diffs.py` | Fetches update and diff data from Overleaf |
| `visualize_contributions.py` | Generates static PNG reports |
| `config.example.json` | Template for `config.json` |
| `requirements.txt` | Python dependencies |

## Troubleshooting

- No charts: click **Fetch Updates** first, or run `python fetch_diffs.py`.
- Login or permission errors: refresh the `overleaf.sid` cookie in `config.json`.
- Another device cannot connect: check that both devices are on the same network
  and that your firewall allows port `5000`.
- Missing PNG dependencies: run `pip install -r requirements.txt` inside your
  virtual environment.

## Optional: Author Names And Colors

By default, authors are detected from the Overleaf data and colors are assigned
automatically.

If you want stable author order, custom display names, or custom colors, add a
`users` field to `config.json`:

```json
{
  "base_url": "https://overleaf.example.com",
  "project_id": "YOUR_PROJECT_ID",
  "cookie": "YOUR_OVERLEAF_SESSION_COOKIE",
  "title": "My Thesis",
  "users": [
    {"name": "Alice Example", "color": "#4C72B0"},
    {"name": "Bob Example", "color": "#DD8452"}
  ]
}
```

Use the author names exactly as they appear in the fetched Overleaf data. The
order in this list is also used for chart legends and comparisons.
