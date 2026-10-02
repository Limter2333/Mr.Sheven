"""Daily monitoring report job.

Metrics (from 06 doc section 十):
    - Pipeline status counts (NEW/CLEANED/EXTRACTED/FAILED/etc.)
    - LLM failure/retry rate
    - Scan counts and hit rate
    - NOT_FOUND Top20 barcodes (= missing data priority list)
    - Third-party API quota
    - Cookies health check
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db import SessionLocal
from shared.models import ScanLog, VideoReview

logger = logging.getLogger("pipeline.monitor")


def generate_daily_report(db: Session) -> dict:
    """Generate daily monitoring report.

    Returns:
        Dict with all metrics
    """
    now = datetime.now()
    yesterday = now - timedelta(days=1)

    # Pipeline status counts
    pipeline_stats = {}
    for status in [
        "NEW", "NO_SUBTITLE", "CLEANED", "DUP_SUSPECT",
        "EXTRACTING", "EXTRACTED", "DISCARDED", "FAILED",
    ]:
        count = db.execute(
            select(func.count(VideoReview.id)).where(VideoReview.status == status)
        ).scalar()
        pipeline_stats[status] = count or 0

    # LLM failure rate
    total_failed = db.execute(
        select(func.count(VideoReview.id)).where(VideoReview.status == "FAILED")
    ).scalar() or 0
    total_processed = db.execute(
        select(func.count(VideoReview.id)).where(
            VideoReview.status.in_(["EXTRACTED", "DISCARDED", "FAILED"])
        )
    ).scalar() or 0
    failure_rate = (total_failed / total_processed * 100) if total_processed > 0 else 0

    # Scan stats (last 24h)
    scan_count = db.execute(
        select(func.count(ScanLog.id)).where(ScanLog.created_at >= yesterday)
    ).scalar() or 0

    hit_count = db.execute(
        select(func.count(ScanLog.id)).where(
            ScanLog.created_at >= yesterday,
            ScanLog.result_type == "HIT_REVIEW",
        )
    ).scalar() or 0

    hit_rate = (hit_count / scan_count * 100) if scan_count > 0 else 0

    # NOT_FOUND Top20 barcodes
    not_found = db.execute(
        select(ScanLog.barcode, func.count(ScanLog.id).label("cnt"))
        .where(
            ScanLog.created_at >= yesterday,
            ScanLog.result_type == "NOT_FOUND",
        )
        .group_by(ScanLog.barcode)
        .order_by(func.count(ScanLog.id).desc())
        .limit(20)
    ).all()

    report = {
        "date": now.strftime("%Y-%m-%d"),
        "pipeline": pipeline_stats,
        "llm_failure_rate": round(failure_rate, 2),
        "scan_count_24h": scan_count,
        "hit_count_24h": hit_count,
        "hit_rate_24h": round(hit_rate, 2),
        "not_found_top20": [{"barcode": bc, "count": cnt} for bc, cnt in not_found],
    }

    logger.info("[monitor] Daily report generated: %s", report)
    return report


def run_daily_report() -> None:
    """Run daily report and log results."""
    db = SessionLocal()
    try:
        report = generate_daily_report(db)
        # TODO: Send via email/Bark/push notification
        print(f"\n{'='*50}")
        print(f"📊 Mr.Sheven Daily Report - {report['date']}")
        print(f"{'='*50}")
        print(f"Pipeline: {report['pipeline']}")
        print(f"LLM Failure Rate: {report['llm_failure_rate']}%")
        print(f"Scans (24h): {report['scan_count_24h']}")
        print(f"Hits (24h): {report['hit_count_24h']} ({report['hit_rate_24h']}%)")
        if report["not_found_top20"]:
            print(f"NOT_FOUND Top Barcodes:")
            for item in report["not_found_top20"][:5]:
                print(f"  {item['barcode']}: {item['count']}次")
        print(f"{'='*50}\n")
    finally:
        db.close()