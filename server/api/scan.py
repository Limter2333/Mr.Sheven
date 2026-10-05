"""Scan API: wine review lookup.

Endpoints:
    GET  /api/v1/scan?barcode={code}  - 条码链路（快速通道/辅助通道）
    POST /api/v1/scan-label           - OCR 中文背标主链路（裁决 C12）
    GET  /api/v1/spu/{id}/reviews     - SPU detail with reviews
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.middleware.limiter import check_rate_limit
from server.middleware.multi_cache import cache_get, cache_put
from server.services.label_match import (
    extract_label_fields,
    judge_match,
    pick_candidates,
)
from server.services.ocr import (
    OCRError,
    OCRUnavailableError,
    ocr_image,
)
from shared.config import config
from shared.db import get_db
from shared.models import SPU, Barcode, Review, ScanLog, SPUAlias

logger = logging.getLogger("server.scan")
router = APIRouter()

# Response status codes
STATUS_HIT_REVIEW = "HIT_REVIEW"
STATUS_HIT_NO_REVIEW = "HIT_NO_REVIEW"
STATUS_NOT_WINE = "NOT_WINE"
STATUS_NOT_FOUND = "NOT_FOUND"


@router.get("/scan", response_model=None)
async def scan_barcode(
    request: Request,
    barcode: str = Query(..., description="EAN-13/UPC barcode"),
    db: Session = Depends(get_db),
):
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

    # Product found but no matching SPU/reviews — return product info as fallback
    _log_scan(db, barcode, STATUS_NOT_FOUND)
    fallback_info = [{
        "name": api_result.get("name", ""),
        "brand": api_result.get("brand", ""),
        "category": api_result.get("category", ""),
        "source": api_result.get("source", ""),
    }]
    resp = _make_response(STATUS_NOT_FOUND, barcode=barcode, fallback=fallback_info)
    await cache_put(barcode, resp, ttl=300)
    return resp


@router.post("/scan-label", response_model=None)
async def scan_label(
    request: Request,
    image: UploadFile | None = File(None),
    text: str | None = Form(None),
    barcode: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """OCR 中文背标主链路（裁决 C12）。

    流程（06 文档六·请求处理流·OCR 主链路）：
        1. 限流（5 次/分/IP，OCR+LLM 有真实成本）
        2. OCR（阿里云读光/qwen-vl-ocr）→ 背标全文；text 透传可跳过（调试）
        3. LLM 结构化提取（缺失字段置 null，不猜）
        4. 三档语义匹配 EXACT/SERIES/NONE（宁可不绑也不乱绑）
        5. 自增长回写 barcode↔SPU 绑定
        6. 组装响应（scan 统一信封 + match_level + ocr_fields）
    """
    client_ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit(client_ip, limit=5, scope="label"):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Try again later."},
        )

    # Step 2: OCR（text 透传优先，便于无 OCR 额度时调试全链路）
    if text and text.strip():
        ocr_text = text.strip()
    elif image is not None:
        image_bytes = await image.read()
        try:
            ocr_text = await ocr_image(
                image_bytes, image.content_type or "image/jpeg"
            )
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except OCRUnavailableError as e:
            return JSONResponse(status_code=503, content={"error": str(e)})
        except OCRError as e:
            return JSONResponse(status_code=502, content={"error": str(e)})
    else:
        return JSONResponse(
            status_code=400, content={"error": "请上传酒标图片或提供 text（调试）"}
        )

    # Step 3: LLM 结构化提取
    try:
        fields = await extract_label_fields(ocr_text)
    except (RuntimeError, ValueError) as e:
        return JSONResponse(status_code=502, content={"error": f"酒标提取失败: {e}"})

    product_name = (fields.get("product_name") or "").strip()
    if not product_name:
        resp = _make_response(STATUS_NOT_FOUND, barcode=barcode)
        resp["match_level"] = "NONE"
        resp["ocr_fields"] = fields
        resp["reason"] = "未识别到品名，请重拍（避反光、让背标占满取景框）"
        _log_scan(db, barcode, STATUS_NOT_FOUND)
        return resp

    # Step 4: 三档语义匹配
    all_spus = db.execute(select(SPU)).scalars().all()
    candidates = pick_candidates(all_spus, fields)
    match = await judge_match(fields, [c for c, _ in candidates])

    if match.match_level == "NONE" or not match.spu_id:
        from pipeline.normalize.normalizer import _strip_asr_particles

        fallback = [
            {
                "spu_id": c.id,
                "name": _strip_asr_particles(str(c.name or "")),
                "brand": c.brand,
                "score": round(s, 1),
            }
            for c, s in candidates[:3]
        ]
        resp = _make_response(STATUS_NOT_FOUND, barcode=barcode, fallback=fallback)
        resp["match_level"] = "NONE"
        resp["ocr_fields"] = fields
        resp["reason"] = match.reason
        _log_scan(db, barcode, STATUS_NOT_FOUND)
        return resp

    # Step 5: 自增长回写 barcode↔SPU 绑定（同瓶下次扫码走快速通道）
    # 仅 EXACT 才绑定；SERIES 是同系列另一款，绑了就是乱绑（宁可不绑）
    if barcode and match.match_level == "EXACT":
        _save_barcode(
            db, barcode.strip(), spu_id=match.spu_id,
            source="ocr_bind", raw={"ocr_fields": fields, "match": match.match_level},
        )

    # Step 6: 组装（SERIES 在 scan_log 记 SERIES 维度，反哺抓取优先级）
    log_type = "SERIES" if match.match_level == "SERIES" else None
    resp = _assemble_response(db, match.spu_id, barcode, log_type=log_type)
    resp["match_level"] = match.match_level
    resp["ocr_fields"] = fields
    resp["reason"] = match.reason
    resp["confidence"] = match.confidence
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


def _assemble_response(
    db: Session,
    spu_id: int,
    barcode: str | None,
    log_type: str | None = None,
) -> dict[str, Any]:
    """Assemble scan response with wine info and reviews.

    log_type: scan_log.result_type 覆盖（SERIES 命中记 SERIES 维度）；
              None 时按是否命中评测记 HIT_REVIEW / HIT_NO_REVIEW。
    """
    spu = db.get(SPU, spu_id)
    reviews = db.execute(
        select(Review).where(Review.spu_id == spu_id, Review.is_latest == 1)
    ).scalars().all()

    if reviews:
        _log_scan(db, barcode, log_type or STATUS_HIT_REVIEW)
        return _make_response(
            STATUS_HIT_REVIEW,
            wine=_spu_to_dict(spu) if spu else None,
            reviews=[_review_to_dict(r) for r in reviews],
            barcode=barcode,
        )
    else:
        _log_scan(db, barcode, log_type or STATUS_HIT_NO_REVIEW)
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
    from pipeline.normalize.normalizer import _strip_asr_particles

    return {
        "id": spu.id,
        # 展示名剥 ASR 尾音（库内历史名如"奥兰小红帽珍藏哈"）
        "name": _strip_asr_particles(spu.name) if spu.name else spu.name,
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
    """Query third-party barcode API for product info.

    Routing:
        69 开头 13 位 / 069 开头 14 位 → Aliyun (国内商品)
        其他 → Open Food Facts (国际商品)
    """
    if _is_chinese_domestic_barcode(barcode):
        result = await _query_aliyun(barcode)
        if result:
            return result
        # 阿里云没查到，再试 Open Food Facts 兜底
        return await _query_openfoodfacts(barcode)
    else:
        return await _query_openfoodfacts(barcode)


def _is_chinese_domestic_barcode(barcode: str) -> bool:
    """判断是否为国内商品条码（阿里云 API 支持范围）。

    支持格式：
        - 69 开头的 13 位 EAN-13
        - 069 开头的 14 位 UPC-A / ITF-14
    """
    code = barcode.strip()
    return (
        (len(code) == 13 and code.startswith("69"))
        or (len(code) == 14 and code.startswith("069"))
    )


async def _query_aliyun(barcode: str) -> dict[str, Any] | None:
    """Query Aliyun barcode API (showapi).

    API: GET {url}?code={barcode}
    Auth: Authorization:APPCODE {appcode}
    Response: showapi_res_body.flag=true 表示查到商品
    """
    cfg = config.barcode_api
    if not cfg.appcode:
        logger.warning("[scan] BARCODE_API_KEY not set, skip Aliyun barcode API")
        return None

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.get(
                cfg.url,
                params={"code": barcode},
                headers={"Authorization": f"APPCODE {cfg.appcode}"},
            )
            resp.raise_for_status()
            data = resp.json()

        body = data.get("showapi_res_body", {})
        if not body.get("flag"):
            logger.info("[scan] Aliyun: %s not found (%s)", barcode, body.get("remark", ""))
            return None

        name = body.get("goodsName", "").strip()
        brand = body.get("trademark", "").strip()
        category = body.get("goodsType", "").strip()

        return {
            "name": name,
            "brand": brand,
            "category": category,
            "is_wine": _is_wine_category(category, name),
            "source": "aliyun",
            "raw": body,
        }

    except httpx.HTTPStatusError as e:
        logger.warning("[scan] Aliyun API HTTP %d for %s", e.response.status_code, barcode)
        return None
    except Exception:
        logger.exception("[scan] Aliyun barcode API error for %s", barcode)
        return None


# 酒类关键词（优先匹配具体品类，避免误判）
_WINE_KEYWORDS = frozenset([
    # 中文
    "葡萄酒", "红酒", "白葡萄酒", "起泡酒", "香槟", "啤酒", "白酒", "威士忌",
    "白兰地", "伏特加", "朗姆", "清酒", "黄酒", "米酒", "果酒", "预调酒",
    # 英文
    "wine", "whisky", "whiskey", "brandy", "vodka", "rum", "gin", "tequila",
    "sake", "baijiu", "spirits", "liquor", "champagne", "prosecco", "cava",
    "bordeaux", "burgundy", "merlot", "cabernet", "chardonnay", "pinot",
])

# 明确非酒精的关键词
_NON_ALCOHOL_KEYWORDS = frozenset([
    "非酒精", "无酒精", "0酒精", "无醇", "脱醇", "non-alcohol", "alcohol-free",
    "苹果醋", "果汁", "汽水", "矿泉水", "茶饮料", "咖啡",
])


def _is_wine_category(category: str, name: str) -> bool:
    """Determine if product is wine/alcohol based on category or name."""
    text = f"{category} {name}".lower()

    # Check non-alcoholic first (排除法)
    if any(kw in text for kw in _NON_ALCOHOL_KEYWORDS):
        return False

    # Check wine keywords
    return any(kw in text for kw in _WINE_KEYWORDS)


async def _query_openfoodfacts(barcode: str) -> dict[str, Any] | None:
    """Query Open Food Facts (free, international products)."""
    try:
        async with httpx.AsyncClient(timeout=config.barcode_api.timeout) as client:
            resp = await client.get(
                f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get("status") != 1:
                return None

            product = data.get("product", {})
            categories = product.get("categories_tags", [])
            is_wine = any("wine" in c or "alcohol" in c or "spirits" in c for c in categories)

            return {
                "name": product.get("product_name", ""),
                "brand": product.get("brands", ""),
                "category": product.get("categories", ""),
                "is_wine": is_wine,
                "source": "openfoodfacts",
                "raw": data,
            }
    except Exception:
        logger.exception("[scan] Open Food Facts API error for %s", barcode)
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

    # 1. Exact match
    spu = db.execute(select(SPU).where(SPU.name == norm_name)).scalars().first()
    if spu:
        return spu

    # 2. Alias match
    alias = db.execute(
        select(SPUAlias).where(SPUAlias.alias_norm == norm_name)
    ).scalars().first()
    if alias:
        return alias.spu

    # 3. Fuzzy match against all SPUs
    best_spu = _fuzzy_match_spu(db, name, api_result)
    if best_spu:
        logger.info("[scan] Fuzzy matched '%s' → SPU '%s'", name, best_spu.name)
        return best_spu

    return None


def _fuzzy_match_spu(db: Session, query_name: str, api_result: dict[str, Any]) -> SPU | None:
    """Fuzzy match product name against all SPUs using rapidfuzz."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        logger.warning("[scan] rapidfuzz not installed, skipping fuzzy match")
        return None

    all_spus = db.execute(select(SPU)).scalars().all()
    if not all_spus:
        return None

    query_norm = query_name.lower().strip()
    query_brand = (api_result.get("brand") or "").lower().strip()

    best_score = 0.0
    best_spu = None

    for spu in all_spus:
        spu_norm = spu.name.lower().strip()
        spu_brand = (spu.brand or "").lower().strip()

        # Token set ratio handles word-order and partial overlap well
        score = fuzz.token_set_ratio(query_norm, spu_norm)

        # Bonus if brand also matches
        if query_brand and spu_brand and query_brand == spu_brand:
            score = min(score + 15, 100)

        # Bonus if brand is contained in either name
        if query_brand and (query_brand in spu_norm or spu_brand in query_norm):
            score = min(score + 10, 100)

        if score > best_score:
            best_score = score
            best_spu = spu

    # Threshold: 75+ for auto-bind (conservative)
    if best_score >= 75:
        logger.info("[scan] Fuzzy match score: %.1f for '%s'", best_score, query_name)
        return best_spu

    logger.info("[scan] Best fuzzy score %.1f too low for '%s'", best_score, query_name)
    return None


def _log_scan(db: Session, barcode: str | None, result_type: str) -> None:
    """Log scan event（barcode 可空：拍酒标链路未必带条码）。"""
    log = ScanLog(
        barcode=barcode,
        result_type=result_type,
        ip_hash=hashlib.sha256(b"unknown").hexdigest(),  # TODO: get real IP
        created_at=datetime.now(),
    )
    db.add(log)
    db.commit()
