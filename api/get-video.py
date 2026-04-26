from http.server import BaseHTTPRequestHandler
import requests, re, json, base64
from urllib.parse import urlparse, parse_qs


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        params   = parse_qs(urlparse(self.path).query)
        video_id = params.get("id", [None])[0]

        if not video_id:
            return self.send_json({"status": "error", "message": "ID kosong"}, 400)

        if "/" in video_id:
            video_id = video_id.strip("/").split("/")[-1].split("?")[0]

        url = self._extract(video_id)
        if url:
            self.send_json({"status": "success", "link": url, "id": video_id})
        else:
            self.send_json({"status": "error", "message": "Link tidak ditemukan"}, 404)

    def _extract(self, video_id):
        endpoints = [
            f"https://vidgf.com/embed.php?id={video_id}",
            f"https://vidgf.com/d/{video_id}",
        ]
        referers = ["https://simemek.com/", "https://montok.live/", "https://vidgf.com/"]
        headers_base = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }
        for endpoint in endpoints:
            for referer in referers:
                try:
                    resp = requests.get(endpoint, headers={**headers_base, "Referer": referer, "Origin": referer.rstrip("/")}, timeout=10)
                    if resp.status_code != 200 or len(resp.text) < 50:
                        continue
                    url = self._parse(resp.text)
                    if url:
                        return url
                except Exception:
                    continue
        return None

    def _parse(self, content):
        # 1. URL langsung
        m = re.search(r'(https?://[^\s"\'<>\\]+?\.(?:mp4|m3u8|webm)(?:\?[^\s"\'<>\\]*)?)', content, re.I)
        if m:
            return m.group(1).replace("\\/", "/")
        # 2. Variabel JS
        m = re.search(r'(?:file|src|url|source|stream|hls)\s*[:=]\s*["\']([^"\']{15,})["\']', content, re.I)
        if m:
            u = m.group(1).replace("\\/", "/")
            if u.startswith("//"): u = "https:" + u
            if u.startswith("http"): return u
        # 3. JSON sources
        m = re.search(r'sources\s*[:=]\s*(\[.*?\])', content, re.DOTALL | re.I)
        if m:
            try:
                for s in json.loads(m.group(1)):
                    u = s.get("file") or s.get("src") or s.get("url") or ""
                    if u.startswith("http"): return u.replace("\\/", "/")
            except Exception:
                pass
        # 4. Base64
        for b64 in re.findall(r'["\']([A-Za-z0-9+/]{30,}={0,2})["\']', content):
            try:
                d = base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
                if any(e in d for e in [".mp4", ".m3u8", ".webm"]) or re.match(r'https?://', d):
                    return d.strip()
            except Exception:
                continue
        return None

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass