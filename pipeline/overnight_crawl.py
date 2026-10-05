"""Overnight crawl runner: crawls videos + logs everything to file.

Tracks B站 rate-limit cooldown duration for analysis.

Usage:
    python -m pipeline.overnight_crawl
    python -m pipeline.overnight_crawl --hours 8
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

from pipeline.crawler.client import fetch_video_list, save_videos
from shared.db import SessionLocal
from shared.log_setup import log_dir, setup_service_logging
from shared.models import VideoReview

# ─── File logging setup ───────────────────────────────────────────────
# 日志规范化：落盘 ./logs/pipeline/crawl_overnight.log
LOG_FILE = log_dir("pipeline") / "crawl_overnight.log"
SUMMARY_FILE = log_dir("pipeline") / "crawl_overnight_summary.txt"

setup_service_logging("pipeline", filename="crawl_overnight.log")
logger = logging.getLogger("overnight")


# ─── Rate-limit tracker ──────────────────────────────────────────────
class RateLimitTracker:
    """Track rate-limit events and cooldown durations."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._blocked_since: float | None = None

    def record_blocked(self, reason: str) -> None:
        now = time.time()
        self._blocked_since = now
        self.events.append({
            "time": datetime.now().isoformat(),
            "event": "BLOCKED",
            "reason": reason,
            "timestamp": now,
        })
        logger.warning("⛔ RATE LIMITED (%s) at %s", reason, datetime.now().strftime("%H:%M:%S"))

    def record_unblocked(self) -> None:
        now = time.time()
        cooldown = now - self._blocked_since if self._blocked_since else 0
        self.events.append({
            "time": datetime.now().isoformat(),
            "event": "UNBLOCKED",
            "cooldown_seconds": round(cooldown, 1),
            "cooldown_readable": str(timedelta(seconds=int(cooldown))),
            "timestamp": now,
        })
        logger.info(
            "✅ UNBLOCKED after cooldown: %.0fs (%s)",
            cooldown,
            str(timedelta(seconds=int(cooldown))),
        )
        self._blocked_since = None

    def is_blocked(self) -> bool:
        return self._blocked_since is not None

    def summary(self) -> str:
        if not self.events:
            return "No rate-limit events recorded."
        lines = ["", "=" * 60, "RATE LIMIT ANALYSIS", "=" * 60]
        blocked = [e for e in self.events if e["event"] == "BLOCKED"]
        unblocked = [e for e in self.events if e["event"] == "UNBLOCKED"]
        lines.append(f"Total blocks: {len(blocked)}")
        lines.append(f"Total unblocks: {len(unblocked)}")
        if unblocked:
            cooldowns = [e["cooldown_seconds"] for e in unblocked]
            lines.append(f"Cooldowns: {cooldowns}")
            lines.append(f"Cooldowns (readable): {[e['cooldown_readable'] for e in unblocked]}")
            lines.append(f"Min cooldown: {min(cooldowns):.0f}s")
            lines.append(f"Max cooldown: {max(cooldowns):.0f}s")
            lines.append(f"Avg cooldown: {sum(cooldowns)/len(cooldowns):.0f}s")
        lines.append("")
        lines.append("Event timeline:")
        for e in self.events:
            if e["event"] == "BLOCKED":
                lines.append(f"  {e['time']}  BLOCKED ({e['reason']})")
            else:
                lines.append(f"  {e['time']}  UNBLOCKED (cooldown={e['cooldown_readable']})")
        lines.append("=" * 60)
        return "\n".join(lines)


tracker = RateLimitTracker()


# ─── Probe: single request to test if unblocked ──────────────────────
def probe_unblocked() -> bool:
    """Send a single lightweight request to check if rate limit has lifted."""
    import httpx

    from pipeline.crawler.client import _build_headers, _load_cookie_str

    cookie_str = _load_cookie_str()
    mid = 97282565  # probe target
    headers = _build_headers(mid, cookie_str)

    try:
        with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
            resp = client.get(
                "https://api.bilibili.com/x/space/arc/search",
                params={"mid": mid, "ps": 1, "pn": 1, "order": "pubdate"},
            )
        if resp.status_code == 412:
            logger.info("  Probe: still blocked (412)")
            return False
        data = resp.json()
        code = data.get("code")
        if code == 0:
            logger.info("  Probe: ✅ unblocked (code=0)")
            return True
        elif code == -799:
            logger.info("  Probe: still blocked (-799)")
            return False
        else:
            logger.info("  Probe: code=%s", code)
            return code == 0
    except Exception as exc:
        logger.warning("  Probe error: %s", exc)
        return False


# ─── Main overnight loop ─────────────────────────────────────────────
def run_overnight(hours: float = 8.0, max_pages_per_round: int = 2) -> None:
    """Crawl overnight, logging everything, measuring cooldowns."""
    from shared.config import config

    deadline = datetime.now() + timedelta(hours=hours)
    mids = config.bilibili.uploader_mids

    logger.info("🚀 Overnight crawl started")
    logger.info("   Duration: %s hours | Deadline: %s", hours, deadline.strftime("%H:%M:%S"))
    logger.info("   UP主 mids: %s", mids)
    logger.info("   Log file: %s", LOG_FILE)
    logger.info("   Max pages per round: %d", max_pages_per_round)

    round_num = 0
    total_inserted = 0
    caught_up_until: dict[int, datetime] = {}  # mid → skip until this time

    while datetime.now() < deadline:
        round_num += 1
        logger.info("")
        logger.info("── Round %d ── %s", round_num, datetime.now().strftime("%H:%M:%S"))

        round_got_data = False
        round_blocked = False

        for mid in mids:
            if datetime.now() >= deadline:
                break

            # Skip if we already caught up recently
            if mid in caught_up_until and datetime.now() < caught_up_until[mid]:
                remaining = (caught_up_until[mid] - datetime.now()).total_seconds()
                logger.info("  mid=%d: caught up, skipping for another %.0f min", mid, remaining / 60)
                continue

            # Find newest video we already have
            db = SessionLocal()
            try:
                last_pubdate = db.execute(
                    select(func.max(VideoReview.pubdate)).where(VideoReview.mid == mid)
                ).scalar()
                count = db.execute(
                    select(func.count(VideoReview.id)).where(VideoReview.mid == mid)
                ).scalar() or 0
            finally:
                db.close()

            logger.info("  mid=%d: %d videos in DB, last_pubdate=%s", mid, count, last_pubdate)

            page = 1
            pages_done = 0
            while pages_done < max_pages_per_round and datetime.now() < deadline:
                # Human-like delay before each request
                delay = random.uniform(2, 5)
                logger.info("  Pre-request delay: %.1fs", delay)
                time.sleep(delay)

                result = fetch_video_list(mid, page=page, page_size=20)

                # ── Rate limit detection ──
                if result.status == "rate_limited":
                    tracker.record_blocked("-799")
                    round_blocked = True
                    break
                if result.status == "blocked_412":
                    tracker.record_blocked("412")
                    round_blocked = True
                    break
                if result.status == "error":
                    logger.warning("  Fetch error for mid=%d page=%d", mid, page)
                    break

                videos = result.videos
                if not videos:
                    logger.info("  End of video list for mid=%d page=%d", mid, page)
                    break

                # Filter out already-known videos
                if last_pubdate:
                    new_videos = [v for v in videos if v["pubdate"] > last_pubdate]
                    if len(new_videos) < len(videos):
                        logger.info(
                            "  page=%d: %d/%d new, %d already in DB",
                            page, len(new_videos), len(videos), len(videos) - len(new_videos),
                        )
                    if not new_videos:
                        logger.info("  ✅ Caught up! All videos up to date for mid=%d", mid)
                        # Mark as caught up — don't waste requests on this mid again soon
                        caught_up_until[mid] = datetime.now() + timedelta(hours=3)
                        logger.info("  ⏭️  Skipping mid=%d until %s", mid, caught_up_until[mid].strftime("%H:%M:%S"))
                        break
                    videos = new_videos

                db = SessionLocal()
                try:
                    inserted = save_videos(db, videos)
                    total_inserted += inserted
                    if inserted > 0:
                        round_got_data = True
                    logger.info("  💾 Inserted %d new videos (total: %d)", inserted, total_inserted)
                finally:
                    db.close()

                pages_done += 1
                if inserted == 0:
                    logger.info("  0 new inserts, moving on")
                    break

                page += 1
                # Long random delay between pages
                page_delay = random.uniform(30, 60)
                logger.info("  Page done. Resting %.0fs before next page", page_delay)
                time.sleep(page_delay)

        # ── Post-round: handle rate limiting ──
        if round_blocked:
            logger.info("⏳ Rate limited! Probing every 2 minutes to measure cooldown...")
            probe_interval = 120  # seconds
            while datetime.now() < deadline:
                time.sleep(probe_interval)
                logger.info("  Probing at %s ...", datetime.now().strftime("%H:%M:%S"))
                if probe_unblocked():
                    tracker.record_unblocked()
                    # Extra warm-up delay before resuming
                    warmup = random.uniform(30, 60)
                    logger.info("  Warm-up delay: %.0fs before resuming", warmup)
                    time.sleep(warmup)
                    break
                else:
                    logger.info("  Still blocked. Next probe in %ds", probe_interval)

        elif datetime.now() < deadline:
            # Normal round complete
            if round_got_data:
                wait = random.uniform(60, 120)
                logger.info("")
                logger.info("Round %d complete. Inserted: %d (total: %d). Next round in %.0fs",
                            round_num, pages_done, total_inserted, wait)
            else:
                # All mids caught up — wait long before checking for new videos
                all_caught_up = all(
                    mid in caught_up_until and datetime.now() < caught_up_until[mid]
                    for mid in mids
                )
                if all_caught_up:
                    wait = random.uniform(1800, 3600)  # 30-60 min when all caught up
                    logger.info("")
                    logger.info("Round %d: all mids caught up. Waiting %.0f min for new videos", round_num, wait / 60)
                else:
                    wait = random.uniform(300, 600)
                    logger.info("")
                    logger.info("Round %d: no new data. Waiting %.0fs", round_num, wait)
            time.sleep(wait)

    # ─── Final report ─────────────────────────────────────────────
    logger.info("")
    logger.info("🏁 Overnight crawl finished at %s", datetime.now().strftime("%H:%M:%S"))
    logger.info("   Total rounds: %d", round_num)
    logger.info("   Total videos inserted: %d", total_inserted)

    summary = tracker.summary()
    logger.info(summary)

    # Also write summary to separate file
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(f"Overnight crawl report - {datetime.now().isoformat()}\n")
        f.write(f"Rounds: {round_num}, Inserted: {total_inserted}\n\n")
        f.write(summary)
    logger.info("📄 Summary written to %s", SUMMARY_FILE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Overnight crawler with rate-limit tracking")
    parser.add_argument("--hours", type=float, default=8.0, help="Run duration in hours (default: 8)")
    parser.add_argument("--pages", type=int, default=2, help="Max pages per round (default: 2)")
    args = parser.parse_args()

    run_overnight(hours=args.hours, max_pages_per_round=args.pages)


if __name__ == "__main__":
    main()
