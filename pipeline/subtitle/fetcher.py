"""Subtitle fetcher: B站 AI 字幕优先，失败直接跳过（裁决 C8：不做 ASR）.

Flow:
    1. Try BiliBiliCCSubtitle (with TOKEN)
    2. Fallback: yt-dlp --write-subs --sub-langs ai-zh
    3. On failure: mark NO_SUBTITLE, log and continue
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from shared.config import config

logger = logging.getLogger("pipeline.subtitle")


def fetch_subtitle(bvid: str, cookies_path: str | None = None) -> list[dict[str, Any]] | None:
    """Fetch subtitle for a Bilibili video.

    Args:
        bvid: Bilibili video ID (e.g., "BV1Yjciz3EuE")
        cookies_path: Path to cookies.txt file

    Returns:
        List of subtitle segments with 'from', 'to', 'content' keys,
        or None if no subtitle available.
    """
    cookies = cookies_path or config.bilibili.cookies_path

    # Try yt-dlp AI subtitle first
    result = _fetch_via_ytdlp(bvid, cookies)
    if result:
        return result

    logger.info("[subtitle] No AI subtitle found for %s, skipping (裁决 C8)", bvid)
    return None


def _fetch_via_ytdlp(bvid: str, cookies_path: str) -> list[dict[str, Any]] | None:
    """Fetch subtitle via yt-dlp."""
    url = f"https://www.bilibili.com/video/{bvid}"
    output_dir = Path(f"probe/{bvid}")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # List available subtitles
        cmd_list = [
            "yt-dlp",
            "--cookies", cookies_path,
            "--list-subs",
            "--no-download",
            url,
        ]
        result = subprocess.run(
            cmd_list, capture_output=True, text=True, timeout=60, check=False
        )

        if "ai-zh" not in result.stdout and "zh-CN" not in result.stdout:
            logger.info("[subtitle] No Chinese subtitle available for %s", bvid)
            return None

        # Download subtitle
        sub_lang = "ai-zh" if "ai-zh" in result.stdout else "zh-CN"
        cmd_download = [
            "yt-dlp",
            "--cookies", cookies_path,
            "--write-subs",
            "--sub-langs", sub_lang,
            "--sub-format", "json3",
            "--skip-download",
            "-o", str(output_dir / "%(id)s"),
            url,
        ]
        subprocess.run(
            cmd_download, capture_output=True, text=True, timeout=120, check=False
        )

        # Find and parse subtitle JSON
        for json_file in output_dir.glob("*.json3"):
            segments = _parse_json3(json_file)
            if segments:
                logger.info(
                    "[subtitle] Fetched %d segments for %s via yt-dlp",
                    len(segments),
                    bvid,
                )
                return segments

        return None

    except subprocess.TimeoutExpired:
        logger.warning("[subtitle] yt-dlp timeout for %s", bvid)
        return None
    except Exception:
        logger.exception("[subtitle] Error fetching subtitle for %s", bvid)
        return None


def _parse_json3(filepath: Path) -> list[dict[str, Any]]:
    """Parse yt-dlp json3 subtitle format."""
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        segments = []
        for event in data.get("events", []):
            start = event.get("tStartMs", 0) / 1000.0
            duration = event.get("dDurationMs", 0) / 1000.0
            end = start + duration

            # Concatenate all segs text
            text_parts = []
            for seg in event.get("segs", []):
                text_parts.append(seg.get("utf8", ""))
            content = "".join(text_parts).strip()

            if content:
                segments.append(
                    {"from": round(start, 2), "to": round(end, 2), "content": content}
                )

        return segments

    except Exception:
        logger.exception("[subtitle] Failed to parse %s", filepath)
        return []