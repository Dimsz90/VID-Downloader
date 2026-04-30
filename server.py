"""
server.py — Entry point untuk Railway
Menggantikan Vercel serverless, jalan sebagai HTTP server biasa.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import os, sys, mimetypes, traceback

# Pastikan folder api/ bisa di-import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))
sys.path.insert(0, os.path.dirname(__file__))

from api.imdb import handler as ImdbHandler
from api.index import handler as IndexHandler

PORT = int(os.environ.get("PORT", 8080))


class MainHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            path = self.path.split("?")[0]

            # Route API ke handler yang sesuai
            if "/api/imdb-proxy" in path or "/api/imdb" in path or "/api/proxy" in path:
                self._delegate(ImdbHandler)
            elif path.startswith("/api/"):
                self._delegate(IndexHandler)
            else:
                self._serve_static(path)
        except Exception:
            print("[ERROR] Unhandled exception in do_GET:", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()

    def do_POST(self):
        try:
            self._delegate(IndexHandler, method="POST")
        except Exception:
            print("[ERROR] Unhandled exception in do_POST:", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()

    def _delegate(self, HandlerClass, method="GET"):
        """Delegate request ke handler class tertentu."""
        try:
            h = HandlerClass.__new__(HandlerClass)
            h.path    = self.path
            h.headers = self.headers
            h.wfile   = self.wfile
            h.rfile   = self.rfile
            h.server  = self.server
            h.request = self.request
            h.client_address = self.client_address
            if method == "POST":
                HandlerClass.do_POST(h)
            else:
                HandlerClass.do_GET(h)
        except Exception:
            print(f"[ERROR] Unhandled exception in _delegate ({method} {self.path}):", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()

    def _serve_static(self, path):
        # Map URL path ke file system
        static_routes = {
            "/manifest.json": "public/manifest.json",
            "/sw.js":         "public/sw.js",
        }

        if path in static_routes:
            file_path = static_routes[path]
        elif path.startswith("/icons/"):
            file_path = "public" + path
        elif path.startswith("/screenshots/"):
            file_path = "public" + path
        elif path == "/" or path == "":
            file_path = "index.html"
        elif path == "/extractor.html":
            file_path = "extractor.html"
        else:
            # SPA fallback → index.html
            file_path = "index.html"

        self._send_file(file_path)

    def _send_file(self, file_path):
        try:
            with open(file_path, "rb") as f:
                content = f.read()

            mime, _ = mimetypes.guess_type(file_path)
            mime = mime or "application/octet-stream"

            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            # Cache static assets
            if any(file_path.endswith(ext) for ext in [".png", ".ico", ".css", ".js"]):
                self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(content)

        except FileNotFoundError:
            # Fallback ke index.html untuk SPA routing
            try:
                with open("index.html", "rb") as f:
                    content = f.read()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}", flush=True)


if __name__ == "__main__":
    print(f"[SERVER] Starting on port {PORT}...", flush=True)
    server = HTTPServer(("0.0.0.0", PORT), MainHandler)
    print(f"[SERVER] Running at http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
