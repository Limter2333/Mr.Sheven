"""Batch extract reviews from all NEW videos.

Usage:
    python -m pipeline.batch_extract
    python -m pipeline.batch_extract --limit 10  # Process only 10
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import func, select

from pipeline.cleaner.cleaner import clean_subtitle_segments
from pipeline.llm.extract import extract_reviews
from pipeline.normalize.normalizer import normalize_and_save
from pipeline.subtitle.fetcher import fetch_subtitle
from shared.db import SessionLocal
from shared.log_setup import setup_service_logging
from shared.models import VideoReview

# ─── Logging ──────────────────────────────────────────────────────────
# 日志规范化：落盘 ./logs/pipeline/pipeline_run.log
setup_service_logging("pipeline", filename="pipeline_run.log")
logger = logging.getLogger("batch")

# LLM is async; create one event loop for the whole batch
_loop = asyncio.new_event_loop()


def _extract_sync(text: str) -> list[dict]:
    """Sync wrapper for async extract_reviews."""
    return _loop.run_until_complete(extract_reviews(text))


def run_batch(limit: int = 0) -> None:
    db = SessionLocal()
    try:
        total = db.execute(select(func.count(VideoReview.id))).scalar()
        new_count = db.execute(
            select(func.count(VideoReview.id)).where(VideoReview.status == "NEW")
        ).scalar()
    finally:
        db.close()

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("视频评论批量录入")
    logger.info("  总视频: %d | NEW: %d", total, new_count)
    if limit:
        logger.info("  本次最多处理: %d 条", limit)
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    processed = 0
    total_reviews = 0
    errors = 0

    # Get all NEW video IDs first (avoid holding session during slow calls)
    db = SessionLocal()
    try:
        new_ids = db.execute(
            select(VideoReview.id)
            .where(VideoReview.status == "NEW")
            .order_by(VideoReview.id)
        ).scalars().all()
    finally:
        db.close()

    if limit:
        new_ids = new_ids[:limit]

    for idx, video_id in enumerate(new_ids, 1):
        db = SessionLocal()
        try:
            video = db.execute(
                select(VideoReview).where(VideoReview.id == video_id)
            ).scalars().first()
            if not video:
                continue

            logger.info("")
            logger.info("[%d/%d] %s | %s", idx, len(new_ids), video.bvid, video.title[:40])

            # 1. Subtitle
            t0 = time.time()
            segments = fetch_subtitle(video.bvid)
            if not segments:
                video.status = "NO_SUBTITLE"
                video.updated_at = datetime.now()
                db.commit()
                logger.info("  ❌ 无字幕，跳过")
                continue

            # 2. Clean
            clean_text = clean_subtitle_segments(segments)
            video.subtitle_text = clean_text

            # 3. LLM Extract
            t1 = time.time()
            reviews = _extract_sync(clean_text)
            t2 = time.time()

            if not reviews:
                video.status = "NO_REVIEWS"
                video.updated_at = datetime.now()
                db.commit()
                logger.info("  ⚠️ 未提取到评测 (%.0fs subtitle, %.0fs LLM)", t1 - t0, t2 - t1)
                continue

            # 4. Normalize & Save
            saved = normalize_and_save(db, video.id, video.mid, reviews)
            video.status = "EXTRACTED"
            video.updated_at = datetime.now()
            db.commit()

            total_reviews += saved
            processed += 1
            logger.info(
                "  ✅ %d reviews → %d saved (total: %d) [%.0fs sub, %.0fs LLM]",
                len(reviews), saved, total_reviews, t1 - t0, t2 - t1,
            )

        except Exception as e:
            errors += 1
            logger.error("  ❌ Error: %s", e)
            try:
                video.status = "FAILED"
                video.fail_reason = str(e)[:200]
                video.retry_count += 1
                video.updated_at = datetime.now()
                db.commit()
            except Exception:
                pass
        finally:
            db.close()

    logger.info("")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("批量录入完成")
    logger.info("  处理: %d | 提取评测: %d | 失败: %d", processed, total_reviews, errors)
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch extract reviews from videos")
    parser.add_argument("--limit", type=int, default=0, help="Max videos to process (0=all)")
    args = parser.parse_args()
    run_batch(limit=args.limit)


if __name__ == "__main__":
    main()
