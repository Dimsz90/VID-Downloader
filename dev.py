"""
Local dev server — python dev.py → http://localhost:3000
"""
import importlib.util, os, sys, re, tempfile, mimetypes
from urllib.parse import quote
from flask import Flask, send_file, request, jsonify, Response
from flask_cors import CORS

# Tambah api/ ke path agar bisa import lib.*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))

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

@app.route("/<path:filename>")
def static_files(filename):
    if os.path.exists(filename):
        return send_file(filename)
    return "404 Not Found", 404


# ── /api/debug ────────────────────────────────────────────────────────────────

@app.route("/api/debug")
def debug():
    results = {"python": sys.version, "env": "local"}
    for pkg in ["requests", "bs4", "yt_dlp", "playwright"]:
        try:
            mod = __import__(pkg)
            results[pkg] = f"OK ({getattr(mod, '__version__', '?')})"
        except ImportError as e:
            results[pkg] = f"MISSING: {e}"
    return jsonify(results)


# ── /api/get-video ────────────────────────────────────────────────────────────

@app.route("/api/get-video")
def get_video():
    video_id = request.args.get("id", "").strip()
    if not video_id:
        return jsonify({"status": "error", "message": "ID kosong"}), 400
    if "/" in video_id:
        video_id = video_id.strip("/").split("/")[-1].split("?")[0]

    from lib import vidgf
    url = vidgf.extract(video_id)
    if url:
        return jsonify({"status": "success", "link": url, "id": video_id})
    return jsonify({"status": "error", "message": "Tidak ditemukan"}), 404


# ── /api/scan ─────────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.get_json() or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400
    mod    = load("api/scan.py")
    videos = mod.extract(url)
    return jsonify({"videos": videos, "count": len(videos)})


# ── /api/formats ──────────────────────────────────────────────────────────────

@app.route("/api/formats", methods=["POST"])
def formats():
    data = request.get_json() or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400
    mod                = load("api/formats.py")
    title, thumb, fmts = mod.get_formats(url)
    return jsonify({"title": title, "thumb": thumb, "formats": fmts})


# ── /api/download ─────────────────────────────────────────────────────────────

@app.route("/api/download", methods=["POST"])
def download():
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
        opts = {
            "format": format_id,
            "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
            "quiet": True,
            "merge_output_format": "mp4",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
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
                "Content-Type":        mime,
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Content-Length":      str(len(data_bytes)),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500


# ── /api/imdb ─────────────────────────────────────────────────────────────────

@app.route("/api/imdb")
def imdb():
    raw_id = request.args.get("id", "").strip()
    action = request.args.get("action", "info").strip()

    if not raw_id:
        return jsonify({"error": "Parameter ?id= diperlukan"}), 400

    mod = load("api/imdb.py")

    imdb_id = mod.extract_imdb_id(raw_id)
    if not imdb_id:
        return jsonify({"error": f"IMDB ID tidak valid: {raw_id}"}), 400

    try:
        info = mod.get_movie_info(imdb_id)

        if action == "stream":
            media_type = "tv" if info.get("type") == "series" else "movie"
            raw_url    = mod.get_fast_stream(imdb_id, media_type)
            if raw_url:
                host = request.host
                protocol = "http" if "localhost" in host or "127.0.0.1" in host else "https"
                info["stream_url"] = f"{protocol}://{host}/api/proxy?url={quote(raw_url)}"
            info["embed_url"] = f"https://streamimdb.ru/embed/movie/{imdb_id}"

        return jsonify({"status": "success", **info})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── /api/proxy ────────────────────────────────────────────────────────────────

@app.route("/api/proxy")
def proxy():
    from urllib.parse import urljoin
    import requests as req
    
    spoof_headers = {
        "Origin": "https://brightpathsignals.com",
        "Referer": "https://brightpathsignals.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    }

    target_url = request.args.get("url", "").strip()
    if not target_url:
        return "Missing url param", 400

    try:
        resp = req.get(target_url, headers=spoof_headers, stream=True, timeout=15)
        content_type = resp.headers.get("Content-Type", "application/octet-stream")

        if "mpegurl" in content_type.lower() or target_url.endswith(".m3u8"):
            content = resp.text

            def rewrite(m):
                abs_link = urljoin(target_url, m.group(1))
                return f"/api/proxy?url={quote(abs_link)}"

            new_content = re.sub(r"^(?!#)(.+)$", rewrite, content, flags=re.MULTILINE)
            return Response(
                new_content.encode(),
                status=resp.status_code,
                headers={
                    "Content-Type":                content_type,
                    "Access-Control-Allow-Origin": "*",
                },
            )

        def generate():
            for chunk in resp.iter_content(chunk_size=65536):
                yield chunk

        return Response(
            generate(),
            status=resp.status_code,
            headers={
                "Content-Type":                content_type,
                "Access-Control-Allow-Origin": "*",
            },
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── /api/subtitle/search ──────────────────────────────────────────────────────

@app.route("/api/subtitle/search")
def subtitle_search():
    imdb_id    = request.args.get("imdb_id", "").strip() or None
    query      = request.args.get("query",   "").strip() or None
    lang       = request.args.get("lang",    "en").strip()
    media_type = request.args.get("type",    "movie").strip()

    if not imdb_id and not query:
        return jsonify({"status": "error", "error": "imdb_id atau query wajib diisi"}), 400

    sub = load("api/subtitle.py")
    result = sub.search(
        imdb_id    = imdb_id,
        query      = query,
        lang       = lang,
        media_type = media_type,
    )

    status_code = 200 if result["status"] == "success" else 503
    return jsonify(result), status_code


# ── /api/subtitle/download ────────────────────────────────────────────────────

@app.route("/api/subtitle/download")
def subtitle_download():
    file_id = request.args.get("file_id", "").strip()
    if not file_id:
        return jsonify({"error": "file_id wajib diisi"}), 400

    sub = load("api/subtitle.py")

    # 1. Minta URL download dari OpenSubtitles
    dl_url, err = sub.get_download_url(file_id)
    if err:
        return jsonify({"error": err}), 500

    # 2. Download konten .srt dan proxy ke frontend
    srt_text, err = sub.fetch_srt(dl_url)
    if err:
        return jsonify({"error": err}), 500

    return Response(
        srt_text.encode("utf-8"),
        status=200,
        headers={
            "Content-Type":                "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    required = [
        "index.html",
        "api/get-video.py",
        "api/imdb.py",
        "api/subtitle.py",
    ]
    optional = [
        "api/scan.py",
        "api/formats.py",
        "api/download.py",
        "extractor.html",
    ]

    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        print("[ERROR] File wajib tidak ada:")
        for f in missing:
            print(f"        {f}")
        sys.exit(1)

    warn = [f for f in optional if not os.path.exists(f)]
    if warn:
        print("[WARN]  File opsional tidak ditemukan:")
        for f in warn:
            print(f"        {f}")

    print("\n>>> http://localhost:3000")
    print(">>> http://localhost:3000/extractor.html\n")
    app.run(host="0.0.0.0", port=3000, debug=True)