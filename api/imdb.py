from http.server import BaseHTTPRequestHandler
import json, re, requests
from urllib.parse import urlparse, parse_qs, quote, urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Header khusus untuk bypass server video
VIDEO_SPOOF_HEADERS = {
    'Origin': 'https://brightpathsignals.com',
    'Referer': 'https://brightpathsignals.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'
}

def extract_imdb_id(raw):
    m = re.search(r'(tt\d{5,})', raw, re.I)
    if m: return m.group(1)
    n = re.search(r'\b(\d{5,})\b', raw)
    if n: return f"tt{n[1]}"
    return None

def get_movie_info(imdb_id):
    info = {
        "imdb_id": imdb_id, "title": "", "year": "", "type": "movie",
        "poster": "", "description": "", "rating": "", "genre": "", "runtime": ""
    }
    for apikey in ["trilogy", "thewdb"]:
        try:
            r = requests.get(f"http://www.omdbapi.com/?i={imdb_id}&apikey={apikey}", headers=HEADERS, timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("Response") == "True":
                    info.update({
                        "title": d.get("Title",""), "year": d.get("Year",""),
                        "type": d.get("Type","movie"), "poster": d.get("Poster",""),
                        "description": d.get("Plot",""), "rating": d.get("imdbRating",""),
                        "genre": d.get("Genre",""), "runtime": d.get("Runtime","")
                    })
                    return info
        except: continue
    return info

def get_fast_stream(imdb_id, media_type="movie"):
    # Pakai API Vaplayer yang kamu temukan (Jauh lebih cepat dari Playwright)
    api_url = f"https://streamdata.vaplayer.ru/api.php?imdb={imdb_id}&type={media_type}"
    try:
        r = requests.get(api_url, headers=VIDEO_SPOOF_HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            streams = data.get("data", {}).get("stream_urls", [])
            if streams:
                return streams[0].replace("\\/", "/")
    except: pass
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_parts = urlparse(self.path)
        params = parse_qs(url_parts.query)
        
        # --- ROUTE 1: AMBIL INFO & LINK ---
        if "/api/imdb" in url_parts.path:
            raw_id = (params.get("id", [None])[0] or "").strip()
            action = (params.get("action", ["info"])[0] or "info").strip()
            
            imdb_id = extract_imdb_id(raw_id)
            if not imdb_id: return self.send_json({"error": "ID tidak valid"}, 400)

            info = get_movie_info(imdb_id)
            if action == "stream":
                m_type = "tv" if info.get("type") == "series" else "movie"
                raw_url = get_fast_stream(imdb_id, m_type)
                # Bungkus link asli ke proxy kita sendiri
                if raw_url:
                    info["stream_url"] = f"/api/proxy?url={quote(raw_url)}"
                else:
                    info["stream_url"] = None

            self.send_json({"status": "success", **info})

        # --- ROUTE 2: PROXY VIDEO (Penyelamat dari 403) ---
        elif "/api/proxy" in url_parts.path:
            target_url = params.get("url", [None])[0]
            if not target_url: return self.send_error(400)

            try:
                resp = requests.get(target_url, headers=VIDEO_SPOOF_HEADERS, stream=True, timeout=15)
                self.send_response(resp.status_code)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/octet-stream'))
                self.end_headers()

                if "mpegurl" in resp.headers.get('Content-Type', '').lower() or target_url.endswith(".m3u8"):
                    content = resp.text
                    def rewrite(m):
                        abs_link = urljoin(target_url, m.group(1))
                        return f'/api/proxy?url={quote(abs_link)}'
                    new_content = re.sub(r'^(?!#)(.+)$', rewrite, content, flags=re.MULTILINE)
                    self.wfile.write(new_content.encode())
                else:
                    for chunk in resp.iter_content(chunk_size=65536):
                        self.wfile.write(chunk)
            except: self.send_error(500)

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass