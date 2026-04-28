from http.server import BaseHTTPRequestHandler
import json, time, os, hashlib, hmac

API_SECRET = os.environ.get("API_SECRET", "changeme")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        now_min    = int(time.time() // 60)
        token      = hmac.new(API_SECRET.encode(), str(now_min).encode(), hashlib.sha256).hexdigest()
        expires_in = 60 - (int(time.time()) % 60)
        self.send_json({"token": token, "expires_in": expires_in})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
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