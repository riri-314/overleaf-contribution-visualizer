"""Flask web interface for the Overleaf contribution visualizer."""
import json, subprocess, threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, send_file, render_template

app = Flask(__name__)

CONFIG_FILE = Path("config.json")
CACHE_FILE  = Path("diff_cache.json")
USAGE_FILE  = Path("usage.json")
STATE_FILE  = Path("state.json")

_task = {"running": False, "message": "", "error": None}
_lock = threading.Lock()


def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    cfg = json.loads(CONFIG_FILE.read_text())
    state = load_state()
    cache_entries = len(json.loads(CACHE_FILE.read_text())) if CACHE_FILE.exists() else 0
    update_count  = len(json.loads(USAGE_FILE.read_text()).get("updates", [])) if USAGE_FILE.exists() else 0
    charts = sorted(p.name for p in Path(".").glob("contributions_*.png"))

    with _lock:
        task = dict(_task)

    return jsonify({
        "project": {
            "title": cfg.get("title", "Overleaf Project"),
            "url":   f"{cfg['base_url'].rstrip('/')}/project/{cfg['project_id']}",
        },
        "last_fetch":    state.get("last_fetch"),
        "cache_entries": cache_entries,
        "update_count":  update_count,
        "task":          task,
        "charts":        charts,
    })


def _run(clear_cache: bool):
    with _lock:
        _task.update(running=True, message="Fetching data…", error=None)
    try:
        if clear_cache and CACHE_FILE.exists():
            CACHE_FILE.unlink()
            with _lock:
                _task["message"] = "Cache cleared — fetching all diffs…"

        r = subprocess.run(["python3", "fetch_diffs.py"], capture_output=True, text=True)
        if r.returncode != 0:
            with _lock:
                _task.update(running=False, message="", error=r.stderr or "fetch_diffs.py failed")
            return

        state = load_state()
        state["last_fetch"] = datetime.now().isoformat()
        save_state(state)

        with _lock:
            _task["message"] = "Generating charts…"

        r2 = subprocess.run(["python3", "visualize_contributions.py"], capture_output=True, text=True)
        last_line = (r.stdout.strip().splitlines() or ["Done"])[-1]
        with _lock:
            _task.update(
                running=False,
                message=last_line,
                error=r2.stderr if r2.returncode != 0 else None,
            )
    except Exception as e:
        with _lock:
            _task.update(running=False, message="", error=str(e))


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    with _lock:
        if _task["running"]:
            return jsonify({"error": "A task is already running"}), 409
    threading.Thread(target=_run, kwargs={"clear_cache": False}, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/refetch", methods=["POST"])
def api_refetch():
    with _lock:
        if _task["running"]:
            return jsonify({"error": "A task is already running"}), 409
    threading.Thread(target=_run, kwargs={"clear_cache": True}, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/charts/<name>")
def chart(name):
    p = Path(name)
    if not name.startswith("contributions_") or not name.endswith(".png") or not p.exists():
        return "", 404
    return send_file(p.resolve(), mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
