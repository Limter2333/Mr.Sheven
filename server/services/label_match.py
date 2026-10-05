"""酒标 LLM 结构化提取 + 三档语义匹配（裁决 C12）。

两段式：
    1. extract_label_fields: 背标文本 → 品名/品牌/品类/原产国/产区/品种/酒精度/净含量/进口商/年份
    2. judge_match: 提取字段 + 候选 SPU → EXACT / SERIES / NONE

防幻觉纪律（真瓶验证：橡木桶五号 vs 珍藏，LLM 应拒绝跨款绑定）：
    - 宁可不绑也不乱绑：不是同一款酒绝不给 EXACT
    - 同系列不同款（珍藏/特酿/五号/年份差异）只能给 SERIES
    - spu_id 必须来自候选集，否则保守降级为 NONE
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from rapidfuzz import fuzz

from pipeline.normalize.normalizer import _strip_asr_particles
from shared.config import config

logger = logging.getLogger("server.label_match")

# 候选进入 LLM 研判的最低相似度
CANDIDATE_MIN_SCORE = 45.0
CANDIDATE_TOP_N = 8

MATCH_LEVELS = frozenset({"EXACT", "SERIES", "NONE"})

EXTRACT_PROMPT = """你是酒标信息抽取员。从以下进口酒中文背标文本中抽取结构化字段。

## 输出格式
严格返回一个 JSON 对象（不要输出任何其他文字）：
- product_name: 中文品名（法定印刷品名，必须逐字照抄背标品名原文，禁止增删任何字）
- brand: 品牌名（照抄背标原文；若文本未单列品牌，可取品名开头的品牌词，拿不准填 null）
- category: 品类 wine/whisky/gin/other
- country: 原产国（如"西班牙"，无则 null）
- region: 产区（无则 null）
- grape: 葡萄/原料品种（无则 null）
- abv: 酒精度数值（如 13.0，无则 null）
- volume_ml: 净含量毫升数（如 750，无则 null）
- importer: 进口商/经销商（无则 null）
- vintage: 年份（如 2020，无则 null）

## 纪律
1. 任何字段拿不准填 null，禁止编造
2. product_name 必须是背标上的品名原文逐字照抄：不改写、不翻译、不补字、不删字、不用其他酒名替换
3. 度数去掉 %vol 单位只留数字；容量统一换算成毫升

## 背标文本
{text}
"""

MATCH_PROMPT = """你是酒款实体对齐专家。给定 OCR 提取的酒标字段与数据库候选酒款，判断匹配档位。

## 档位定义
- EXACT：同一款酒（同品牌、同系列、同产品；允许叫法差异，如简称/全称/中英混写）
- SERIES：同品牌或同系列的**不同产品**（如拍到"A系列特酿"，候选是"A系列珍藏"；或年份/度数/包装明显不同）
- NONE：无关，或候选中没有接近的酒款

## 纪律（宁可不绑也不乱绑）
1. 不是同一款酒，绝不给 EXACT
2. 系列/产品线不同（珍藏/特酿/年份/度数差异）只能给 SERIES
3. 候选里没有像样的对应酒款时，给 NONE，不要硬凑
4. spu_id 只能填候选列表中的 id；NONE 时 spu_id 填 null
5. confidence 是你对本次判断的置信度（0.00~1.00）
6. OCR 可能有错别字（同音/形近字，如"珍藏"误识为"陈藏"），个别字差异不等于产品不同；以品牌+系列+产品线综合判断

## 输出格式
严格返回一个 JSON 对象：
{{"spu_id": <int 或 null>, "match_level": "EXACT|SERIES|NONE",
 "confidence": 0.95, "reason": "简要依据"}}

## OCR 提取的酒标字段
{fields}

## 候选酒款（数据库）
{candidates}
"""


@dataclass
class MatchResult:
    """三档匹配结论。"""

    spu_id: int | None
    match_level: str  # EXACT / SERIES / NONE
    confidence: float
    reason: str


async def extract_label_fields(text: str) -> dict[str, Any]:
    """LLM 结构化提取背标字段。

    Returns:
        字段 dict（缺失字段为 null）；LLM 失败时抛 RuntimeError
    """
    if not text or len(text.strip()) < 5:
        raise ValueError("背标文本过短")

    prompt = EXTRACT_PROMPT.format(text=text[:8000])
    raw = await _chat_json(prompt)

    if not isinstance(raw, dict):
        logger.warning("[label_match] Extract output not a dict: %s", type(raw).__name__)
        return {}

    fields: dict[str, Any] = {
        "product_name": _as_str(raw.get("product_name")),
        "brand": _as_str(raw.get("brand")),
        "category": _as_str(raw.get("category")),
        "country": _as_str(raw.get("country")),
        "region": _as_str(raw.get("region")),
        "grape": _as_str(raw.get("grape")),
        "abv": _as_float(raw.get("abv")),
        "volume_ml": _as_int(raw.get("volume_ml")),
        "importer": _as_str(raw.get("importer")),
        "vintage": _as_int(raw.get("vintage")),
    }
    logger.info("[label_match] Extracted fields: %s", fields.get("product_name"))
    return fields


def pick_candidates(spus: Sequence[Any], fields: dict[str, Any]) -> list[tuple[Any, float]]:
    """rapidfuzz 粗排：按品名相似度 + 品牌加成取 Top-N 候选。

    spu 只需具备 id/name/brand 属性（便于测试注入）。
    """
    query_name = str(fields.get("product_name") or "").lower().strip()
    if not query_name:
        return []
    query_brand = str(fields.get("brand") or "").lower().strip()

    scored: list[tuple[Any, float]] = []
    for spu in spus:
        spu_name = (getattr(spu, "name", "") or "").lower()
        spu_brand = (getattr(spu, "brand", "") or "").lower().strip()

        score = float(fuzz.token_set_ratio(query_name, spu_name))
        if query_brand and spu_brand and query_brand == spu_brand:
            score = min(score + 15.0, 100.0)
        elif query_brand and (query_brand in spu_name or (spu_brand and spu_brand in query_name)):
            score = min(score + 10.0, 100.0)
        elif spu_brand and spu_brand in query_name:
            # 提取没单列出品牌时，库内品牌出现在品名里也算命中（"奥兰小红帽…"含"奥兰"）
            score = min(score + 15.0, 100.0)

        if score > 0:
            scored.append((spu, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [(s, sc) for s, sc in scored[:CANDIDATE_TOP_N] if sc >= CANDIDATE_MIN_SCORE]


async def judge_match(fields: dict[str, Any], candidates: Sequence[Any]) -> MatchResult:
    """LLM 三档研判。无候选直接 NONE；研判结果过 _validate_judgment 保守校验。"""
    if not candidates:
        return MatchResult(None, "NONE", 0.0, "无候选酒款")

    candidate_lines = "\n".join(
        # 库名可能带 ASR 尾音（如"珍藏哈"），清洗后再研判，避免把语气词当产品差异
        f"- id={getattr(c, 'id', None)} "
        f"name={_strip_asr_particles(str(getattr(c, 'name', '') or ''))} "
        f"brand={getattr(c, 'brand', '') or '未知'} category={getattr(c, 'category', '') or '未知'}"
        for c in candidates
    )
    prompt = MATCH_PROMPT.format(
        fields=json.dumps(fields, ensure_ascii=False),
        candidates=candidate_lines,
    )

    raw = await _chat_json(prompt)
    allowed_ids = {int(c.id) for c in candidates if getattr(c, "id", None) is not None}
    result = _validate_judgment(raw, allowed_ids)
    logger.info(
        "[label_match] Match result: %s (spu_id=%s, conf=%.2f) %s",
        result.match_level, result.spu_id, result.confidence, result.reason,
    )
    return result


def _validate_judgment(raw: Any, allowed_ids: set[int]) -> MatchResult:
    """校验 LLM 研判输出，越界/非法一律保守降级 NONE。"""
    if not isinstance(raw, dict):
        return MatchResult(None, "NONE", 0.0, "LLM 输出格式错误")

    level = str(raw.get("match_level") or "").upper().strip()
    if level not in MATCH_LEVELS:
        return MatchResult(None, "NONE", 0.0, f"非法 match_level: {level or '空'}")

    spu_id_raw = raw.get("spu_id")
    try:
        spu_id: int | None = int(spu_id_raw) if spu_id_raw is not None else None
    except (TypeError, ValueError):
        spu_id = None

    if level == "NONE":
        spu_id = None
    elif spu_id is None or spu_id not in allowed_ids:
        return MatchResult(None, "NONE", 0.0, "spu_id 不在候选集内，保守降级为 NONE")

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = str(raw.get("reason") or "")[:200]
    return MatchResult(spu_id, level, confidence, reason)


async def _chat_json(prompt: str) -> Any:
    """调用 LLM（JSON 模式）并解析。失败抛 RuntimeError。"""
    if not config.llm.api_key:
        raise RuntimeError("缺少 LLM_API_KEY")

    try:
        async with httpx.AsyncClient(timeout=config.llm.timeout) as client:
            resp = await client.post(
                f"{config.llm.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.llm.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.llm.temperature,
                    "max_tokens": min(config.llm.max_tokens, 2048),
                    "response_format": {"type": "json_object"},
                    "enable_thinking": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("[label_match] LLM HTTP %d", e.response.status_code)
        raise RuntimeError(f"LLM 服务返回 HTTP {e.response.status_code}") from e
    except httpx.HTTPError:
        logger.exception("[label_match] LLM request failed")
        raise RuntimeError("LLM 服务请求失败") from None

    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("[label_match] LLM JSON parse failed: %s", str(content)[:200])
        raise RuntimeError("LLM 输出不是合法 JSON") from e


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None
