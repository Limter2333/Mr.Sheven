"""Bilibili video list crawler.

Flow:
    1. Fetch UP主's video list via WBI-signed API (bilibili_client)
    2. Filter out deleted/private/dynamic videos (state check)
    3. Insert new videos into video_review with status=NEW
    4. Skip duplicates via uk_bvid (INSERT IGNORE semantics)
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import VideoReview

logger = logging.getLogger("pipeline.crawler")


def _load_cookie_str() -> str:
    """Load raw cookie string from cookie.txt."""
    from shared.config import config

    cookie_path = config.bilibili.cookies_path
    try:
        with open(cookie_path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("[crawler] Cookie file not found: %s", cookie_path)
        return ""


# Rotate User-Agent to look like different browsers/sessions
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]


def _human_delay(low: float = 2.0, high: float = 6.0) -> None:
    """Random delay to simulate human browsing rhythm."""
    delay = random.uniform(low, high)
    logger.debug("[crawler] Human delay: %.1fs", delay)
    time.sleep(delay)


def _build_headers(mid: int, cookie_str: str) -> dict[str, str]:
    """Build realistic browser headers with rotation."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Cookie": cookie_str,
        "Referer": f"https://space.bilibili.com/{mid}/video",
        "Origin": "https://space.bilibili.com",
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

# B站 video state values (from bilibili-api-python)
# 0=开放, 1=橙色通过, 2=待审, 3=补件, 4=退回, 5=稿件被锁定, 6=转码中,
# 7=待删除, 8=禁止访问, 9=暂缓发布, 10=预约上架, 11=定时发布,
# 12=投稿ing, 13=转码失败, 14=允许转载, 15=开放浏览
VALID_STATES = {0, 1, 14, 15}  # Only these states mean the video is publicly accessible


class FetchResult:
    """Result of a video list fetch, with rate-limit status."""

    def __init__(self, videos: list[dict[str, Any]], status: str) -> None:
        self.videos = videos
        self.status = status  # "ok", "rate_limited", "blocked_412", "error"


def _clean_title(title: str) -> tuple[str, str]:
    """Clean title: remove 【】decorations, year, symbols. Returns (clean, hash)."""
    import re

    # Remove content inside 【】
    clean = re.sub(r"【[^】]*】", "", title)
    # Remove common decorations
    clean = re.sub(r"[|｜\-_~～·•]", " ", clean)
    # Remove year patterns
    clean = re.sub(r"\b(19|20)\d{2}\b", "", clean)
    # Normalize whitespace and lowercase
    clean = " ".join(clean.split()).strip().lower()
    title_hash = hashlib.md5(clean.encode()).hexdigest()
    return clean, title_hash


def fetch_video_list(mid: int, page: int = 1, page_size: int = 20) -> FetchResult:
    """Fetch video list for a given UP主 (mid) using WBI-signed API.

    Args:
        mid: Bilibili user ID
        page: Page number (1-based)
        page_size: Videos per page (default 20, B站 limit)

    Returns:
        FetchResult with videos list and status
    """
    from pipeline.crawler.bilibili_client import fetch_video_list_signed

    result = fetch_video_list_signed(mid=mid, page=page, page_size=page_size)
    return FetchResult(result.videos, result.status)


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


def save_videos(db: Session, videos: list[dict[str, Any]]) -> int:
    """Save videos to video_review table. Skip duplicates via uk_bvid.

    Args:
        db: SQLAlchemy session
        videos: List of video dicts from fetch_video_list

    Returns:
        Number of newly inserted videos
    """
    inserted = 0
    for v in videos:
        title_clean, title_hash = _clean_title(v["title"])
        record = VideoReview(
            bvid=v["bvid"],
            mid=v["mid"],
            title=v["title"],
            title_clean=title_clean,
            title_hash=title_hash,
            pubdate=v["pubdate"],
            duration_sec=v["duration"],
            status="NEW",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        # Use savepoint so a duplicate doesn't roll back the whole batch
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
                inserted += 1
        except IntegrityError:
            logger.debug("[crawler] Duplicate BVID=%s, skipping", v["bvid"])
            continue

    db.commit()
    logger.info("[crawler] Saved %d new videos (%d total attempted)", inserted, len(videos))
    return inserted