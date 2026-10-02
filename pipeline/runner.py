"""Pipeline runner: orchestrates the full data pipeline.

Flow (from 06 doc section 五):
    1. Crawl: fetch video list from UP主
    2. Subtitle: fetch AI subtitles
    3. Clean: remove timestamps/ads/garbage
    4. Dedup: three-layer deduplication
    5. LLM Extract: structured extraction
    6. Normalize: SPU matching + review insertion
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.cleaner.cleaner import clean_subtitle_segments
from pipeline.crawler.client import fetch_video_list, save_videos
from pipeline.dedup.checker import check_duplicate
from pipeline.llm.extract import extract_reviews
from pipeline.normalize.normalizer import normalize_and_save
from pipeline.subtitle.fetcher import fetch_subtitle
from shared.db import SessionLocal
from shared.models import VideoReview

logger = logging.getLogger("pipeline.runner")

# List of UP主 mids to track (configurable)
UPLOADER_MIDS: list[int] = []  # TODO: load from config or DB


def run_crawl(db: Session) -> None:
    """Step 1: Crawl UP主 video lists."""
    for mid in UPLOADER_MIDS:
        page = 1
        while True:
            videos = fetch_video_list(mid, page=page, page_size=50)
            if not videos:
                break
            save_videos(db, videos)
            if len(videos) < 50:
                break
            page += 1


def run_pipeline(db: Session) -> None:
    """Run the full pipeline for all NEW videos."""
    # Get all videos waiting for processing
    stmt = (
        select(VideoReview)
        .where(
            VideoReview.status.in_(["NEW", "CLEANED", "DUP_SUSPECT"]),
            VideoReview.retry_count < 3,
        )
        .order_by(VideoReview.created_at)
        .limit(50)  # Process in batches
    )
    videos = db.execute(stmt).scalars().all()

    for video in videos:
        try:
            _process_video(db, video)
        except Exception:
            logger.exception("[runner] Failed to process BVID=%s", video.bvid)
            video.status = "FAILED"
            video.fail_reason = "Pipeline error"
            video.retry_count += 1
            video.updated_at = datetime.now()
            db.commit()


def _process_video(db: Session, video: VideoReview) -> None:
    """Process a single video through the pipeline."""
    logger.info("[runner] Processing BVID=%s status=%s", video.bvid, video.status)

    # Step 2: Subtitle (if NEW)
    if video.status == "NEW":
        if not video.subtitle_text:
            segments = fetch_subtitle(video.bvid)
            if not segments:
                video.status = "NO_SUBTITLE"
                video.updated_at = datetime.now()
                db.commit()
                logger.info("[runner] BVID=%s → NO_SUBTITLE", video.bvid)
                return

            # Step 3: Clean
            from pipeline.cleaner.cleaner import clean_subtitle_text
            raw_text = "\n".join(s.get("content", "") for s in segments)
            video.subtitle_text = clean_subtitle_text(raw_text)

        video.status = "CLEANED"
        video.updated_at = datetime.now()
        db.commit()

    # Step 4: Dedup (if CLEANED or DUP_SUSPECT)
    if video.status in ("CLEANED", "DUP_SUSPECT"):
        dedup_result = check_duplicate(
            db,
            mid=video.mid,
            bvid=video.bvid,
            title_clean=video.title_clean or "",
            title_hash=video.title_hash or "",
            subtitle_text=video.subtitle_text,
        )

        if dedup_result.action == "dup_suspect":
            video.status = "DUP_SUSPECT"
            video.updated_at = datetime.now()
            db.commit()
            # TODO: LLM comparison for suspected duplicates
            logger.info("[runner] BVID=%s → DUP_SUSPECT", video.bvid)
            return
        elif dedup_result.action == "transfer_discard":
            video.status = "DISCARDED"
            video.fail_reason = dedup_result.reason
            video.updated_at = datetime.now()
            db.commit()
            logger.info("[runner] BVID=%s → DISCARDED (transfer)", video.bvid)
            return

    # Step 5: LLM Extract
    if video.status == "CLEANED" and video.subtitle_text:
        video.status = "EXTRACTING"
        video.updated_at = datetime.now()
        db.commit()

        # Run async extraction in sync context
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        reviews = loop.run_until_complete(extract_reviews(video.subtitle_text))

        video.status = "EXTRACTED"
        video.updated_at = datetime.now()
        db.commit()

        # Step 6: Normalize and save
        if reviews:
            normalize_and_save(db, video.id, video.mid, reviews)

        logger.info("[runner] BVID=%s → EXTRACTED (%d reviews)", video.bvid, len(reviews))


def run_patch(db: Session) -> None:
    """Re-try subtitle fetch for NO_SUBTITLE videos."""
    stmt = (
        select(VideoReview)
        .where(VideoReview.status == "NO_SUBTITLE")
        .limit(20)
    )
    videos = db.execute(stmt).scalars().all()

    for video in videos:
        segments = fetch_subtitle(video.bvid)
        if segments:
            raw_text = "\n".join(s.get("content", "") for s in segments)
            video.subtitle_text = clean_subtitle_segments(segments)
            video.status = "NEW"  # Reset to reprocess
            video.updated_at = datetime.now()
            db.commit()
            logger.info("[patch] BVID=%s subtitle found, reset to NEW", video.bvid)