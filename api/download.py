from http.server import BaseHTTPRequestHandler
import json, re, os, tempfile, mimetypes

# ── Auth ──
import os, time, hashlib, hmac
from collections import defaultdict

API_SECRET  = os.environ.get("API_SECRET", "changeme-set-in-vercel-env")
_rate_store = defaultdict(list)

def _make_token():
    now_min = int(time.time() // 60)
    return hmac.new(API_SECRET.encode(), str(now_min).encode(), hashlib.sha256).hexdigest()

def _verify_token(token):
    if not token: return False
    now_min = int(time.time() // 60)
    for m in [now_min, now_min - 1]:
        exp = hmac.new(API_SECRET.encode(), str(m).encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, exp): return True
    return False

def _get_ip(handler):
    for h in ["x-forwarded-for", "x-real-ip", "cf-connecting-ip"]:
        v = handler.headers.get(h)
        if v: return v.split(",")[0].strip()
    return handler.client_address[0]

def _rate_ok(ip, limit=30, window=60):
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < window]
    if len(_rate_store[ip]) >= limit: return False
    _rate_store[ip].append(now)
    return True

def guard(handler):
    ip = _get_ip(handler)
    if not _rate_ok(ip):
        _err(handler, 429, "Too many requests"); return False
    token = handler.headers.get("x-api-token", "")
    if not _verify_token(token):
        _err(handler, 401, "Token tidak valid"); return False
    return True

def _err(handler, code, msg):
    import json
    body = json.dumps({"error": msg}).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)



try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        if not guard(self): return
        length    = int(self.headers.get("Content-Length", 0))
        body      = json.loads(self.rfile.read(length) or b"{}")
        url       = body.get("url", "").strip()
        format_id = body.get("format_id", "bestvideo+bestaudio/best")
        title     = body.get("title", "video")

        if not url:
            return self.send_json({"error": "URL required"}, 400)

        if not yt_dlp:
            return self.send_json({"error": "yt-dlp tidak terinstall"}, 500)

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": format_id,
                "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
                "quiet": True,
                "merge_output_format": "mp4",
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                files = os.listdir(tmpdir)
                if not files:
                    return self.send_json({"error": "Download gagal"}, 500)

                filepath = os.path.join(tmpdir, files[0])
                ext      = os.path.splitext(files[0])[1]
                safe     = re.sub(r'[^\w\s-]', '', title)[:60].strip() or "video"
                fname    = f"{safe}{ext}"
                mime     = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

                with open(filepath, "rb") as f:
                    data = f.read()

                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            except Exception as e:
                self.send_json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass