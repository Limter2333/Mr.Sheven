"""SPU normalizer: name normalization, alias matching, and review insertion.

Matching strategy (from 06 doc section 五·6):
    1. Exact match on spu.name
    2. Exact match on spu_alias.alias_norm
    3. rapidfuzz: >= 90 auto-bind (log + insert alias)
    4. 75~89: create new SPU with possible_dup_of
    5. < 75: create new SPU

Write strategy (裁决 C5):
    - New review: INSERT
    - Duplicate with change: INSERT new review with prev_review_id + trend
    - Duplicate no change: DISCARD
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import Review, SPU, SPUAlias

logger = logging.getLogger("pipeline.normalize")

# Thresholds
AUTO_BIND_THRESHOLD = 90
DUP_SUSPECT_THRESHOLD = 75


def _normalize_name(name: str) -> str:
    """Normalize wine name: lowercase, remove symbols."""
    clean = re.sub(r"[^\w\s]", "", name.lower())
    return " ".join(clean.split()).strip()


def normalize_and_save(
    db: Session,
    video_review_id: int,
    mid: int,
    reviews: list[dict[str, Any]],
) -> int:
    """Normalize extracted reviews and save to database.

    Args:
        db: SQLAlchemy session
        video_review_id: ID of the video_review record
        mid: UP主 ID
        reviews: List of extracted review dicts from LLM

    Returns:
        Number of reviews saved
    """
    saved = 0
    for review_data in reviews:
        product_name = review_data.get("product_name_raw", "").strip()
        if not product_name:
            continue

        # Find or create SPU
        spu = _find_or_create_spu(db, product_name, review_data)
        if not spu:
            continue

        # Check for existing review from same UP主 for same SPU
        existing = _find_existing_review(db, spu.id, mid)

        if existing:
            # Check if score changed
            new_score = review_data.get("score_raw")
            old_score = existing.score_raw
            if new_score and old_score and new_score != old_score:
                # Score changed: insert new review with evolution chain
                _insert_review(
                    db, spu.id, video_review_id, mid, review_data,
                    prev_review_id=existing.id,
                    score_trend=_calc_trend(old_score, new_score),
                )
                # Mark old review as not latest
                existing.is_latest = 0
                saved += 1
                logger.info(
                    "[normalize] Score change for %s by mid=%d: %s → %s",
                    product_name, mid, old_score, new_score,
                )
            else:
                # No change: discard (裁决 C5)
                logger.info(
                    "[normalize] Duplicate review for %s by mid=%d, discarding",
                    product_name, mid,
                )
        else:
            # New review
            _insert_review(db, spu.id, video_review_id, mid, review_data)
            saved += 1

    db.commit()
    logger.info("[normalize] Saved %d reviews", saved)
    return saved


def _find_or_create_spu(
    db: Session, product_name: str, review_data: dict[str, Any]
) -> SPU | None:
    """Find existing SPU or create new one."""
    norm_name = _normalize_name(product_name)

    # 1. Exact match on spu.name
    spu = db.execute(select(SPU).where(SPU.name == norm_name)).scalars().first()
    if spu:
        return spu

    # 2. Exact match on spu_alias.alias_norm
    alias = db.execute(
        select(SPUAlias).where(SPUAlias.alias_norm == norm_name)
    ).scalars().first()
    if alias:
        return alias.spu

    # 3. Fuzzy match against all SPU names
    all_spus = db.execute(select(SPU)).scalars().all()
    best_match = None
    best_score = 0

    for candidate in all_spus:
        score = fuzz.token_set_ratio(norm_name, candidate.name)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= AUTO_BIND_THRESHOLD and best_match:
        # Auto-bind: add alias
        _add_alias(db, best_match.id, product_name, norm_name, "llm")
        logger.info(
            "[normalize] Auto-bound %s → %s (score=%d)",
            product_name, best_match.name, best_score,
        )
        return best_match

    # 4. Create new SPU
    new_spu = SPU(
        name=norm_name,
        name_raw=product_name,
        brand=review_data.get("brand"),
        category=review_data.get("category"),
        source="llm_extract",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    if best_score >= DUP_SUSPECT_THRESHOLD and best_match:
        new_spu.possible_dup_of = best_match.id
        logger.info(
            "[normalize] Created SPU %s with possible_dup_of=%d (score=%d)",
            norm_name, best_match.id, best_score,
        )

    db.add(new_spu)
    db.flush()

    # Add alias for raw name
    _add_alias(db, new_spu.id, product_name, norm_name, "llm")

    return new_spu


def _add_alias(db: Session, spu_id: int, alias: str, alias_norm: str, source: str) -> None:
    """Add an alias for an SPU."""
    existing = db.execute(
        select(SPUAlias).where(SPUAlias.alias_norm == alias_norm)
    ).scalars().first()

    if not existing:
        db.add(SPUAlias(
            spu_id=spu_id,
            alias=alias,
            alias_norm=alias_norm,
            source=source,
        ))
        db.flush()


def _find_existing_review(db: Session, spu_id: int, mid: int) -> Review | None:
    """Find existing latest review for this SPU by this UP主."""
    return db.execute(
        select(Review).where(
            Review.spu_id == spu_id,
            Review.mid == mid,
            Review.is_latest == 1,
        )
    ).scalars().first()


def _insert_review(
    db: Session,
    spu_id: int,
    video_review_id: int,
    mid: int,
    review_data: dict[str, Any],
    prev_review_id: int | None = None,
    score_trend: str | None = None,
) -> Review:
    """Insert a new review record."""
    review = Review(
        spu_id=spu_id,
        video_review_id=video_review_id,
        mid=mid,
        score_raw=review_data.get("score_raw"),
        score_type=review_data.get("score_type"),
        verdict=review_data.get("verdict"),
        flavor_tags=review_data.get("flavor_tags"),
        recommend_index=review_data.get("recommend_index"),
        quote=review_data.get("quote"),
        ts_start=review_data.get("timestamp_start"),
        ts_end=review_data.get("timestamp_end"),
        score_trend=score_trend,
        prev_review_id=prev_review_id,
        confidence=Decimal(str(review_data.get("confidence", 0))),
        is_latest=1,
        created_at=datetime.now(),
    )
    db.add(review)
    db.flush()
    return review


def _calc_trend(old_score: str, new_score: str) -> str:
    """Calculate score trend: UP/DOWN/SAME."""
    try:
        old = float(old_score)
        new = float(new_score)
        if new > old:
            return "UP"
        elif new < old:
            return "DOWN"
        return "SAME"
    except ValueError:
        return "SAME"