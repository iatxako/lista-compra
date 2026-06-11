#!/usr/bin/env python3
"""
Lista de la compra — v3 API (Railway + Postgres)

Endpoints:
  GET    /api/list                  -> JSON de items activos
  POST   /api/check                 -> {"name": "...", "checked": bool}
  POST   /api/add                   -> {"name": "...", "category"?: "..."}
  POST   /api/remove                -> {"name": "..."}
  POST   /api/category              -> {"name": "...", "category": "..."}
  POST   /api/reset                 -> vacía la lista + guarda snapshot en history
  GET    /api/history               -> últimos 10 snapshots
  GET    /api/history/<id>          -> detalle de snapshot (items_json)
  POST   /api/history/<id>/receipt  -> sube ticket, extrae datos con Groq vision
  GET    /api/suggestions           -> sugerencias del catálogo
  GET    /api/stream                -> SSE para sync en tiempo real
  GET    /health                    -> health check

Autenticación: cookie HMAC-SHA256 (httponly) + X-API-Key header fallback
Persistencia: Postgres (DATABASE_URL)
"""

import os
import base64
import json
import logging
import queue
import threading
import time
import hmac
import hashlib
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context, make_response

# ── Config ──────────────────────────────────────────────────────────

def _resolve_database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "").strip()
    # Handle accidental "DATABASE_URL = postgresql://..." format (env file line pasted as value)
    if raw.upper().startswith("DATABASE_URL"):
        rest = raw[len("DATABASE_URL"):].lstrip(" \t=")
        if rest.startswith("postgresql://") or rest.startswith("postgres://"):
            raw = rest
    # Railway provides postgres:// but psycopg2/libpq requires postgresql://
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw:
        return raw
    # Fallback: build from individual PG* env vars
    pg_host = os.environ.get("PGHOST")
    pg_port = os.environ.get("PGPORT")
    pg_user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER")
    pg_pass = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    pg_db = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB")
    if all([pg_host, pg_port, pg_user, pg_pass, pg_db]):
        return f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    return ""

DATABASE_URL = _resolve_database_url()

API_KEY = os.environ.get("API_KEY", "")
PORT = int(os.environ.get("PORT", 8767))
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS catalog (
                name TEXT PRIMARY KEY,
                times_added INTEGER NOT NULL DEFAULT 0,
                times_purchased INTEGER NOT NULL DEFAULT 0,
                last_added_at TIMESTAMP,
                last_purchased_at TIMESTAMP,
                avg_interval_days DOUBLE PRECISION
            )
        """)
        cur.execute("ALTER TABLE catalog ADD COLUMN IF NOT EXISTS category TEXT DEFAULT NULL")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                saved_at TIMESTAMP DEFAULT NOW(),
                item_count INTEGER NOT NULL,
                checked_count INTEGER NOT NULL,
                items_json JSONB NOT NULL
            )
        """)
        cur.execute("ALTER TABLE history ADD COLUMN IF NOT EXISTS store_name TEXT DEFAULT NULL")
        cur.execute("ALTER TABLE history ADD COLUMN IF NOT EXISTS total_amount NUMERIC(10,2) DEFAULT NULL")
        cur.execute("ALTER TABLE history ADD COLUMN IF NOT EXISTS receipt_json JSONB DEFAULT NULL")
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
        cur.execute("""
            SELECT i.name, i.added, i.checked, c.category
            FROM items i
            LEFT JOIN catalog c ON c.name = i.name
            ORDER BY i.created_at ASC
        """)
        items = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return items
    except Exception as e:
        log.error("Error loading items: %s", e)
        return []


# ── SSE pub/sub ─────────────────────────────────────────────────────

_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _notify_clients():
    items = load_items()
    payload = "data: " + json.dumps({"items": items, "updated": datetime.now().isoformat()}) + "\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


# ── Auth ────────────────────────────────────────────────────────────

_COOKIE_NAME = "lista_auth"
_COOKIE_PAYLOAD = "lista-auth-v1"

def _make_auth_cookie() -> str:
    sig = hmac.new(API_KEY.encode(), _COOKIE_PAYLOAD.encode(), hashlib.sha256).hexdigest()
    return f"{_COOKIE_PAYLOAD}.{sig}"

def _valid_auth_cookie() -> bool:
    if not API_KEY:
        return True
    cookie = request.cookies.get(_COOKIE_NAME, "")
    expected = _make_auth_cookie()
    return bool(cookie) and hmac.compare_digest(cookie, expected)

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        key = request.headers.get("X-API-Key", "")
        if key == API_KEY or _valid_auth_cookie():
            return f(*args, **kwargs)
        return jsonify({"error": "unauthorized"}), 401
    return decorated


# ── API Routes ──────────────────────────────────────────────────────

@app.route("/api/stream")
def api_stream():
    q: queue.Queue = queue.Queue(maxsize=10)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        # Send current state immediately on connect
        items = load_items()
        yield "data: " + json.dumps({"items": items, "updated": datetime.now().isoformat()}) + "\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/list")
def api_list():
    items = load_items()
    return jsonify({"items": items, "updated": datetime.now().isoformat()})


@app.route("/api/suggestions")
def api_suggestions():
    if not DATABASE_URL:
        return jsonify({"suggestions": []})
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.name, c.times_added
            FROM catalog c
            WHERE c.times_added > 1
              AND NOT EXISTS (SELECT 1 FROM items i WHERE i.name = c.name)
            ORDER BY c.times_added DESC
            LIMIT 5
        """)
        suggestions = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"suggestions": suggestions})
    except Exception as e:
        log.error("Error loading suggestions: %s", e)
        return jsonify({"suggestions": []})


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
        if checked:
            cur.execute("SELECT times_purchased, last_purchased_at, avg_interval_days FROM catalog WHERE name = %s", (name,))
            row = cur.fetchone()
            if row and row["last_purchased_at"]:
                interval = (datetime.now() - row["last_purchased_at"]).total_seconds() / 86400
                prev_avg = row["avg_interval_days"]
                prev_purchases = row["times_purchased"] or 0
                new_avg = interval if prev_avg is None else (prev_avg * prev_purchases + interval) / (prev_purchases + 1)
            else:
                new_avg = None
            cur.execute("""
                INSERT INTO catalog (name, times_purchased, last_purchased_at, avg_interval_days)
                VALUES (%s, 1, NOW(), %s)
                ON CONFLICT (name) DO UPDATE
                    SET times_purchased = catalog.times_purchased + 1,
                        last_purchased_at = NOW(),
                        avg_interval_days = %s
            """, (name, new_avg, new_avg))
        conn.commit()
        cur.close()
        conn.close()
        _notify_clients()
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
        category = body.get("category")
        cur.execute("""
            INSERT INTO catalog (name, times_added, last_added_at, category)
            VALUES (%s, 1, NOW(), %s)
            ON CONFLICT (name) DO UPDATE
                SET times_added = catalog.times_added + 1,
                    last_added_at = NOW(),
                    category = COALESCE(catalog.category, EXCLUDED.category)
        """, (name, category))
        conn.commit()
        cur.close()
        conn.close()
        _notify_clients()
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
        _notify_clients()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error removing item: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/category", methods=["POST"])
@require_api_key
def api_category():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    category = body.get("category")
    if not name:
        return jsonify({"error": "name required"}), 400
    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO catalog (name, times_added, category)
            VALUES (%s, 0, %s)
            ON CONFLICT (name) DO UPDATE SET category = EXCLUDED.category
        """, (name, category))
        conn.commit()
        cur.close()
        conn.close()
        _notify_clients()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error setting category: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
@require_api_key
def api_reset():
    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT i.name, i.checked, c.category
            FROM items i LEFT JOIN catalog c ON c.name = i.name
        """)
        items_snap = [dict(r) for r in cur.fetchall()]
        if items_snap:
            cur.execute(
                "INSERT INTO history (item_count, checked_count, items_json) VALUES (%s, %s, %s::jsonb)",
                (len(items_snap), sum(1 for i in items_snap if i['checked']), json.dumps(items_snap))
            )
            cur.execute("""
                DELETE FROM history WHERE id NOT IN (
                    SELECT id FROM history ORDER BY saved_at DESC LIMIT 10
                )
            """)
        cur.execute("DELETE FROM items")
        conn.commit()
        cur.close()
        conn.close()
        _notify_clients()
        return jsonify({"ok": True})
    except Exception as e:
        log.error("Error resetting: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
@require_api_key
def api_history():
    if not DATABASE_URL:
        return jsonify({"history": []})
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, saved_at, item_count, checked_count, store_name, total_amount FROM history ORDER BY saved_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        for r in rows:
            r["saved_at"] = r["saved_at"].isoformat()
        return jsonify({"history": rows})
    except Exception as e:
        log.error("Error loading history: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<int:history_id>")
@require_api_key
def api_history_detail(history_id):
    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT items_json FROM history WHERE id = %s", (history_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify({"items": row["items_json"]})
    except Exception as e:
        log.error("Error loading history detail: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<int:history_id>/receipt", methods=["POST"])
@require_api_key
def api_receipt(history_id):
    if not DATABASE_URL:
        return jsonify({"error": "no database"}), 500

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not configured"}), 503

    if "receipt" not in request.files:
        return jsonify({"error": "missing file field 'receipt'"}), 400

    img_bytes = request.files["receipt"].read()
    if len(img_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "image too large (max 10MB)"}), 413

    img_b64 = base64.b64encode(img_bytes).decode()
    mime = request.files["receipt"].mimetype or "image/jpeg"
    del img_bytes  # discard immediately

    # Load catalog names to help matching
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, category FROM catalog ORDER BY times_purchased DESC LIMIT 200")
        catalog_names = [f"{r['name']} ({r['category'] or 'sin categoría'})" for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception:
        catalog_names = []

    catalog_hint = ", ".join(catalog_names[:80]) if catalog_names else "sin datos"

    prompt = f"""Eres un asistente que extrae datos estructurados de tickets de compra.
Analiza la imagen del ticket y devuelve SOLO un JSON válido con esta estructura exacta:

{{
  "store_name": "nombre del supermercado o tienda",
  "purchase_date": "YYYY-MM-DD o null si no aparece",
  "total_amount": 12.34,
  "items": [
    {{
      "name_raw": "nombre tal como aparece en el ticket",
      "catalog_match": "nombre del producto del catálogo que mejor coincide, o null",
      "price": 1.23,
      "quantity": 1,
      "unit": "ud/kg/l o null"
    }}
  ],
  "discounts": [{{"description": "...", "amount": 0.50}}],
  "payment_method": "efectivo/tarjeta/null"
}}

Catálogo disponible para matching (nombre — categoría): {catalog_hint}

Reglas:
- Si no puedes leer un campo, ponlo a null
- total_amount debe ser el total final pagado (número, sin símbolo €)
- Para catalog_match, busca la coincidencia más cercana en el catálogo; si no hay, null
- Responde ÚNICAMENTE con el JSON, sin texto adicional"""

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}}
                ]
            }],
            max_tokens=2048,
            temperature=0.1,
        )
        del img_b64  # discard after API call

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        receipt_data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("Groq returned invalid JSON: %s", e)
        return jsonify({"error": "El ticket no pudo ser procesado. Intenta con una foto más nítida."}), 422
    except Exception as e:
        log.error("Error calling Groq: %s", e)
        return jsonify({"error": "Error al procesar el ticket"}), 500

    store_name = receipt_data.get("store_name")
    total_amount = receipt_data.get("total_amount")

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE history
            SET store_name = %s, total_amount = %s, receipt_json = %s::jsonb
            WHERE id = %s
        """, (store_name, total_amount, json.dumps(receipt_data), history_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error("Error saving receipt: %s", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "ok": True,
        "store_name": store_name,
        "total_amount": total_amount,
        "item_count": len(receipt_data.get("items", [])),
    })


# ── Serve frontend ──────────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    resp = make_response(send_from_directory(BASE_DIR, "index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    if API_KEY:
        resp.set_cookie(
            _COOKIE_NAME, _make_auth_cookie(),
            max_age=365 * 24 * 3600,
            httponly=True,
            samesite="Strict",
            secure=request.is_secure,
        )
    return resp

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(BASE_DIR, "manifest.json")

@app.route("/icon-192.png")
def serve_icon_192():
    return send_from_directory(BASE_DIR, "icon-192.png")

@app.route("/icon-512.png")
def serve_icon_512():
    return send_from_directory(BASE_DIR, "icon-512.png")

@app.route("/apple-touch-icon.png")
def serve_apple_icon():
    return send_from_directory(BASE_DIR, "apple-touch-icon.png")


# ── Health check ────────────────────────────────────────────────────


@app.route("/health")
def health():
    db_ok = False
    db_info = "no DATABASE_URL configured"
    if DATABASE_URL:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            db_ok = True
            db_info = "connected"
        except Exception as e:
            db_info = f"connection failed: {str(e)[:120]}"
    return jsonify({
        "status": "ok",
        "service": "lista-compra-v2",
        "database": "connected" if db_ok else "disconnected",
        "db_info": db_info,
    })


# ── Startup ─────────────────────────────────────────────────────────

init_db()
if not DATABASE_URL:
    log.warning("DATABASE_URL not set — API will return empty lists")
if not API_KEY:
    log.warning("API_KEY not set — endpoints are unprotected")

# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting on port %d (debug=%s)", PORT, DEBUG)
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
