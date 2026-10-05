"""Bilibili API client with WBI signing.

Uses the WBI signing algorithm (wbi_sign.py) to sign requests,
then sends them via httpx with realistic browser headers.

This replaces the direct unsigned API calls that were being rate-limited (-799).

Key acquisition priority:
    1. Cached wbi_keys.json (valid ~24h)
    2. GET /x/web-interface/nav → wbi_img.img_url / sub_url
    3. Fail: raise / return None
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from pipeline.crawler.wbi_sign import WbiKeys, sign_params
from shared.log_setup import log_dir

logger = logging.getLogger("pipeline.bilibili_client")

WBI_CACHE_FILE = log_dir("pipeline") / "wbi_keys.json"
CACHE_TTL = 24 * 3600  # 24 hours

# Rotate User-Agent to look like different browsers/sessions
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]


def _load_cookie_str() -> str:
    """Load raw cookie string from cookie.txt."""
    from shared.config import config

    cookie_path = config.bilibili.cookies_path
    try:
        with open(cookie_path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("[bilibili_client] Cookie file not found: %s", cookie_path)
        return ""


def _build_headers(cookie_str: str, referer: str = "https://www.bilibili.com/") -> dict[str, str]:
    """Build realistic browser headers."""
    import random

    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Cookie": cookie_str,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Connection": "keep-alive",
    }


# ─── WBI Key acquisition ──────────────────────────────────────────────

def _extract_key_from_url(url: str) -> str:
    """Extract the key from a wbi_img URL.

    Example: https://i0.hdslb.com/bfs/wbi/<key>.png → <key>
    """
    match = re.search(r"/wbi/([^.]+)\.png", url)
    return match.group(1) if match else ""


def _load_cached_keys() -> WbiKeys | None:
    """Load WBI keys from local cache file if still valid."""
    try:
        if not os.path.exists(WBI_CACHE_FILE):
            return None
        with open(WBI_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("cached_at", 0) > CACHE_TTL:
            return None
        keys = WbiKeys(img_key=data["img_key"], sub_key=data["sub_key"])
        logger.info("[bilibili_client] Loaded WBI keys from cache")
        return keys
    except Exception:
        return None


def _save_cached_keys(keys: WbiKeys) -> None:
    """Save WBI keys to cache file."""
    try:
        with open(WBI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "img_key": keys.img_key,
                "sub_key": keys.sub_key,
                "cached_at": time.time(),
            }, f)
        logger.info("[bilibili_client] WBI keys cached to %s", WBI_CACHE_FILE)
    except Exception:
        pass


def get_wbi_keys() -> WbiKeys | None:
    """Get WBI signing keys. Priority: cache → nav API.

    Returns None if both methods fail.
    """
    # 1. Try cache
    keys = _load_cached_keys()
    if keys:
        return keys

    # 2. Try nav API
    cookie_str = _load_cookie_str()
    headers = _build_headers(cookie_str, referer="https://www.bilibili.com/")

    try:
        with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
            resp = client.get("https://api.bilibili.com/x/web-interface/nav")

        if resp.status_code == 412:
            logger.error("[bilibili_client] 412 blocked when fetching nav API for WBI keys")
            return None

        data = resp.json()
        if data.get("code") != 0:
            logger.error("[bilibili_client] nav API error: code=%s msg=%s",
                         data.get("code"), data.get("message"))
            return None

        wbi_img = data.get("data", {}).get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        img_key = _extract_key_from_url(img_url)
        sub_key = _extract_key_from_url(sub_url)

        if not img_key or not sub_key:
            logger.error("[bilibili_client] Failed to extract WBI keys from nav response")
            return None

        keys = WbiKeys(img_key=img_key, sub_key=sub_key)
        _save_cached_keys(keys)
        logger.info("[bilibili_client] WBI keys acquired from nav API: img=%s… sub=%s…",
                     img_key[:8], sub_key[:8])
        return keys

    except Exception as exc:
        logger.error("[bilibili_client] Failed to get WBI keys: %s", exc)
        return None


# ─── Signed API requests ──────────────────────────────────────────────

@dataclass
class SignedFetchResult:
    """Result of a signed API fetch."""
    videos: list[dict]
    status: str  # "ok", "rate_limited", "blocked_412", "error", "no_keys"
    code: int = 0


def fetch_video_list_signed(
    mid: int,
    page: int = 1,
    page_size: int = 20,
) -> SignedFetchResult:
    """Fetch video list with WBI-signed request.

    Uses GET /x/space/wbi/arc/search (the WBI-protected endpoint).
    """
    import random

    keys = get_wbi_keys()
    if not keys:
        return SignedFetchResult([], "no_keys")

    cookie_str = _load_cookie_str()
    headers = _build_headers(
        cookie_str,
        referer=f"https://space.bilibili.com/{mid}/video",
    )

    params = {
        "mid": mid,
        "ps": page_size,
        "pn": page,
        "order": "pubdate",
        "platform": "web",
        "web_location": "1550101",
    }

    # WBI signature
    signed_params = sign_params(params, keys.img_key, keys.sub_key)

    url = "https://api.bilibili.com/x/space/wbi/arc/search"

    try:
        import time as _time
        _time.sleep(random.uniform(1.0, 3.0))  # Human-like delay before request

        with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
            resp = client.get(url, params=signed_params)

        if resp.status_code == 412:
            logger.warning("[bilibili_client] 412 risk control for mid=%d", mid)
            return SignedFetchResult([], "blocked_412")

        if resp.status_code != 200:
            logger.error("[bilibili_client] HTTP %d for mid=%d", resp.status_code, mid)
            return SignedFetchResult([], "error")

        data = resp.json()
        code = data.get("code", -1)

        if code == -799:
            logger.warning("[bilibili_client] Rate limited (-799) for mid=%d page=%d", mid, page)
            return SignedFetchResult([], "rate_limited", code=code)

        if code != 0:
            logger.error("[bilibili_client] API error mid=%d code=%d msg=%s",
                         mid, code, data.get("message"))
            return SignedFetchResult([], "error", code=code)

        # Parse video list
        from datetime import datetime

        videos = []
        for v in data.get("data", {}).get("list", {}).get("vlist", []):
            state_val = v.get("state", 0)
            if isinstance(state_val, dict):
                state_val = state_val.get("state", 0)

            # VALID_STATES from client.py
            if state_val not in {0, 1, 14, 15}:
                continue

            videos.append({
                "bvid": v.get("bvid", ""),
                "mid": mid,
                "title": v.get("title", ""),
                "pubdate": datetime.fromtimestamp(v.get("created", 0)),
                "duration": _parse_duration(v.get("length", "0:00")),
            })

        logger.info("[bilibili_client] ✅ Fetched %d valid videos for mid=%d (page %d, WBI-signed)",
                     len(videos), mid, page)
        return SignedFetchResult(videos, "ok", code=code)

    except Exception as exc:
        logger.error("[bilibili_client] Failed to fetch for mid=%d: %s", mid, exc)
        return SignedFetchResult([], "error")


def _parse_duration(length_str: str) -> int:
    """Parse 'MM:SS' or 'HH:MM:SS' duration string to seconds."""
    parts = length_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0
