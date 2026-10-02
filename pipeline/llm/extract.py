"""LLM structured extraction: extract wine reviews from subtitle text.

Uses 百炼 qwen-plus (or qwen-max for difficult cases).
Anti-hallucination rules:
    1. Only extract wines actually tasted/reviewed (not casually mentioned)
    2. Fill null for uncertain fields (never fabricate)
    3. quote must be verbatim from source text
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from shared.config import config

logger = logging.getLogger("pipeline.llm.extract")

EXTRACTION_PROMPT = """你是酒类评测数据标注员。从以下转写文本中抽取所有被实际评测的酒款。

## 输出 Schema
返回 JSON 数组，每个元素包含：
- product_name_raw: 博主口中原话叫法（保留原始形态）
- brand: 品牌（能推断则填，否则 null）
- category: 品类 wine/whisky/gin/other（能推断则填，否则 null）
- score_raw: 原始评分（如 "92", "8.5"，无评分则 null）
- score_type: 评分制式 pct100/scale10/none
- verdict: 推荐/中性/避雷（三档归一）
- quote: 逐字摘录关键评价 1~3 句
- timestamp_start: 该段评价在视频中的起始时间（秒）
- timestamp_end: 结束时间（秒）
- confidence: 模型自评置信度 0.00~1.00

## 三条纪律
1. 只抽实际品尝/评测的酒，顺嘴提到的不算
2. 任何字段拿不准填 null，禁止编造
3. quote 必须逐字来自转写文本，不许改写

## 示例
```json
[{
  "product_name_raw": "麦卡伦12年双桶",
  "brand": "麦卡伦",
  "category": "whisky",
  "score_raw": "8.5",
  "score_type": "scale10",
  "verdict": "推荐",
  "quote": "这款酒雪莉桶的味道很浓郁，性价比不错",
  "timestamp_start": 120,
  "timestamp_end": 180,
  "confidence": 0.90
}]
```

## 转写文本
{text}
"""


async def extract_reviews(text: str) -> list[dict[str, Any]]:
    """Extract wine reviews from subtitle text using LLM.

    Args:
        text: Cleaned subtitle text

    Returns:
        List of extracted review dicts

    Raises:
        RuntimeError: If LLM call fails
    """
    if not text or len(text.strip()) < 50:
        logger.warning("[llm.extract] Text too short, skipping")
        return []

    prompt = EXTRACTION_PROMPT.format(text=text[:15000])  # Limit to ~15k chars

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.barcode_api.aliyun_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-plus",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        # Parse JSON response
        result = json.loads(content)

        # Handle both {"reviews": [...]} and [...] formats
        if isinstance(result, dict):
            reviews = result.get("reviews", result.get("data", []))
        elif isinstance(result, list):
            reviews = result
        else:
            reviews = []

        # Validate each review
        validated = []
        for r in reviews:
            if _validate_review(r):
                validated.append(r)
            else:
                logger.warning("[llm.extract] Invalid review skipped: %s", r.get("product_name_raw"))

        logger.info("[llm.extract] Extracted %d reviews (%d raw)", len(validated), len(reviews))
        return validated

    except json.JSONDecodeError:
        logger.exception("[llm.extract] Failed to parse LLM JSON response")
        return []
    except Exception:
        logger.exception("[llm.extract] LLM extraction failed")
        raise RuntimeError("LLM extraction failed")


def _validate_review(review: dict) -> bool:
    """Validate a single review dict."""
    # Must have product name
    if not review.get("product_name_raw"):
        return False

    # score_type must be valid if present
    valid_score_types = {"pct100", "scale10", "none", None}
    if review.get("score_type") not in valid_score_types and review.get("score_type") is not None:
        return False

    # verdict must be valid if present
    valid_verdicts = {"推荐", "中性", "避雷", None}
    if review.get("verdict") not in valid_verdicts:
        return False

    # confidence must be 0-1
    conf = review.get("confidence")
    if conf is not None and (not isinstance(conf, (int, float)) or conf < 0 or conf > 1):
        return False

    return True


async def compare_reviews(
    old_summary: str, new_summary: str
) -> dict[str, Any]:
    """Compare old and new reviews for the same wine by same UP主.

    Args:
        old_summary: Summary of old review
        new_summary: Summary of new review

    Returns:
        Dict with is_duplicate, score_trend, trend_reason
    """
    prompt = f"""对比以下两条来自同一博主对同一款酒的评测，判断是否为重复评测。

## 旧评测摘要
{old_summary}

## 新评测摘要
{new_summary}

## 输出 JSON
{{
  "is_duplicate": true/false,
  "old_score": "旧评分",
  "new_score": "新评分",
  "score_trend": "UP/DOWN/SAME",
  "reason_for_change": "变化原因（如有）"
}}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.barcode_api.aliyun_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-plus",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    except Exception:
        logger.exception("[llm.compare] Comparison failed")
        raise RuntimeError("LLM comparison failed")