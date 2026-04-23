from http.server import BaseHTTPRequestHandler
import requests
import re
import json
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Ambil ID dari URL (?id=...)
        query = urlparse(self.path).query
        params = parse_qs(query)
        video_id = params.get('id', [None])[0]

        if not video_id:
            self.send_error_response("Video ID tidak ditemukan di URL.")
            return

        # 2. Setup URL dan Headers
        target_url = f"https://vidgf.com/embed.php?id={video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://vidgf.com/",
            "Accept": "text/html,application/xhtml+xml,xml;q=0.9,image/avif,webp,*/*;q=0.8"
        }

        try:
            # 3. Ambil Source Code dari halaman VidGF
            response = requests.get(target_url, headers=headers, timeout=10)
            html_content = response.text

            # 4. Cari link video (.mp4 atau .m3u8) menggunakan Regex
            # Mencoba beberapa pola umum yang sering dipakai player video
            match = (
                re.search(r'file:\s*"([^"]+)"', html_content) or 
                re.search(r'src:\s*"([^"]+)"', html_content) or 
                re.search(r'<source\s+src="([^"]+)"', html_content)
            )

            if match:
                video_url = match.group(1)
                
                # Perbaikan jika URL bersifat relatif (//domain.com)
                if video_url.startswith('//'):
                    video_url = 'https:' + video_url

                self.send_success_response(video_url)
            else:
                self.send_error_response("Link video mentah tidak ditemukan. Mungkin terproteksi atau expired.")

        except Exception as e:
            self.send_error_response(f"Server Error: {str(e)}")

    def send_success_response(self, link):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        res = {"status": "success", "link": link}
        self.wfile.write(json.dumps(res).encode())

    def send_error_response(self, message):
        self.send_response(200) # Tetap 200 agar ditangkap frontend sebagai JSON error
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        res = {"status": "error", "message": message}
        self.wfile.write(json.dumps(res).encode())
