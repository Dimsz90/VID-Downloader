"""
Local dev server — python dev.py → http://localhost:3000
"""
import importlib.util, os, sys, re, tempfile, mimetypes
from flask import Flask, send_file, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


def load(path):
    spec = importlib.util.spec_from_file_location("mod", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204


# ── /api/token ────────────────────────────────────────────────────────────────

@app.route("/api/token")
def token():
    import time, hashlib, hmac, os
    secret     = os.environ.get("API_SECRET","changeme")
    now_min    = int(time.time()//60)
    tok        = hmac.new(secret.encode(), str(now_min).encode(), hashlib.sha256).hexdigest()
    expires_in = 60 - (int(time.time())%60)
    return jsonify({"token": tok, "expires_in": expires_in})


# ── /api/debug ────────────────────────────────────────────────────────────────

@app.route("/api/debug")
def debug():
    results = {"python": sys.version, "env": "local"}
    for pkg in ["requests","bs4","yt_dlp","playwright"]:
        try:
            mod = __import__(pkg)
            results[pkg] = f"OK ({getattr(mod,'__version__','?')})"
        except ImportError as e:
            results[pkg] = f"MISSING: {e}"
    return jsonify(results)


# ── /api/get-video ────────────────────────────────────────────────────────────

@app.route("/api/get-video")
def get_video():
    video_id = request.args.get("id","").strip()
    if not video_id:
        return jsonify({"status":"error","message":"ID kosong"}), 400
    if "/" in video_id:
        video_id = video_id.strip("/").split("/")[-1].split("?")[0]
    mod  = load("api/get-video.py")
    inst = mod.handler.__new__(mod.handler)
    url  = inst._extract(video_id)
    if url:
        return jsonify({"status":"success","link":url,"id":video_id})
    return jsonify({"status":"error","message":"Tidak ditemukan"}), 404


# ── /api/scan ─────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.get_json() or {}
    url  = data.get("url","").strip()
    if not url:
        return jsonify({"error":"URL required"}), 400
    mod    = load("api/scan.py")
    videos = mod.extract(url)
    return jsonify({"videos":videos,"count":len(videos)})


# ── /api/formats ──────────────────────────────────────────────────────────────

@app.route("/api/formats", methods=["POST"])
def formats():
    data = request.get_json() or {}
    url  = data.get("url","").strip()
    if not url:
        return jsonify({"error":"URL required"}), 400
    mod            = load("api/formats.py")
    title,thumb,fmts = mod.get_formats(url)
    return jsonify({"title":title,"thumb":thumb,"formats":fmts})


# ── /api/download ─────────────────────────────────────────────────────────────

@app.route("/api/download", methods=["POST"])
def download():
    data      = request.get_json() or {}
    url       = data.get("url","").strip()
    format_id = data.get("format_id","bestvideo+bestaudio/best")
    title     = data.get("title","video")
    if not url:
        return jsonify({"error":"URL required"}), 400
    try:
        import yt_dlp
    except ImportError:
        return jsonify({"error":"yt-dlp tidak terinstall"}), 500

    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {"format":format_id,
                "outtmpl":os.path.join(tmpdir,"%(title)s.%(ext)s"),
                "quiet":True,"merge_output_format":"mp4"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            files = os.listdir(tmpdir)
            if not files:
                return jsonify({"error":"Download gagal"}), 500
            filepath = os.path.join(tmpdir, files[0])
            ext      = os.path.splitext(files[0])[1]
            safe     = re.sub(r'[^\w\s-]','',title)[:60].strip() or "video"
            fname    = f"{safe}{ext}"
            mime     = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
            with open(filepath,"rb") as f:
                data_bytes = f.read()
            return Response(data_bytes, headers={
                "Content-Type":        mime,
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Content-Length":      str(len(data_bytes)),
            })
        except Exception as e:
            return jsonify({"error":str(e)}), 500


# ── /api/imdb ─────────────────────────────────────────────────────────────────

@app.route("/api/imdb")
def imdb():
    raw_id = request.args.get("id","").strip()
    action = request.args.get("action","info").strip()
    if not raw_id:
        return jsonify({"error":"Parameter ?id= diperlukan"}), 400
    mod     = load("api/imdb.py")
    imdb_id = mod.extract_imdb_id(raw_id)
    if not imdb_id:
        return jsonify({"error":f"IMDB ID tidak valid: {raw_id}"}), 400
    try:
        info = mod.get_movie_info(imdb_id)
        if action == "stream":
            media_type         = "tv" if info.get("type") == "series" else "movie"
            info["stream_url"] = mod.extract_stream_url(imdb_id, media_type)
        return jsonify({"status":"success",**info})
    except Exception as e:
        return jsonify({"error":str(e)}), 500


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    missing = [f for f in ["index.html","api/get-video.py","api/scan.py",
                            "api/formats.py","api/download.py","api/imdb.py"]
               if not os.path.exists(f)]
    if missing:
        print("❌ File tidak ada:")
        for f in missing: print(f"   {f}")
        sys.exit(1)

    print("\n🚀  http://localhost:3000\n")
    app.run(host="0.0.0.0", port=3000, debug=True)