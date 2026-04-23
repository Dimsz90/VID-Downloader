from http.server import BaseHTTPRequestHandler
import requests
import re
import json
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Mengambil ID dari query parameter ?id=...
        query = urlparse(self.path).query
        params = parse_qs(query)
        video_id = params.get('id', [None])[0]

        if not video_id:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing Video ID")
            return

        embed_url = f"https://vidgf.com/embed.php?bucket=temporary&id={video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://vidgf.com/"
        }

        try:
            resp = requests.get(embed_url, headers=headers, timeout=10)
            match = re.search(r'<source\s+src="([^"]+)"', resp.text)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*') # Allow CORS
            self.end_headers()

            if match:
                result = {"status": "success", "link": match.group(1)}
            else:
                result = {"status": "error", "message": "Link not found"}
            
            self.wfile.write(json.dumps(result).encode())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())