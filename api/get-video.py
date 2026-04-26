from http.server import BaseHTTPRequestHandler
import requests
import re
import json
import base64
from urllib.parse import urlparse, parse_qs


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query  = urlparse(self.path).query
        params = parse_qs(query)
        video_id = params.get("id", [None])[0]

        if not video_id:
            self.send_json({"status": "error", "message": "ID kosong"}, 400)
            return

        # Bersihkan video_id — ambil bagian terakhir kalau dikasih full URL
        if "/" in video_id:
            video_id = video_id.strip("/").split("/")[-1].split("?")[0]

        video_url = self._extract(video_id)

        if video_url:
            self.send_json({"status": "success", "link": video_url, "id": video_id})
        else:
            self.send_json({
                "status": "error",
                "message": "Tidak bisa menemukan link video. Coba ID yang lain."
            }, 404)

    # ── Core extractor ────────────────────────────────────────────────────

    def _extract(self, video_id):
        """
        Coba beberapa endpoint vidgf secara berurutan sampai salah satu berhasil.
        """
        endpoints = [
            f"https://vidgf.com/embed.php?id={video_id}",
            f"https://vidgf.com/d/{video_id}",
            f"https://vidgf.com/v/{video_id}",
        ]

        referers = [
            "https://simemek.com/",
            "https://montok.live/",
            "https://vidgf.com/",
        ]

        headers_base = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }

        for endpoint in endpoints:
            for referer in referers:
                try:
                    headers = {**headers_base, "Referer": referer, "Origin": referer.rstrip("/")}
                    resp = requests.get(endpoint, headers=headers, timeout=10)

                    if resp.status_code != 200:
                        continue

                    content = resp.text
                    if len(content) < 50:  # halaman kosong / error
                        continue

                    url = self._parse_content(content)
                    if url:
                        print(f"[vidgf] ✓ {endpoint} (referer={referer}) → {url[:80]}")
                        return url

                except Exception as e:
                    print(f"[vidgf] error {endpoint}: {e}")
                    continue

        return None

    def _parse_content(self, content):
        """
        Ekstrak URL video dari HTML/JS dengan 4 metode berbeda.
        """

        # 1. URL mp4/m3u8/webm langsung di dalam teks
        m = re.search(
            r'(https?://[^\s"\'<>\\]+?\.(?:mp4|m3u8|webm|mkv|mov)(?:\?[^\s"\'<>\\]*)?)',
            content, re.IGNORECASE
        )
        if m:
            return m.group(1).replace("\\/", "/")

        # 2. Variabel JS: file:"...", src:"...", url:"...", source:"..."
        m = re.search(
            r'(?:file|src|url|source|stream|hls)\s*[:=]\s*["\']([^"\']{15,})["\']',
            content, re.IGNORECASE
        )
        if m:
            url = m.group(1).replace("\\/", "/")
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http"):
                return url

        # 3. JSON sources array: [{"file":"..."}] atau [{"src":"..."}]
        m = re.search(r'sources\s*[:=]\s*(\[.*?\])', content, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                sources = json.loads(m.group(1))
                for s in sources:
                    url = s.get("file") or s.get("src") or s.get("url") or ""
                    if url and url.startswith("http"):
                        return url.replace("\\/", "/")
            except Exception:
                pass

        # 4. Base64 encoded URL (vidgf kadang encode URL-nya)
        for b64 in re.findall(r'["\']([A-Za-z0-9+/]{30,}={0,2})["\']', content):
            try:
                decoded = base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
                if any(ext in decoded for ext in [".mp4", ".m3u8", ".webm"]):
                    return decoded.strip()
                if re.match(r'https?://', decoded) and len(decoded) > 20:
                    return decoded.strip()
            except Exception:
                continue

        return None

    # ── Helper ───────────────────────────────────────────────────────────

    def send_json(self, data, status_code=200):
        body = json.dumps(data).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress default request logs