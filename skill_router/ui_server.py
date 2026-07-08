"""Локальный веб-дашборд каталога: список, поиск, фильтры (категория/тег/риск/рейтинг), сортировка.

Читает catalog.jsonl из кэш-папки (config). Слушает только 127.0.0.1, проверяет Host
(защита от DNS-rebinding). Browse-only (без добавления скиллов). Запуск: skill-router ui.
"""
import io
import json
import os
import sys
import collections
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import config

PORT = 8765
NUMERIC = {"rating", "stars", "installs", "owners"}
SORT_OK = {"rating", "stars", "installs", "name", "canon", "owners", "risk", "category", "description"}
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}", "localhost", "127.0.0.1"}
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


def _safe_lines(path):
    if not os.path.exists(path):
        return
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def load_data():
    rows = []
    for c in _safe_lines(config.catalog_path()):
        canon = c.get("canon") or ""
        rows.append({
            "name": c.get("name"), "rating": c.get("rating"),
            "stars": c.get("stars"), "installs": c.get("installs"), "canon": canon,
            "url": f"https://github.com/{canon}" if canon else "",
            "owners": c.get("n_owners"), "risk": c.get("risk"),
            "hard_block": bool(c.get("hard_block")), "needs_review": bool(c.get("needs_review")),
            "needs_audit": bool(c.get("needs_audit")),
            "category": c.get("category", "Other"), "group": c.get("group", "Other"),
            "tags": c.get("tags", []), "description": c.get("description") or "",
        })
    return rows


DATA = []
TOP_TAGS = []


def _num(qs, key, default, typ, lo=None, hi=None):
    try:
        v = typ((qs.get(key, [str(default)])[0]) or default)
    except Exception:
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def query(qs):
    q = (qs.get("q", [""])[0] or "").lower().strip()[:120]
    minr = _num(qs, "min_rating", 0, float, 0, 10)
    risk = qs.get("risk", [""])[0]
    category = qs.get("category", [""])[0]
    tag = (qs.get("tag", [""])[0] or "").lower().strip()
    only_clean = qs.get("only_clean", ["0"])[0] == "1"
    sort = qs.get("sort", ["rating"])[0]
    sort = sort if sort in SORT_OK else "rating"
    order = "asc" if qs.get("order", ["desc"])[0] == "asc" else "desc"
    limit = _num(qs, "limit", 100, int, 1, 500)
    offset = _num(qs, "offset", 0, int, 0)

    res = DATA
    if q:
        res = [r for r in res if q in (r.get("name") or "").lower()
               or q in (r.get("canon") or "").lower() or q in (r.get("description") or "").lower()]
    if minr > 0:
        res = [r for r in res if (r.get("rating") or 0) >= minr]
    if risk in ("none", "low", "medium", "high"):
        res = [r for r in res if r.get("risk") == risk]
    if category:
        res = [r for r in res if r.get("category") == category]
    if tag:
        res = [r for r in res if tag in [t.lower() for t in (r.get("tags") or [])]]
    if only_clean:
        res = [r for r in res if not r.get("hard_block")]
    total = len(res)

    present = [r for r in res if r.get(sort) is not None]
    missing = [r for r in res if r.get(sort) is None]
    present.sort(key=lambda r: ((r.get("stars") or 0), (r.get("installs") or 0)), reverse=True)
    if sort in NUMERIC:
        present.sort(key=lambda r: r.get(sort) if isinstance(r.get(sort), (int, float)) else 0,
                     reverse=(order == "desc"))
    else:
        present.sort(key=lambda r: (r.get(sort) or "").lower() if isinstance(r.get(sort), str) else "",
                     reverse=(order == "desc"))
    res = present + missing
    return {"total": total, "shown": min(limit, max(0, total - offset)),
            "rows": res[offset:offset + limit]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local(self):
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local():
            self._send(403, {"error": "forbidden host"}); return
        u = urlparse(self.path)
        if u.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon"); return
        if u.path in ("/", "/index.html"):
            try:
                html = io.open(os.path.join(UI_DIR, "index.html"), "rb").read()
                self._send(200, html, "text/html; charset=utf-8")
            except Exception:
                self._send(500, {"error": "ui/index.html not found"})
        elif u.path == "/api/skills":
            self._send(200, query(parse_qs(u.query)))
        elif u.path == "/api/tags":
            self._send(200, TOP_TAGS)
        else:
            self._send(404, {"error": "not found"})


def serve(open_browser=True):
    global DATA, TOP_TAGS
    if not config.data_ready():
        print("Catalog not found. Run:  skill-router update", file=sys.stderr)
        return 1
    DATA = load_data()
    TOP_TAGS = [t for t, _ in collections.Counter(
        tg for r in DATA for tg in (r.get("tags") or [])).most_common(300)]
    print(f"loaded {len(DATA)} skills")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    url = f"http://localhost:{PORT}"
    print(f"catalog UI: {url}   (Ctrl+C to stop)")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
