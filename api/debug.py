from http.server import BaseHTTPRequestHandler
import json, sys, os


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Cek semua yang penting
        results = {
            "python_version": sys.version,
            "environment": "vercel" if os.environ.get("VERCEL") else "local",
        }

        # Cek setiap package
        packages = ["requests", "bs4", "yt_dlp"]
        for pkg in packages:
            try:
                mod = __import__(pkg)
                ver = getattr(mod, "__version__", "unknown")
                results[pkg] = f"OK ({ver})"
            except ImportError as e:
                results[pkg] = f"MISSING: {e}"

        # Cek bisa fetch URL sederhana
        try:
            import requests as req
            r = req.get("https://httpbin.org/get", timeout=5)
            results["network"] = f"OK (status {r.status_code})"
        except Exception as e:
            results["network"] = f"ERROR: {e}"

        # Cek yt-dlp bisa extract YouTube
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True,
                                    "extract_flat": True, "socket_timeout": 5}) as ydl:
                info = ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
                results["ytdlp_test"] = f"OK - got: {info.get('title','?')[:30]}"
        except Exception as e:
            results["ytdlp_test"] = f"ERROR: {str(e)[:100]}"

        body = json.dumps(results, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass