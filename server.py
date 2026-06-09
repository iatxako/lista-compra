#!/usr/bin/env python3
"""
Lista de la compra — v2 API (Railway + Postgres)

Endpoints:
  GET    /api/list      -> JSON de items
  POST   /api/check     -> {"name": "...", "checked": bool}
  POST   /api/add       -> {"name": "..."}
  POST   /api/remove    -> {"name": "..."}
  POST   /api/reset     -> vacía la lista
  GET    /health        -> health check

Autenticación: X-API-Key header (variable env API_KEY)
Persistencia: Postgres (DATABASE_URL)
"""

import os
import json
import logging
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Config ──────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")
API_KEY = os.environ.get("API_KEY", "")
PORT = int(os.environ.get("PORT", 8767))
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
log = logging.getLogger("lista-compra")


# ── Database ────────────────────────────────────────────────────────

def get_db():
    """Get a Postgres connection."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    """Create table if not exists."""
    if not DATABASE_URL:
        log.warning("DATABASE_URL not set — skipping DB init")
        return
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                added TEXT NOT NULL DEFAULT '',
                checked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        log.info("Database initialized")
    except Exception as e:
        log.error("Database init error: %s", e)


def load_items():
    """Load all items from Postgres."""
    if not DATABASE_URL:
        return []
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, added, checked FROM items ORDER BY created_at ASC")
        items = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return items
    except Exception as e:
        log.error("Error loading items: %s", e)
        return []


# ── Auth decorator ──────────────────────────────────────────────────

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if API_KEY and key != API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


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

    if not DATABASE_URL or not name:
        return jsonify({"error": "missing data"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE items SET checked = %s WHERE name = %s", (checked, name))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True, "item": {"name": name, "checked": checked}})
    except Exception as e:
        log.error("Error checking item: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/add", methods=["POST"])
@require_api_key
def api_add():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500

    today = datetime.now().strftime("%d %b")

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (name, added, checked) VALUES (%s, %s, FALSE) ON CONFLICT (name) DO NOTHING",
            (name, today)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error adding item: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove", methods=["POST"])
@require_api_key
def api_remove():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")

    if not DATABASE_URL or not name:
        return jsonify({"error": "missing data"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE name = %s", (name,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error removing item: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
@require_api_key
def api_reset():
    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM items")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error resetting: %s", e)
        return jsonify({"error": str(e)}), 500


# ── Serve frontend ──────────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    return send_from_directory(BASE_DIR, "index.html")


# ── Health check ────────────────────────────────────────────────────

@app.route("/health")
def health():
    db_ok = False
    if DATABASE_URL:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            db_ok = True
        except:
            pass
    return jsonify({
        "status": "ok",
        "service": "lista-compra-v2",
        "database": "connected" if db_ok else "disconnected",
    })


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    if not DATABASE_URL:
        log.warning("DATABASE_URL not set — API will return empty lists")
    if not API_KEY:
        log.warning("API_KEY not set — endpoints are unprotected")
    log.info("Starting on port %d (debug=%s)", PORT, DEBUG)
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
