#!/usr/bin/env python3
"""
Lista de la compra — v2 API (Railway-ready)

Endpoints:
  GET  /api/list      -> JSON de items
  POST /api/check     -> {"name": "...", "checked": bool}
  POST /api/add       -> {"name": "..."}
  POST /api/remove    -> {"name": "..."}
  POST /api/reset     -> vacía la lista

Autenticación: X-API-Key header (variable env API_KEY)
Persistencia: Notion API directa (sin disco local)
"""

import os
import json
import logging
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Config ──────────────────────────────────────────────────────────

# Try multiple env var names for flexibility
NOTION_TOKEN = (
    os.environ.get("NOTION_TOKEN")
    or os.environ.get("NOTION_API_KEY")
    or ""
)
NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "37a13b5cd60a818681dbf9436bb2f339")
API_KEY = os.environ.get("API_KEY", "")
PORT = int(os.environ.get("PORT", 8767))
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

NOTION_VERSION = "2025-09-03"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
log = logging.getLogger("lista-compra")


# ── Auth decorator ──────────────────────────────────────────────────

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if API_KEY and key != API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Notion helpers ──────────────────────────────────────────────────

def notion_get(endpoint):
    """GET from Notion API."""
    url = f"https://api.notion.com/v1/{endpoint.lstrip('/')}"
    resp = requests.get(url, headers=NOTION_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def notion_patch(endpoint, payload):
    """PATCH to Notion API."""
    url = f"https://api.notion.com/v1/{endpoint.lstrip('/')}"
    resp = requests.patch(url, json=payload, headers=NOTION_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_markdown():
    """Get current page markdown from Notion."""
    try:
        data = notion_get(f"pages/{NOTION_PAGE_ID}/markdown")
        return data.get("markdown", ""), None
    except Exception as e:
        log.error("Error fetching Notion page: %s", e)
        return None, str(e)


def parse_items_from_markdown(md):
    """Parse markdown table into item list."""
    items = []
    for line in md.split("\n"):
        if line.startswith("|") and ("🕐" in line or "✅" in line):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                name = parts[1]
                added = parts[2]
                checked = "✅" in parts[3]
                items.append({"name": name, "added": added, "checked": checked})
    return items


def build_markdown_table(items):
    """Build markdown table from item list."""
    today = datetime.now().strftime("%d %b")
    lines = [
        "## 🛒 Lista de la compra\n",
        "| Item | Añadido | Estado |",
        "|---|---|---|",
    ]
    for item in items:
        status = "✅ Comprado" if item.get("checked") else "🕐 Pendiente"
        lines.append(f"| {item['name']} | {item.get('added', today)} | {status} |")
    lines.append("")
    lines.append("---")
    lines.append("*📌 Lista rodante — cuando compres algo avísame y lo marco.*")
    lines.append("*🕐 Pendiente | ✅ Comprado*")
    return "\n".join(lines)


def load_items():
    """Load items directly from Notion (no cache)."""
    md, err = fetch_markdown()
    if err:
        log.warning("Falling back to empty list: %s", err)
        return []
    return parse_items_from_markdown(md)


def save_items(items):
    """Write items back to Notion."""
    md, err = fetch_markdown()
    if err:
        return False, err
    new_md = build_markdown_table(items)
    payload = {
        "type": "replace_content_range",
        "replace_content_range": {
            "content": new_md,
            "content_range": md,
        },
    }
    try:
        notion_patch(f"pages/{NOTION_PAGE_ID}/markdown", payload)
        return True, None
    except Exception as e:
        log.error("Error saving to Notion: %s", e)
        return False, str(e)


# ── API Routes ──────────────────────────────────────────────────────

@app.route("/api/list")
def api_list():
    items = load_items()
    return jsonify({"items": items, "updated": datetime.now().isoformat()})


@app.route("/api/check", methods=["POST"])
@require_api_key
def api_check():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    checked = body.get("checked", False)

    items = load_items()
    for item in items:
        if item["name"] == name:
            item["checked"] = checked
            break

    ok, err = save_items(items)
    if not ok:
        return jsonify({"error": err}), 500
    return jsonify({"ok": True, "item": {"name": name, "checked": checked}})


@app.route("/api/add", methods=["POST"])
@require_api_key
def api_add():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    items = load_items()
    # Avoid duplicates
    if any(i["name"].lower() == name.lower() for i in items):
        return jsonify({"ok": True, "duplicate": True})

    items.append({
        "name": name,
        "added": datetime.now().strftime("%d %b"),
        "checked": False,
    })

    ok, err = save_items(items)
    if not ok:
        return jsonify({"error": err}), 500
    return jsonify({"ok": True})


@app.route("/api/remove", methods=["POST"])
@require_api_key
def api_remove():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")

    items = load_items()
    items = [i for i in items if i["name"] != name]

    ok, err = save_items(items)
    if not ok:
        return jsonify({"error": err}), 500
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
@require_api_key
def api_reset():
    ok, err = save_items([])
    if not ok:
        return jsonify({"error": err}), 500
    return jsonify({"ok": True})


# ── Serve frontend ──────────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    return send_from_directory(BASE_DIR, "index.html")


# ── Health check ────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "lista-compra-v2"})


# ── Debug (solo si DEBUG=true) ───────────────────────────────────────

@app.route("/api/debug")
def api_debug():
    if not DEBUG:
        return jsonify({"error": "debug disabled"}), 404
    token = NOTION_TOKEN or "(empty)"
    return jsonify({
        "env": {
            "NOTION_TOKEN": token[:8] + "..." if token != "(empty)" else "(empty)",
            "NOTION_TOKEN_LEN": len(NOTION_TOKEN),
            "NOTION_PAGE_ID": NOTION_PAGE_ID,
            "DEBUG": DEBUG,
        },
        "notion_test": _test_notion_connection(),
    })

def _test_notion_connection():
    if not NOTION_TOKEN:
        return "no token configured"
    try:
        resp = requests.get(
            f"https://api.notion.com/v1/pages/{NOTION_PAGE_ID}",
            headers=NOTION_HEADERS,
            timeout=10,
        )
        return f"HTTP {resp.status_code}"
    except Exception as e:
        return f"error: {e}"


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not NOTION_TOKEN:
        log.warning("NOTION_TOKEN not set — API will return empty lists")
    if not API_KEY:
        log.warning("API_KEY not set — endpoints are unprotected")
    log.info("Starting on port %d (debug=%s)", PORT, DEBUG)
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
