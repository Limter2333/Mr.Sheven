"""Subtitle fetcher: B站 AI 字幕优先，失败直接跳过（裁决 C8：不做 ASR）.

Flow:
    1. yt-dlp --list-subs 检查是否有 ai-zh 字幕
    2. yt-dlp --write-subs 下载字幕（srt 格式）
    3. 解析 srt → segments 列表
    4. On failure: mark NO_SUBTITLE, log and continue
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from shared.config import config

logger = logging.getLogger("pipeline.subtitle")


def _get_netscape_cookies() -> str:
    """Get path to Netscape-format cookies file for yt-dlp.

    If only raw cookie string exists (cookie.txt), auto-convert to Netscape format.
    """
    import time

    from shared.config import config

    raw_path = config.bilibili.cookies_path
    netscape_path = "cookies_netscape.txt"

    # Always regenerate from raw cookie.txt to keep in sync
    try:
        with open(raw_path, encoding="utf-8") as f:
            raw = f.read().strip()

        cookies = {}
        for pair in raw.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, val = pair.split("=", 1)
                cookies[key.strip()] = val.strip()

        expires = str(int(time.time()) + 86400 * 365)
        lines = ["# Netscape HTTP Cookie File", "# https://curl.se/rfc/cookie_spec.html", ""]
        for name, value in cookies.items():
            lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}")

        with open(netscape_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return netscape_path
    except Exception:
        logger.warning("[subtitle] Failed to convert cookies, using raw path")
        return raw_path


def fetch_subtitle(bvid: str, cookies_path: str | None = None) -> list[dict[str, Any]] | None:
    """Fetch subtitle for a Bilibili video.

    Args:
        bvid: Bilibili video ID (e.g., "BV1Yjciz3EuE")
        cookies_path: Path to cookies file (Netscape format)

    Returns:
        List of subtitle segments with 'from', 'to', 'content' keys,
        or None if no subtitle available.
    """
    cookies = cookies_path or _get_netscape_cookies()

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
            cmd_list, capture_output=True, timeout=60, check=False
        )
        stdout = result.stdout.decode("utf-8", errors="replace")

        if "ai-zh" not in stdout and "zh-CN" not in stdout:
            logger.info("[subtitle] No Chinese subtitle available for %s", bvid)
            return None

        # Download subtitle
        sub_lang = "ai-zh" if "ai-zh" in stdout else "zh-CN"
        cmd_download = [
            "yt-dlp",
            "--cookies", cookies_path,
            "--write-subs",
            "--sub-langs", sub_lang,
            "--skip-download",
            "-o", str(output_dir / "%(id)s"),
            url,
        ]
        subprocess.run(
            cmd_download, capture_output=True, timeout=120, check=False
        )

        # Find and parse subtitle file (srt or json3)
        for sub_file in list(output_dir.glob("*.srt")) + list(output_dir.glob("*.json3")):
            if sub_file.suffix == ".srt":
                segments = _parse_srt(sub_file)
            else:
                segments = _parse_json3(sub_file)
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


# SRT time format: 00:01:23,456 → seconds
_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _parse_srt(filepath: Path) -> list[dict[str, Any]]:
    """Parse SRT subtitle format into segments."""
    try:
        with open(filepath, encoding="utf-8-sig") as f:
            content = f.read()

        segments = []
        # Split by blank lines (blocks)
        blocks = re.split(r"\n\s*\n", content.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue

            # Line 0: index, Line 1: timing, Line 2+: text
            time_match = _SRT_TIME_RE.search(lines[1])
            if not time_match:
                continue

            g = [int(x) for x in time_match.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0

            text = "\n".join(lines[2:]).strip()
            if text:
                segments.append({
                    "from": round(start, 2),
                    "to": round(end, 2),
                    "content": text,
                })

        return segments

    except Exception:
        logger.exception("[subtitle] Failed to parse SRT %s", filepath)
        return []


def _parse_json3(filepath: Path) -> list[dict[str, Any]]:
    """Parse yt-dlp json3 subtitle format."""
    import json

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        segments = []
        for event in data.get("events", []):
            start = event.get("tStartMs", 0) / 1000.0
            duration = event.get("dDurationMs", 0) / 1000.0
            end = start + duration

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