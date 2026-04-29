"""
Token generation & validation.
HMAC-based, rotates setiap menit.
"""
import time
import hashlib
import hmac

from .config import API_SECRET


def generate_token() -> dict:
    """Buat token + waktu kedaluwarsa."""
    now_min    = int(time.time() // 60)
    token      = hmac.new(
        API_SECRET.encode(), str(now_min).encode(), hashlib.sha256
    ).hexdigest()
    expires_in = 60 - (int(time.time()) % 60)
    return {"token": token, "expires_in": expires_in}


def validate_token(token: str) -> bool:
    """
    Validasi token — terima token dari menit ini ATAU menit sebelumnya
    (grace window 1 menit agar tidak race condition).
    """
    if not token:
        return False

    now_min = int(time.time() // 60)

    for offset in (0, -1):
        expected = hmac.new(
            API_SECRET.encode(),
            str(now_min + offset).encode(),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(token, expected):
            return True

    return False
