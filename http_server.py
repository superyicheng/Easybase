#!/usr/bin/env python3
"""Easybase HTTP API — local server for the browser extension.

Zero dependencies (stdlib only). Runs on localhost.

Usage:
    python3 http_server.py                          # default port 8372
    EASYBASE_PORT=9000 python3 http_server.py       # custom port
    EASYBASE_DIR=/path/to/data python3 http_server.py  # custom data dir

Endpoints:
    GET  /api/load?query=...&top_k=10&scope=...    Context block (text)
    GET  /api/search?query=...&top_k=10&scope=...  Search results (JSON)
    POST /api/add         {id, summary, body, ...}  Create chunk (JSON)
    POST /api/respond     {text}                    Record response (JSON)
    POST /api/index                                 Rebuild search index (JSON)
    POST /api/scan        {paths}                   Scan and import projects (JSON)
    POST /api/permit      {project, type, value}    Record permanent permission (JSON)
    GET  /api/ingest                                Process inbox files (text)
    GET  /api/stats                                 Index statistics (text)
    GET  /api/check                                 System integrity check (text)
    GET  /api/status                                Health check (JSON)
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add this directory to path so we can import ctx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctx

BASE_DIR = os.environ.get("EASYBASE_DIR", os.path.expanduser("~/.easybase"))
PORT = int(os.environ.get("EASYBASE_PORT", "8372"))


class EasybaseHandler(BaseHTTPRequestHandler):

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _text_response(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/api/load":
                query = params.get("query", [""])[0]
                if not query:
                    return self._json_response({"error": "query parameter required"}, 400)
                scope = params.get("scope", [None])[0]
                result = ctx._load_context(query, BASE_DIR, scope=scope)
                self._text_response(result)

            elif path == "/api/search":
                query = params.get("query", [""])[0]
                if not query:
                    return self._json_response({"error": "query parameter required"}, 400)
                scope = params.get("scope", [None])[0]
                results = ctx._search_results(query, BASE_DIR, scope=scope)
                self._json_response({"results": results})

            elif path == "/api/stats":
                result = ctx._get_stats(BASE_DIR)
                self._text_response(result)

            elif path == "/api/ingest":
                result = ctx._ingest_files(BASE_DIR)
                self._text_response(result)

            elif path == "/api/check":
                result = ctx._check_integrity(BASE_DIR)
                self._text_response(result)

            elif path == "/api/status":
                try:
                    index = ctx.load_index(BASE_DIR)
                    self._json_response({
                        "ok": True,
                        "chunks": index["N"],
                    })
                except (ctx.EasybaseError, Exception):
                    self._json_response({"ok": False, "chunks": 0, "error": "No index found"})

            else:
                self._json_response({"error": "Not found"}, 404)

        except ctx.EasybaseError as e:
            self._json_response({"error": str(e)}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self._json_response({"error": "Invalid JSON"}, 400)

        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/add":
                result = ctx._add_chunk(
                    chunk_id=body.get("id", ""),
                    summary=body.get("summary", ""),
                    body=body.get("body", ""),
                    domain=body.get("domain", ""),
                    tags=body.get("tags", ""),
                    depends=body.get("depends", ""),
                    tree_path=body.get("tree_path", ""),
                    base_dir=BASE_DIR,
                )
                self._json_response({"ok": True, "message": result})

            elif parsed.path == "/api/respond":
                text = body.get("text", "")
                result = ctx._record_response(text, BASE_DIR)
                self._json_response({"ok": True, "message": result})

            elif parsed.path == "/api/index":
                result = ctx._rebuild_index(BASE_DIR)
                self._json_response({"ok": True, "message": result})

            elif parsed.path == "/api/scan":
                paths_str = body.get("paths", "")
                path_list = [p.strip() for p in paths_str.split(",") if p.strip()] if paths_str else None
                result = ctx._scan_projects(path_list, BASE_DIR)
                self._json_response({"ok": True, "message": result})

            elif parsed.path == "/api/permit":
                project = body.get("project", "")
                perm_type = body.get("type", "")
                value = body.get("value", "")
                if not project or not perm_type or not value:
                    return self._json_response(
                        {"error": "project, type, and value are required"}, 400)
                result = ctx._add_permission(project, perm_type, value, BASE_DIR)
                self._json_response({"ok": True, "message": result})

            else:
                self._json_response({"error": "Not found"}, 404)

        except ctx.EasybaseError as e:
            self._json_response({"error": str(e)}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def log_message(self, format, *args):
        # Suppress default request logging
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), EasybaseHandler)
    print(f"Easybase HTTP server running at http://127.0.0.1:{PORT}")
    print(f"Data directory: {BASE_DIR}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
