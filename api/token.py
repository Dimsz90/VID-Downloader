from http.server import BaseHTTPRequestHandler
import json, time
from ._auth import make_token, ALLOWED_ORIGINS


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        token      = make_token()
        expires_in = 60 - (int(time.time()) % 60)

        self.send_json({
            "token":      token,
            "expires_in": expires_in,  # detik sampai token berganti
        })

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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