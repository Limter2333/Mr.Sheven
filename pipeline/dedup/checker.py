"""Three-layer deduplication checker.

Layers (from 06 doc section 五·3):
    1. uk_bvid (hard) - already handled by INSERT IGNORE in crawler
    2. Title hash comparison within same UP主 - rapidfuzz token_set_ratio >= 90
    3. uk_mid_day_title (hard) - requires pubdate_date generated column

Cross-UP主 transfer detection:
    - Same title_hash but different mid → don't hard block
    - Compare subtitle text similarity >= 95% → discard as transfer
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import VideoReview

logger = logging.getLogger("pipeline.dedup")

# Thresholds
TITLE_SIMILARITY_THRESHOLD = 90  # token_set_ratio >= 90 → DUP_SUSPECT
TRANSFER_SIMILARITY_THRESHOLD = 95  # text similarity >= 95 → discard as transfer


class DedupResult:
    """Result of deduplication check."""

    def __init__(
        self,
        action: Literal["pass", "dup_suspect", "transfer_discard"],
        reason: str = "",
        similar_video_id: int | None = None,
    ):
        self.action = action
        self.reason = reason
        self.similar_video_id = similar_video_id

    def __repr__(self) -> str:
        return f"DedupResult(action={self.action!r}, reason={self.reason!r})"


def check_duplicate(
    db: Session,
    mid: int,
    bvid: str,
    title_clean: str,
    title_hash: str,
    subtitle_text: str | None = None,
) -> DedupResult:
    """Check if a video is a duplicate.

    Args:
        db: SQLAlchemy session
        mid: UP主 ID
        bvid: Video BV ID
        title_clean: Cleaned title
        title_hash: MD5 hash of cleaned title
        subtitle_text: Cleaned subtitle text (for cross-UP主 comparison)

    Returns:
        DedupResult with action: 'pass', 'dup_suspect', or 'transfer_discard'
    """
    # Layer 1: uk_bvid - already handled by crawler INSERT IGNORE
    # Layer 2: Title hash within same UP主
    similar = _find_similar_by_title(db, mid, title_hash, bvid)
    if similar:
        logger.info(
            "[dedup] DUP_SUSPECT: BVID=%s similar to BVID=%s (same UP主, title match)",
            bvid,
            similar.bvid,
        )
        return DedupResult(
            action="dup_suspect",
            reason=f"Similar title to BVID={similar.bvid}",
            similar_video_id=similar.id,
        )

    # Layer 3: Cross-UP主 transfer detection
    if subtitle_text:
        transfer = _check_cross_uploader_transfer(db, mid, title_hash, subtitle_text)
        if transfer:
            logger.info(
                "[dedup] TRANSFER_DISCARD: BVID=%s is transfer from BVID=%s",
                bvid,
                transfer.bvid,
            )
            return DedupResult(
                action="transfer_discard",
                reason=f"Cross-UP主 transfer from BVID={transfer.bvid}",
                similar_video_id=transfer.id,
            )

    return DedupResult(action="pass")


def _find_similar_by_title(
    db: Session, mid: int, title_hash: str, current_bvid: str
) -> VideoReview | None:
    """Find videos with same/ similar title from same UP主."""
    # Exact title_hash match
    stmt = (
        select(VideoReview)
        .where(
            VideoReview.mid == mid,
            VideoReview.title_hash == title_hash,
            VideoReview.bvid != current_bvid,
        )
        .limit(5)
    )
    result = db.execute(stmt).scalars().first()
    if result:
        return result

    # Fuzzy title matching (rapidfuzz)
    stmt = select(VideoReview).where(
        VideoReview.mid == mid,
        VideoReview.bvid != current_bvid,
        VideoReview.title_clean.isnot(None),
    )
    candidates = db.execute(stmt).scalars().all()

    for candidate in candidates:
        if candidate.title_clean:
            ratio = fuzz.token_set_ratio(title_hash, candidate.title_hash or "")
            if ratio >= TITLE_SIMILARITY_THRESHOLD:
                return candidate

    return None


def _check_cross_uploader_transfer(
    db: Session, mid: int, title_hash: str, subtitle_text: str
) -> VideoReview | None:
    """Check if this video is a transfer from another UP主."""
    # Find videos with same title_hash from different UP主
    stmt = select(VideoReview).where(
        VideoReview.mid != mid,
        VideoReview.title_hash == title_hash,
        VideoReview.subtitle_text.isnot(None),
    )
    candidates = db.execute(stmt).scalars().all()

    for candidate in candidates:
        if candidate.subtitle_text:
            ratio = fuzz.ratio(subtitle_text[:1000], candidate.subtitle_text[:1000])
            if ratio >= TRANSFER_SIMILARITY_THRESHOLD:
                return candidate

    return None