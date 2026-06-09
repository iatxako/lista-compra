#!/usr/bin/env python3
"""Servidor web para la lista de la compra.

Endpoints:
  GET  /              -> HTML de la lista
  GET  /api/list      -> JSON de items
  POST /api/check     -> {"name": "...", "checked": bool}
  POST /api/add       -> {"name": "..."}
  POST /api/sync      -> sincroniza checks a Notion

Puerto: 8767 (evita conflicto con VNC :8765 y screenshot :8766)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DATA_DIR, "data.json")
HTML_FILE = os.path.join(DATA_DIR, "index.html")
PORT = 8767

# ── Load / Save data ──────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"items": [], "updated": None}

def save_data(data):
    data["updated"] = datetime.now().isoformat()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def refresh_from_notion():
    """Pull latest from Notion and merge with local checked state."""
    data = load_data()
    old_checked = {i["name"]: i.get("checked", False) for i in data.get("items", [])}

    # Read Notion page
    token = None
    env_path = "/opt/data/.env.secret"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "NOTION_API_KEY" in line and "=" in line:
                    token = line.split("=", 1)[1].strip()
                    break

    if not token:
        return False

    import urllib.request
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2025-09-03",
    }

    page_id = "37a13b5cd60a818681dbf9436bb2f339"  # Lista de la compra
    try:
        req = urllib.request.Request(
            f"https://api.notion.com/v1/pages/{page_id}/markdown",
            headers=headers
        )
        with urllib.request.urlopen(req) as resp:
            md = json.loads(resp.read())["markdown"]
    except Exception as e:
        print(f"Error leyendo Notion: {e}")
        return False

    # Parse markdown table: | Item | Añadido | Estado |
    items = []
    for line in md.split("\n"):
        if line.startswith("|") and "🕐" in line or "✅" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                name = parts[1]
                added = parts[2]
                checked = "✅" in parts[3] or old_checked.get(name, False)
                items.append({"name": name, "added": added, "checked": checked})

    if items:
        data["items"] = items
        save_data(data)
        return True
    return False

def sync_to_notion(data):
    """Write checked/unchecked state back to Notion."""
    token = None
    env_path = "/opt/data/.env.secret"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "NOTION_API_KEY" in line and "=" in line:
                    token = line.split("=", 1)[1].strip()
                    break

    if not token:
        return False

    import urllib.request
    _, error = _build_notion_headers_and_page(token)
    if error:
        return False
    return True

def _build_notion_headers_and_page(token):
    """Helper to get Notion headers and current page markdown."""
    import urllib.request
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json",
    }
    page_id = "37a13b5cd60a818681dbf9436bb2f339"
    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}/markdown",
        headers=headers
    )
    try:
        with urllib.request.urlopen(req) as resp:
            current = json.loads(resp.read())["markdown"]
        return headers, current
    except Exception as e:
        return None, str(e)

# ── HTTP Handler ──────────────────────────────────────────────────

class ShoppingListHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_html()
        elif path == "/api/list":
            self._serve_json(load_data())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return

        data = load_data()

        if path == "/api/check":
            name = payload.get("name", "")
            checked = payload.get("checked", False)
            for item in data["items"]:
                if item["name"] == name:
                    item["checked"] = checked
                    break
            save_data(data)
            self._serve_json({"ok": True, "item": {"name": name, "checked": checked}})

        elif path == "/api/add":
            name = payload.get("name", "").strip()
            if name:
                data["items"].append({
                    "name": name,
                    "added": datetime.now().strftime("%d %b"),
                    "checked": False
                })
                save_data(data)
            self._serve_json({"ok": True})

        elif path == "/api/remove":
            name = payload.get("name", "")
            data["items"] = [i for i in data["items"] if i["name"] != name]
            save_data(data)
            self._serve_json({"ok": True})

        elif path == "/api/refresh":
            ok = refresh_from_notion()
            self._serve_json({"ok": ok})

        elif path == "/api/sync":
            self._sync_to_notion(data)

        elif path == "/api/reset":
            data["items"] = []
            save_data(data)
            self._serve_json({"ok": True})

        else:
            self._send(404, {"error": "not found"})

    def _sync_to_notion(self, data):
        """Build markdown table and write back to Notion."""
        today = datetime.now().strftime("%d %b")
        lines = ["## 🛒 Lista de la compra\n", "| Item | Añadido | Estado |"]
        lines.append("|---|---|---|")
        for item in data["items"]:
            status = "✅ Comprado" if item.get("checked") else "🕐 Pendiente"
            lines.append(f"| {item['name']} | {item.get('added', today)} | {status} |")
        lines.append("")
        lines.append("---")
        lines.append("*📌 Lista rodante — cuando compres algo avísame y lo marco.*")
        lines.append("*🕐 Pendiente | ✅ Comprado*")
        markdown = "\n".join(lines)

        token = None
        with open("/opt/data/.env.secret") as f:
            for line in f:
                if "NOTION_API_KEY" in line and "=" in line:
                    token = line.split("=", 1)[1].strip()
                    break

        if not token:
            self._send(500, {"error": "no token"})
            return

        import urllib.request
        headers, current_md = _build_notion_headers_and_page(token)
        if not headers:
            self._send(500, {"error": current_md})
            return

        payload = {
            "type": "replace_content_range",
            "replace_content_range": {
                "content": markdown,
                "content_range": current_md
            }
        }
        page_id = "37a13b5cd60a818681dbf9436bb2f339"
        req = urllib.request.Request(
            f"https://api.notion.com/v1/pages/{page_id}/markdown",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self._serve_json({"ok": True})
        except Exception as e:
            self._send(500, {"error": str(e)})

    # ── Helpers ──────────────────────────────────────────────────

    def _serve_html(self):
        if os.path.exists(HTML_FILE):
            with open(HTML_FILE) as f:
                html = f.read()
            self._send(200, html, content_type="text/html; charset=utf-8")
        else:
            self._send(500, {"error": "index.html not found"})

    def _serve_json(self, data):
        self._send(200, data, content_type="application/json")

    def _send(self, code, content, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

        if isinstance(content, str):
            self.wfile.write(content.encode())
        elif isinstance(content, dict):
            self.wfile.write(json.dumps(content, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self._send(204, "")

    def log_message(self, format, *args):
        pass  # quieter


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Refresh from Notion on start
    print("🔃 Sincronizando desde Notion...")
    refresh_from_notion()

    server = HTTPServer(("0.0.0.0", PORT), ShoppingListHandler)
    print(f"🛒 Lista de la compra activa en http://0.0.0.0:{PORT}")
    print(f"   Accede desde el móvil: http://<nas-ip>:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Apagando servidor")
        server.shutdown()
