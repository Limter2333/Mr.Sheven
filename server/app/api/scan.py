"""Scan API: barcode-based wine review lookup.

Endpoints:
    GET /api/v1/scan?barcode={code}   - Main lookup
    GET /api/v1/spu/{id}/reviews      - SPU detail with reviews
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.config import config
from shared.db import get_db
from shared.models import Barcode, Review, SPU, SPUAlias, ScanLog
from server.app.cache.multi_cache import cache_get, cache_put
from server.app.ratelimit.limiter import check_rate_limit

logger = logging.getLogger("server.scan")
router = APIRouter()

# Response status codes
STATUS_HIT_REVIEW = "HIT_REVIEW"
STATUS_HIT_NO_REVIEW = "HIT_NO_REVIEW"
STATUS_NOT_WINE = "NOT_WINE"
STATUS_NOT_FOUND = "NOT_FOUND"


@router.get("/scan")
async def scan_barcode(
    request: Request,
    barcode: str = Query(..., description="EAN-13/UPC barcode"),
    db: Session = Depends(get_db),
) -> dict[str, Any] | JSONResponse:
    """Main barcode scan endpoint.

    Flow (from 06 doc section 六):
        1. Rate limiting
        2. L1/L2 cache check
        3. Third-party barcode API
        4. Save to DB + cache
        5. Associate reviews
        6. Assemble response
    """
    # Step 1: Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Try again later."},
        )

    # Step 2: L1/L2 cache check
    cached = await cache_get(barcode)
    if cached:
        return cached

    # Step 3: Check DB
    barcode_record = db.execute(
        select(Barcode).where(Barcode.code == barcode)
    ).scalars().first()

    if barcode_record:
        if barcode_record.is_non_wine:
            resp = _make_response(STATUS_NOT_WINE, barcode=barcode)
            await cache_put(barcode, resp, ttl=604800)  # 7 days
            return resp
        if barcode_record.spu_id:
            resp = _assemble_response(db, barcode_record.spu_id, barcode)
            await cache_put(barcode, resp, ttl=604800)  # 7 days
            return resp
        # Known barcode but no SPU
        resp = _make_response(STATUS_NOT_FOUND, barcode=barcode)
        await cache_put(barcode, resp, ttl=300)  # 5 min (empty marker)
        return resp

    # Step 3: Query third-party barcode API
    api_result = await _query_barcode_api(barcode)

    if api_result is None:
        # Not found in API
        _save_barcode(db, barcode, is_non_wine=False, source="api")
        _log_scan(db, barcode, STATUS_NOT_FOUND)
        resp = _make_response(STATUS_NOT_FOUND, barcode=barcode)
        await cache_put(barcode, resp, ttl=300)  # 5 min empty marker
        return resp

    if not api_result.get("is_wine", True):
        # Not a wine product
        _save_barcode(db, barcode, is_non_wine=True, source="api", raw=api_result)
        _log_scan(db, barcode, STATUS_NOT_WINE)
        resp = _make_response(STATUS_NOT_WINE, barcode=barcode)
        await cache_put(barcode, resp, ttl=604800)  # 7 days
        return resp

    # Step 4: Save wine info and try to match SPU
    spu = _match_or_create_spu(db, api_result)
    _save_barcode(db, barcode, spu_id=spu.id if spu else None, source="api", raw=api_result)

    # Step 5 & 6: Associate reviews and respond
    if spu:
        resp = _assemble_response(db, spu.id, barcode)
        await cache_put(barcode, resp, ttl=604800)
        return resp

    _log_scan(db, barcode, STATUS_NOT_FOUND)
    resp = _make_response(STATUS_NOT_FOUND, barcode=barcode)
    await cache_put(barcode, resp, ttl=300)
    return resp


@router.get("/spu/{spu_id}/reviews")
async def get_spu_reviews(spu_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get SPU detail with all latest reviews."""
    spu = db.get(SPU, spu_id)
    if not spu:
        return {"error": "SPU not found"}

    reviews = db.execute(
        select(Review).where(Review.spu_id == spu_id, Review.is_latest == 1)
    ).scalars().all()

    return {
        "spu": _spu_to_dict(spu),
        "reviews": [_review_to_dict(r) for r in reviews],
    }


def _assemble_response(db: Session, spu_id: int, barcode: str) -> dict[str, Any]:
    """Assemble scan response with wine info and reviews."""
    spu = db.get(SPU, spu_id)
    reviews = db.execute(
        select(Review).where(Review.spu_id == spu_id, Review.is_latest == 1)
    ).scalars().all()

    if reviews:
        _log_scan(db, barcode, STATUS_HIT_REVIEW)
        return _make_response(
            STATUS_HIT_REVIEW,
            wine=_spu_to_dict(spu) if spu else None,
            reviews=[_review_to_dict(r) for r in reviews],
            barcode=barcode,
        )
    else:
        _log_scan(db, barcode, STATUS_HIT_NO_REVIEW)
        return _make_response(
            STATUS_HIT_NO_REVIEW,
            wine=_spu_to_dict(spu) if spu else None,
            barcode=barcode,
        )


def _make_response(status: str, **kwargs: Any) -> dict[str, Any]:
    """Build standard response envelope."""
    resp: dict[str, Any] = {"status": status}
    resp["wine"] = kwargs.get("wine")
    resp["reviews"] = kwargs.get("reviews", [])
    resp["fallback"] = kwargs.get("fallback", [])
    return resp


def _spu_to_dict(spu: SPU) -> dict[str, Any]:
    """Convert SPU to dict."""
    return {
        "id": spu.id,
        "name": spu.name,
        "brand": spu.brand,
        "category": spu.category,
        "country": spu.country,
        "region": spu.region,
        "abv": float(spu.abv) if spu.abv else None,
        "volume_ml": spu.volume_ml,
    }


def _review_to_dict(review: Review) -> dict[str, Any]:
    """Convert Review to dict."""
    return {
        "id": review.id,
        "mid": review.mid,
        "score_raw": review.score_raw,
        "score_type": review.score_type,
        "verdict": review.verdict,
        "flavor_tags": review.flavor_tags,
        "recommend_index": review.recommend_index,
        "quote": review.quote,
        "ts_start": review.ts_start,
        "ts_end": review.ts_end,
        "score_trend": review.score_trend,
        "trend_reason": review.trend_reason,
        "confidence": float(review.confidence) if review.confidence else None,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


async def _query_barcode_api(barcode: str) -> dict[str, Any] | None:
    """Query third-party barcode API for product info."""
    # Placeholder - implement actual API call
    # For MVP, try Open Food Facts (free)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    product = data.get("product", {})
                    categories = product.get("categories_tags", [])
                    is_wine = any(
                        "wine" in c or "alcohol" in c or "spirits" in c
                        for c in categories
                    )
                    return {
                        "name": product.get("product_name", ""),
                        "brand": product.get("brands", ""),
                        "category": product.get("categories", ""),
                        "is_wine": is_wine,
                        "raw": data,
                    }
        return None
    except Exception:
        logger.exception("[scan] Barcode API error for %s", barcode)
        return None


def _save_barcode(
    db: Session,
    code: str,
    spu_id: int | None = None,
    is_non_wine: bool = False,
    source: str = "api",
    raw: dict | None = None,
) -> None:
    """Save barcode record."""
    record = Barcode(
        code=code,
        spu_id=spu_id,
        is_non_wine=1 if is_non_wine else 0,
        raw_json=raw,
        source=source,
        created_at=datetime.now(),
    )
    db.merge(record)
    db.commit()


def _match_or_create_spu(db: Session, api_result: dict[str, Any]) -> SPU | None:
    """Try to match barcode product to existing SPU."""
    name = api_result.get("name", "").strip()
    if not name:
        return None

    from pipeline.normalize.normalizer import _normalize_name
    norm_name = _normalize_name(name)

    # Try exact match
    spu = db.execute(select(SPU).where(SPU.name == norm_name)).scalars().first()
    if spu:
        return spu

    # Try alias match
    alias = db.execute(
        select(SPUAlias).where(SPUAlias.alias_norm == norm_name)
    ).scalars().first()
    if alias:
        return alias.spu

    # Don't create new SPU from barcode API alone (needs LLM validation)
    return None


def _log_scan(db: Session, barcode: str, result_type: str) -> None:
    """Log scan event."""
    log = ScanLog(
        barcode=barcode,
        result_type=result_type,
        ip_hash=hashlib.sha256(b"unknown").hexdigest(),  # TODO: get real IP
        created_at=datetime.now(),
    )
    db.add(log)
    db.commit()