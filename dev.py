"""
Local dev server (Flask) — meniru Vercel routing.
Jalankan: python dev.py
Buka: http://localhost:3000
"""
import importlib.util, os, sys, re, tempfile, mimetypes, time, hashlib, hmac
from flask import Flask, send_file, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_SECRET = os.environ.get("API_SECRET", "changeme-set-in-vercel-env")


def load_module(filepath):
    spec = importlib.util.spec_from_file_location("mod", filepath)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_token():
    now_min = int(time.time() // 60)
    return hmac.new(API_SECRET.encode(), str(now_min).encode(), hashlib.sha256).hexdigest()


def verify_token(token):
    if not token:
        return False
    now_min = int(time.time() // 60)
    for minute in [now_min, now_min - 1]:
        expected = hmac.new(API_SECRET.encode(), str(minute).encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, expected):
            return True
    return False


# Rate limiter
from collections import defaultdict
_rate = defaultdict(list)

def rate_ok(ip, limit=30, window=60):
    now = time.time()
    _rate[ip] = [t for t in _rate[ip] if now - t < window]
    if len(_rate[ip]) >= limit:
        return False
    _rate[ip].append(now)
    return True


def guard():
    """Cek token + rate limit. Return error response atau None jika OK."""
    ip = (request.headers.get("x-forwarded-for") or request.remote_addr or "").split(",")[0].strip()

    if not rate_ok(ip):
        return jsonify({"error": "Too many requests"}), 429

    token = request.headers.get("x-api-token", "")
    if not verify_token(token):
        return jsonify({"error": "Token tidak valid"}), 401

    return None


# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204


# ── /api/token — satu-satunya endpoint tanpa auth ────────────────────────────

@app.route("/api/token", methods=["GET"])
def get_token():
    """Frontend ambil token dulu, lalu pakai untuk request lain."""
    token      = make_token()
    expires_in = 60 - (int(time.time()) % 60)
    return jsonify({"token": token, "expires_in": expires_in})


# ── /api/get-video ────────────────────────────────────────────────────────────

@app.route("/api/get-video", methods=["GET"])
def get_video():
    err = guard()
    if err: return err

    video_id = request.args.get("id", "").strip()
    if not video_id:
        return jsonify({"status": "error", "message": "ID kosong"}), 400

    if "/" in video_id:
        video_id = video_id.strip("/").split("/")[-1].split("?")[0]

    mod  = load_module("api/get-video.py")
    inst = mod.handler.__new__(mod.handler)
    url  = inst._extract(video_id)

    if url:
        return jsonify({"status": "success", "link": url, "id": video_id})
    return jsonify({"status": "error", "message": "Link tidak ditemukan"}), 404


# ── /api/scan ─────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def scan():
    err = guard()
    if err: return err

    data = request.get_json() or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400

    mod    = load_module("api/scan.py")
    videos = mod.extract(url)
    return jsonify({"videos": videos, "count": len(videos)})


# ── /api/formats ──────────────────────────────────────────────────────────────

@app.route("/api/formats", methods=["POST"])
def formats():
    err = guard()
    if err: return err

    data = request.get_json() or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400

    mod                = load_module("api/formats.py")
    title, thumb, fmts = mod.get_formats(url)
    return jsonify({"title": title, "thumb": thumb, "formats": fmts})


# ── /api/download ─────────────────────────────────────────────────────────────

@app.route("/api/download", methods=["POST"])
def download():
    err = guard()
    if err: return err

    data      = request.get_json() or {}
    url       = data.get("url", "").strip()
    format_id = data.get("format_id", "bestvideo+bestaudio/best")
    title     = data.get("title", "video")

    if not url:
        return jsonify({"error": "URL required"}), 400

    try:
        import yt_dlp
    except ImportError:
        return jsonify({"error": "yt-dlp tidak terinstall"}), 500

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
                return jsonify({"error": "Download gagal"}), 500

            filepath   = os.path.join(tmpdir, files[0])
            ext        = os.path.splitext(files[0])[1]
            safe       = re.sub(r'[^\w\s-]', '', title)[:60].strip() or "video"
            fname      = f"{safe}{ext}"
            mime       = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

            with open(filepath, "rb") as f:
                data_bytes = f.read()

            return Response(data_bytes, headers={
                "Content-Type": mime,
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Content-Length": str(len(data_bytes)),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    missing = [f for f in [
        "index.html", "api/get-video.py",
        "api/scan.py", "api/formats.py", "api/download.py"
    ] if not os.path.exists(f)]

    if missing:
        print("❌ File tidak ditemukan:")
        for f in missing: print(f"   - {f}")
        sys.exit(1)

    print(f"\n🚀  Dev server : http://localhost:3000")
    print(f"🔑  API Secret : {API_SECRET[:8]}...")
    print(f"    Set env    : set API_SECRET=secret-kamu (Windows)")
    print(f"                 export API_SECRET=secret-kamu (Linux/Mac)\n")
    app.run(host="0.0.0.0", port=3000, debug=True)