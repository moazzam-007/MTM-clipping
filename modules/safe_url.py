"""
modules/safe_url.py
Canonical validation and sanitization for YouTube URLs.
Guards against argument injection, SSRF, and malformed inputs.
"""

import re
from urllib.parse import urlparse, parse_qs

_VIDEO_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be"
}

def extract_video_id(raw_url: str) -> str:
    """
    Extracts and strictly validates an 11-character YouTube video ID.
    Raises ValueError if the input is malformed, injected, or non-YouTube.
    """
    if not isinstance(raw_url, str):
        raise ValueError("URL must be a string")

    raw = raw_url.strip()
    if not raw or len(raw) > 300:
        raise ValueError("URL length is invalid")

    # Reject control chars, newlines, carriage returns, null bytes
    if any(c in raw for c in "\r\n\x00\t "):
        raise ValueError("URL contains illegal whitespace or control characters")

    # Reject yt-dlp option injection attempts
    if raw.startswith("-"):
        raise ValueError("URL cannot start with a hyphen")

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")

    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise ValueError(f"Host '{host}' is not an authorized YouTube domain")

    video_id = ""
    if host == "youtu.be":
        # e.g. https://youtu.be/z_9E0w_2IwY
        path_parts = parsed.path.strip("/").split("/")
        if path_parts:
            video_id = path_parts[0]
    else:
        # youtube.com
        if parsed.path == "/watch":
            params = parse_qs(parsed.query)
            v_list = params.get("v")
            if v_list and len(v_list) > 0:
                video_id = v_list[0]
        elif parsed.path.startswith(("/shorts/", "/live/")):
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                video_id = parts[1]

    if not video_id or not _VIDEO_ID_REGEX.match(video_id):
        raise ValueError(f"Could not extract valid 11-char YouTube video ID from: {raw_url}")

    return video_id

def canonical_youtube_url(raw_url: str) -> str:
    """
    Returns a sanitized, canonical YouTube watch URL: https://www.youtube.com/watch?v={video_id}
    """
    vid = extract_video_id(raw_url)
    return f"https://www.youtube.com/watch?v={vid}"
