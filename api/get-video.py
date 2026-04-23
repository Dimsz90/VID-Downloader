from http.server import BaseHTTPRequestHandler
import requests
import re
import json
import base64
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        video_id = params.get('id', [None])[0]

        if not video_id:
            self.send_json({"status": "error", "message": "ID Kosong"}, 400)
            return

        # VidGF biasanya punya beberapa format URL, kita coba tembak embed utamanya
        target_url = f"https://vidgf.com/embed.php?id={video_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://vidgf.com/",
        }

        try:
            resp = requests.get(target_url, headers=headers, timeout=10)
            content = resp.text

            # 1. Cari link MP4 langsung
            link = re.search(r'(https?://[^\s"\'<>]+?\.mp4[^\s"\'<>]*?)', content)
            
            # 2. Jika tidak ada, cari di dalam variabel 'file' atau 'src'
            if not link:
                link = re.search(r'(?:file|src|url)\s*[:=]\s*["\']([^"\']+)["\']', content)

            # 3. Jika masih tidak ada, cek apakah ada string Base64 (sering dipakai untuk sembunyiin link)
            if not link:
                b64_matches = re.findall(r'["\']([A-Za-z0-9+/]{30,}=*)["\']', content)
                for b in b64_matches:
                    try:
                        decoded = base64.b64decode(b).decode('utf-8')
                        if '.mp4' in decoded or 'http' in decoded:
                            video_url = decoded
                            break
                    except:
                        continue
            else:
                video_url = link.group(1).replace('\\/', '/')

            # Validasi hasil
            if 'video_url' in locals() and video_url:
                if video_url.startswith('//'): video_url = 'https:' + video_url
                self.send_json({"status": "success", "link": video_url})
            else:
                # Jika benar-benar buntu, kita kembalikan link embed-nya saja sebagai fallback
                # Tapi karena tadi 'refused to connect', ini hanya last resort
                self.send_json({"status": "success", "link": target_url, "type": "iframe_fallback"})

        except Exception as e:
            self.send_json({"status": "error", "message": str(e)}, 500)

    def send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
