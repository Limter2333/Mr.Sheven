"""Text cleaner: remove timestamps, garbage, and ad patterns from subtitle text.

Rules:
    - Remove timestamp markers ([00:00] style)
    - Remove common opening/closing phrases
    - Remove ad/sponsor segments
    - Normalize whitespace
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger("pipeline.cleaner")

# Configurable blacklist phrases (ad/求三连/开场白)
BLACKLIST_PHRASES = [
    "求三连",
    "一键三连",
    "点赞投币收藏",
    "点赞关注",
    "感谢观看",
    "感谢收看",
    "我们下期再见",
    "下期再见",
    "拜拜",
    "本期视频",
    "本视频",
    "赞助商",
    "广告",
    "推广",
    "优惠券",
    "专属链接",
    "点击链接",
    "扫码",
    "关注我的",
    "关注我",
]

# Timestamp patterns
TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\]")
TIMESTAMP_RE2 = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")

# Garbage patterns
GARBAGE_RE = re.compile(r"[♪♫♬🎵🎶​‌‍﻿]")
MULTI_SPACE_RE = re.compile(r"\s{2,}")


def clean_subtitle_text(raw_text: str) -> str:
    """Clean raw subtitle text into plain text.

    Args:
        raw_text: Raw subtitle text (may contain timestamps, markers, etc.)

    Returns:
        Cleaned plain text
    """
    if not raw_text:
        return ""

    text = raw_text

    # Remove timestamp markers
    text = TIMESTAMP_RE.sub("", text)
    text = TIMESTAMP_RE2.sub("", text)

    # Remove garbage characters
    text = GARBAGE_RE.sub("", text)

    # Remove blacklist phrases (case-insensitive)
    for phrase in BLACKLIST_PHRASES:
        text = text.replace(phrase, "")

    # Normalize whitespace
    text = MULTI_SPACE_RE.sub(" ", text)
    text = text.strip()

    # Remove empty lines but keep paragraph structure
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    logger.debug("[cleaner] Cleaned text: %d chars → %d chars", len(raw_text), len(text))
    return text


def clean_subtitle_segments(segments: list[dict]) -> str:
    """Clean subtitle segments (from yt-dlp/json3) into a single text block.

    Args:
        segments: List of dicts with 'from', 'to', 'content' keys

    Returns:
        Cleaned plain text with timestamps preserved as comments
    """
    if not segments:
        return ""

    lines = []
    for seg in segments:
        content = seg.get("content", "").strip()
        if not content:
            continue
        # Skip blacklist phrases
        if any(phrase in content for phrase in BLACKLIST_PHRASES):
            continue
        lines.append(content)

    raw_text = "\n".join(lines)
    return clean_subtitle_text(raw_text)