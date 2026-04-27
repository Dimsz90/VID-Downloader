from http.server import BaseHTTPRequestHandler
import json, re, os, time, hashlib, hmac, requests
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

# ── Auth (inline) ─────────────────────────────────────────────────────────────
API_SECRET  = os.environ.get("API_SECRET", "changeme-set-in-vercel-env")
_rate_store = defaultdict(list)

def _verify_token(token):
    if not token: return False
    now_min = int(time.time() // 60)
    for m in [now_min, now_min - 1]:
        exp = hmac.new(API_SECRET.encode(), str(m).encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, exp): return True
    return False

def _get_ip(h):
    for hdr in ["x-forwarded-for","x-real-ip","cf-connecting-ip"]:
        v = h.headers.get(hdr)
        if v: return v.split(",")[0].strip()
    return h.client_address[0]

def _rate_ok(ip, limit=30, window=60):
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < window]
    if len(_rate_store[ip]) >= limit: return False
    _rate_store[ip].append(now); return True

def guard(h):
    ip = _get_ip(h)
    if not _rate_ok(ip): _err(h, 429, "Too many requests"); return False
    token = h.headers.get("x-api-token", "")
    if not _verify_token(token): _err(h, 401, "Token tidak valid"); return False
    return True

def _err(h, code, msg):
    body = json.dumps({"error": msg}).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)

# ── IMDB extractor ────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_imdb_id(input_str):
    """
    Ekstrak IMDB ID (ttXXXXXXX) dari berbagai format input:
    - https://www.imdb.com/title/tt11378946/
    - https://streamimdb.me/embed/tt11378946
    - tt11378946
    - 11378946
    """
    # Cari pattern tt + angka
    m = re.search(r'(tt\d{5,})', input_str)
    if m:
        return m.group(1)
    # Kalau hanya angka
    m = re.search(r'\b(\d{5,})\b', input_str)
    if m:
        return f"tt{m.group(1)}"
    return None


def get_movie_info(imdb_id):
    """
    Ambil info film dari beberapa sumber:
    1. OMDB API (gratis, no key needed untuk basic)
    2. Scrape IMDB langsung sebagai fallback
    """
    info = {
        "imdb_id":     imdb_id,
        "title":       "",
        "year":        "",
        "type":        "",  # movie / series
        "poster":      "",
        "description": "",
        "rating":      "",
        "genre":       "",
        "runtime":     "",
        "embed_url":   f"https://streamimdb.me/embed/{imdb_id}",
        "imdb_url":    f"https://www.imdb.com/title/{imdb_id}/",
    }

    # ── Coba OMDB API (tidak butuh key untuk basic info) ──────────────────
    try:
        # OMDB punya free tier tanpa API key untuk beberapa field
        # Pakai public API key "trilogy" yang sering work untuk testing
        for apikey in ["trilogy", "thewdb"]:
            r = requests.get(
                f"http://www.omdbapi.com/?i={imdb_id}&apikey={apikey}",
                headers=HEADERS, timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("Response") == "True":
                    info["title"]       = data.get("Title", "")
                    info["year"]        = data.get("Year", "")
                    info["type"]        = data.get("Type", "movie")
                    info["poster"]      = data.get("Poster", "")
                    info["description"] = data.get("Plot", "")
                    info["rating"]      = data.get("imdbRating", "")
                    info["genre"]       = data.get("Genre", "")
                    info["runtime"]     = data.get("Runtime", "")
                    print(f"[imdb] OMDB OK: {info['title']}")
                    return info
    except Exception as e:
        print(f"[imdb] OMDB error: {e}")

    # ── Fallback: scrape IMDB langsung ────────────────────────────────────
    try:
        from bs4 import BeautifulSoup
        r = requests.get(
            f"https://www.imdb.com/title/{imdb_id}/",
            headers={**HEADERS,
                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                     "Sec-Fetch-Mode": "navigate",
                     "Sec-Fetch-Site": "none"},
            timeout=10
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            # JSON-LD adalah cara paling reliable
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "{}")
                    if data.get("@type") in ("Movie", "TVSeries", "TVEpisode"):
                        info["title"]       = data.get("name", "")
                        info["description"] = (data.get("description") or "")[:200]
                        info["genre"]       = ", ".join(data.get("genre") or [])
                        info["rating"]      = str((data.get("aggregateRating") or {}).get("ratingValue", ""))
                        img = data.get("image")
                        if isinstance(img, str):
                            info["poster"] = img
                        elif isinstance(img, dict):
                            info["poster"] = img.get("url", "")
                        info["type"] = "series" if data.get("@type") == "TVSeries" else "movie"
                        print(f"[imdb] scrape OK: {info['title']}")
                        break
                except Exception:
                    pass

            # Fallback ke og:tags
            if not info["title"]:
                for meta in soup.find_all("meta"):
                    prop = meta.get("property", "") or meta.get("name", "")
                    content = meta.get("content", "")
                    if prop == "og:title":       info["title"] = content
                    elif prop == "og:image":     info["poster"] = content
                    elif prop == "og:description": info["description"] = content[:200]
    except Exception as e:
        print(f"[imdb] scrape error: {e}")

    # ── Last resort: pakai judul dari IMDB ID saja ────────────────────────
    if not info["title"]:
        info["title"] = imdb_id

    return info


# ── Handler ───────────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if not guard(self): return

        params   = parse_qs(urlparse(self.path).query)
        raw_id   = params.get("id", [None])[0] or ""

        if not raw_id:
            return self.send_json({"error": "Parameter ?id= diperlukan"}, 400)

        imdb_id = extract_imdb_id(raw_id)
        if not imdb_id:
            return self.send_json({"error": f"IMDB ID tidak valid: {raw_id}"}, 400)

        try:
            info = get_movie_info(imdb_id)
            self.send_json({"status": "success", **info})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-token")
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass