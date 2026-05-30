"""Flask web interface for the Overleaf contribution visualizer."""
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CONFIG_FILE = Path("config.json")
CACHE_FILE  = Path("diff_cache.json")
USAGE_FILE  = Path("usage.json")
STATE_FILE  = Path("state.json")

_task = {"running": False, "message": "", "error": None}
_lock = threading.Lock()


def load_config():
    if not CONFIG_FILE.exists():
        raise RuntimeError(
            "config.json not found. Copy config.example.json to config.json "
            "and fill in your Overleaf settings."
        )

    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"config.json is not valid JSON: {e}") from e

    missing = [key for key in ("base_url", "project_id") if not cfg.get(key)]
    if missing:
        raise RuntimeError(f"config.json is missing: {', '.join(missing)}")

    cookie = os.environ.get("OVERLEAF_COOKIE") or cfg.get("cookie")
    if not cookie or cookie == "YOUR_OVERLEAF_SESSION_COOKIE":
        raise RuntimeError(
            "No Overleaf session cookie configured. Add overleaf.sid to "
            "config.json or set OVERLEAF_COOKIE."
        )

    return cfg


def load_state():
    return load_json_file(STATE_FILE, {})


def save_state(s):
    write_json_file(STATE_FILE, s)


def load_json_file(path: Path, default):
    if not path.exists():
        return default

    try:
        text = path.read_text()
        if not text.strip():
            return default
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Could not parse %s while reading status: %s", path, e)
        return default


def write_json_file(path: Path, data):
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data))
    temp.replace(path)


def _set_task(**updates):
    with _lock:
        _task.update(**updates)


def _start_fetch_task(clear_cache: bool):
    with _lock:
        if _task["running"]:
            logger.info("Fetch request rejected because a task is already running")
            return jsonify({"error": "A task is already running"}), 409
        _task.update(running=True, message="Fetching data...", error=None)

    logger.info("Fetch request accepted (clear_cache=%s)", clear_cache)
    threading.Thread(target=_run, kwargs={"clear_cache": clear_cache}, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/")
def index():
    logger.info("Serving dashboard")
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with _lock:
        task = dict(_task)

    try:
        cfg = load_config()
        error = None
    except RuntimeError as e:
        logger.warning("Configuration problem: %s", e)
        cfg = {"title": "Configuration required", "base_url": "", "project_id": ""}
        error = str(e)

    state = load_state()
    cache_entries = len(load_json_file(CACHE_FILE, {}))
    update_count = len(load_json_file(USAGE_FILE, {}).get("updates", []))

    return jsonify({
        "project": {
            "title": cfg.get("title", "Overleaf Project"),
            "url":   (
                f"{cfg['base_url'].rstrip('/')}/project/{cfg['project_id']}"
                if cfg.get("base_url") and cfg.get("project_id")
                else "#"
            ),
        },
        "last_fetch":    state.get("last_fetch"),
        "cache_entries": cache_entries,
        "update_count":  update_count,
        "task":          task,
        "error":         error,
    })


@app.route("/api/charts")
def api_charts():
    from data import load_data
    from charts import build_all_charts
    logger.info("Building charts from cached data")
    try:
        data = load_data(CONFIG_FILE, USAGE_FILE, CACHE_FILE)
    except Exception as e:
        logger.exception("Chart data failed to load")
        return jsonify({"error": f"Could not load chart data: {e}"}), 500
    if data is None:
        logger.info("No cached chart data available yet")
        return jsonify({})
    logger.info(
        "Loaded chart data: %s file/session row(s), %s timeline row(s)",
        len(data["df"]),
        len(data["sdf"]),
    )
    return jsonify(build_all_charts(data))


def _run_fetch_script() -> tuple[int, str, str]:
    logger.info("Starting fetch_diffs.py")
    process = subprocess.Popen(
        [sys.executable, "-u", "fetch_diffs.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    last_line = ""
    last_error_line = ""
    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            last_line = line
            if line.startswith("ERROR") or line.startswith("Traceback"):
                last_error_line = line
            logger.info("fetch_diffs.py: %s", line)
            _set_task(message=line)

    return process.wait(), last_line, last_error_line


def _run(clear_cache: bool):
    logger.info("Background fetch started (clear_cache=%s)", clear_cache)
    try:
        load_config()

        if clear_cache and CACHE_FILE.exists():
            logger.info("Clearing diff cache at %s", CACHE_FILE)
            CACHE_FILE.unlink()
            _set_task(message="Cache cleared - fetching all diffs...")

        returncode, last_line, last_error_line = _run_fetch_script()
        if returncode != 0:
            error = last_error_line or last_line or "fetch_diffs.py failed"
            logger.error("fetch_diffs.py exited with code %s: %s", returncode, error)
            _set_task(running=False, message="", error=error)
            return

        state = load_state()
        state["last_fetch"] = datetime.now().isoformat()
        save_state(state)

        message = last_line or "Done"
        if message == "Cache entries: 0":
            message = "No Overleaf updates found yet."
        logger.info("Background fetch completed: %s", message)
        _set_task(running=False, message=message, error=None)
    except RuntimeError as e:
        logger.warning("Background fetch could not start: %s", e)
        _set_task(running=False, message="", error=str(e))
    except Exception as e:
        logger.exception("Background fetch failed")
        _set_task(running=False, message="", error=str(e))


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    return _start_fetch_task(clear_cache=False)


@app.route("/api/refetch", methods=["POST"])
def api_refetch():
    return _start_fetch_task(clear_cache=True)


if __name__ == "__main__":
    logger.info("Starting dashboard at http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
