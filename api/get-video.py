from http.server import BaseHTTPRequestHandler
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
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Missing Video ID"}).encode())
            return

        # Kita kembalikan link Embed resmi agar bisa diputar di Iframe
        # Link ini sudah kamu uji sebelumnya dan bisa dibuka
        embed_url = f"https://vidgf.com/embed.php?bucket=temporary&id={video_id}"
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*') # Penting untuk Vercel
        self.end_headers()

        # Kita kirim kembali ke frontend
        result = {
            "status": "success", 
            "link": embed_url
        }
        
        self.wfile.write(json.dumps(result).encode())
