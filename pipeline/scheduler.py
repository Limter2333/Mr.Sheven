"""Pipeline scheduler: APScheduler-based job runner.

Jobs:
    - 21:30  crawl_job      拉取博主视频列表
    - 22:00  batch_job       夜间跑批（字幕→清洗→查重→LLM→归一化）
    - 03:00  patch_job       补录 NO_SUBTITLE 视频
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline.scheduler")


def crawl_job() -> None:
    """21:30 - 拉取博主视频列表，新视频元数据入 video_review（轻量）."""
    logger.info("[crawl_job] Starting...")
    from shared.db import SessionLocal
    from pipeline.runner import run_crawl

    db = SessionLocal()
    try:
        run_crawl(db)
    finally:
        db.close()
    logger.info("[crawl_job] Done.")


def batch_job() -> None:
    """22:00 - 夜间跑批：字幕→清洗→查重→LLM→归一化."""
    logger.info("[batch_job] Starting...")
    from shared.db import SessionLocal
    from pipeline.runner import run_pipeline

    db = SessionLocal()
    try:
        run_pipeline(db)
    finally:
        db.close()
    logger.info("[batch_job] Done.")


def patch_job() -> None:
    """03:00 - 补录 NO_SUBTITLE 视频再试字幕."""
    logger.info("[patch_job] Starting...")
    from shared.db import SessionLocal
    from pipeline.runner import run_patch

    db = SessionLocal()
    try:
        run_patch(db)
    finally:
        db.close()
    logger.info("[patch_job] Done.")


def daily_report_job() -> None:
    """08:00 - 生成并推送日报."""
    logger.info("[daily_report] Starting...")
    from pipeline.monitor import run_daily_report

    run_daily_report()
    logger.info("[daily_report] Done.")


def main() -> None:
    """Start the APScheduler with four nightly jobs."""
    scheduler = BlockingScheduler()

    scheduler.add_job(crawl_job, CronTrigger(hour=21, minute=30), id="crawl")
    scheduler.add_job(batch_job, CronTrigger(hour=22, minute=0), id="batch")
    scheduler.add_job(patch_job, CronTrigger(hour=3, minute=0), id="patch")
    scheduler.add_job(daily_report_job, CronTrigger(hour=8, minute=0), id="daily_report")

    logger.info("Scheduler started. Jobs: crawl(21:30), batch(22:00), patch(03:00), report(08:00)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
        scheduler.shutdown()