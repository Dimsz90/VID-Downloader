from http.server import BaseHTTPRequestHandler
import requests
import re
import json
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        video_id = params.get('id', [None])[0]

        if not video_id:
            self.send_json({"status": "error", "message": "ID tidak valid"}, 400)
            return

        # Target URL
        target_url = f"https://vidgf.com/embed.php?id={video_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://vidgf.com/",
        }

        try:
            resp = requests.get(target_url, headers=headers, timeout=10)
            # Mencari berbagai pola link .mp4 yang mungkin ada di script
            link_match = re.search(r'(https?://[^\s"\'<>]+?\.mp4[^\s"\'<>]*?)', resp.text)
            
            if not link_match:
                # Pola cadangan jika link tidak ada ekstensi .mp4 langsung
                link_match = re.search(r'file:\s*["\']([^"\']+)["\']', resp.text)

            if link_match:
                video_url = link_match.group(1).replace('\\/', '/')
                if video_url.startswith('//'):
                    video_url = 'https:' + video_url
                
                self.send_json({"status": "success", "link": video_url})
            else:
                self.send_json({"status": "error", "message": "Direct link not found"}, 200)

        except Exception as e:
            self.send_json({"status": "error", "message": str(e)}, 500)

    def send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
