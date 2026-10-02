"""Bilibili video list crawler using bilibili-api-python.

Flow:
    1. Fetch UP主's video list via API
    2. Filter out deleted/private/dynamic videos (state check)
    3. Insert new videos into video_review with status=NEW
    4. Skip duplicates via uk_bvid (INSERT IGNORE semantics)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import VideoReview

logger = logging.getLogger("pipeline.crawler")

# B站 video state values (from bilibili-api-python)
# 0=开放, 1=橙色通过, 2=待审, 3=补件, 4=退回, 5=稿件被锁定, 6=转码中,
# 7=待删除, 8=禁止访问, 9=暂缓发布, 10=预约上架, 11=定时发布,
# 12=投稿ing, 13=转码失败, 14=允许转载, 15=开放浏览
VALID_STATES = {0, 1, 14, 15}  # Only these states mean the video is publicly accessible


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


def fetch_video_list(mid: int, page: int = 1, page_size: int = 30) -> list[dict[str, Any]]:
    """Fetch video list for a given UP主 (mid).

    Args:
        mid: Bilibili user ID
        page: Page number (1-based)
        page_size: Videos per page (max 50)

    Returns:
        List of video metadata dicts with keys:
        bvid, mid, title, pubdate, duration, state
    """
    try:
        from bilibili_api import user, sync

        u = user.User(mid)
        resp = sync(u.get_videos(pn=page, ps=page_size))

        videos = []
        for v in resp.get("list", {}).get("vlist", []):
            state = v.get("state", {})
            # Check if video is accessible
            # In newer API versions, state might be an int directly
            state_val = state if isinstance(state, int) else state.get("state", 0)

            if state_val not in VALID_STATES:
                logger.debug(
                    "[crawler] Skipping BVID=%s state=%d (not public)",
                    v.get("bvid"),
                    state_val,
                )
                continue

            videos.append(
                {
                    "bvid": v.get("bvid", ""),
                    "mid": mid,
                    "title": v.get("title", ""),
                    "pubdate": datetime.fromtimestamp(v.get("created", 0)),
                    "duration": _parse_duration(v.get("length", "0:00")),
                }
            )

        logger.info("[crawler] Fetched %d valid videos for mid=%d (page %d)", len(videos), mid, page)
        return videos

    except Exception:
        logger.exception("[crawler] Failed to fetch videos for mid=%d", mid)
        return []


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
        try:
            db.add(record)
            db.flush()
            inserted += 1
        except IntegrityError:
            # Duplicate bvid, skip
            db.rollback()
            logger.debug("[crawler] Duplicate BVID=%s, skipping", v["bvid"])
            continue

    db.commit()
    logger.info("[crawler] Saved %d new videos (%d total attempted)", inserted, len(videos))
    return inserted