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

EXTRACTION_PROMPT = """你是酒类评测数据标注员。从以下转写文本中抽取所有被**实际品尝并给出评价**的酒款。

## 输出格式
严格返回一个 JSON 数组（即使只有一款酒也要用数组包裹），不要输出任何其他文字。
每个元素包含：
- product_name_raw: 博主口中原话叫法（保留原始形态，同一款酒全文只用一个最完整的叫法）
- brand: 品牌（能推断则填，否则 null）
- category: 品类 wine/whisky/gin/other（能推断则填，否则 null）
- score_raw: 原始评分（如 "92", "8.5"，无评分则 null）
- score_type: 评分制式 pct100/scale10/none
- verdict: 推荐/中性/避雷（三档归一）
- quote: 逐字摘录关键评价 1~3 句
- timestamp_start: 该段评价在视频中的起始时间（秒）
- timestamp_end: 结束时间（秒）
- confidence: 模型自评置信度 0.00~1.00

## 什么算"实际评测"（✅ 抽取）
必须同时满足以下两个条件：
1. **喝到了**：博主亲自品尝了这款酒（"我们试一下""来一口""入口""喝""品"等动作）
2. **有评价**：给出了口感/风味/质量/评分/推荐与否的判断（如"酸度不错""给85分""不推荐""有铁锈味"）

## 什么算"顺嘴提到"（❌ 不抽取）
以下情况一律**不要抽取**：
- **没点/没喝**："上次有XX没点""想试试XX""下次喝XX"
- **点单/报菜名**："来一杯XX""我们今天有XX""XX多少钱"——只说了名字和价格，没有口感评价
- **餐前/餐后闲聊**：开胃酒、佐餐酒、利口酒等只是配角，博主没有正式品评
- **事后回提**："刚才那个XX还行"——在评测完之后再次提到，不是新的评测
- **对比/参照**："比XX好喝""像XX那种"——被拿来比较的酒不是本次评测对象

## 同款酒去重规则
- 同一款酒在全文中可能有不同叫法（简称、全称、昵称），只提取**一次**
- product_name_raw 用博主**品测时**的叫法（通常是"我们第X只""这只XX"处的称呼）
- 例如"兰布鲁斯科起泡酒"和"阿兰布鲁斯科"如果是同一款酒，只写一条

## 其他纪律
1. 任何字段拿不准填 null，禁止编造
2. quote 必须逐字来自转写文本，不许改写

## 示例
假设文本中有：
- "上次有个麦卡伦12年没点" → ❌ 不抽（没喝）
- "来一杯1987索阿维" → ❌ 不抽（点单，无评价）
- "我们第一只就从这只麦卡伦12年双桶开始，入口雪莉桶味很浓，给8.5分" → ✅ 抽取

正确输出：
```json
[{{
  "product_name_raw": "麦卡伦12年双桶",
  "brand": "麦卡伦",
  "category": "whisky",
  "score_raw": "8.5",
  "score_type": "scale10",
  "verdict": "推荐",
  "quote": "入口雪莉桶味很浓，给8.5分",
  "timestamp_start": 120,
  "timestamp_end": 180,
  "confidence": 0.90
}}]
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
        async with httpx.AsyncClient(timeout=config.llm.timeout) as client:
            response = await client.post(
                f"{config.llm.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.llm.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.llm.temperature,
                    "max_tokens": config.llm.max_tokens,
                    "response_format": {"type": "json_object"},
                    "enable_thinking": False,  # 关闭思考模式，避免超时
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        # Parse JSON response
        result = json.loads(content)

        # Handle multiple formats: [...] | {"reviews": [...]} | {...single review...}
        if isinstance(result, list):
            reviews = result
        elif isinstance(result, dict):
            if "reviews" in result:
                reviews = result["reviews"]
            elif "data" in result:
                reviews = result["data"]
            elif "product_name_raw" in result:
                # Single review object, wrap in list
                reviews = [result]
            else:
                reviews = []
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
        async with httpx.AsyncClient(timeout=config.llm.timeout) as client:
            response = await client.post(
                f"{config.llm.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.llm.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.llm.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.llm.temperature,
                    "max_tokens": config.llm.max_tokens,
                    "response_format": {"type": "json_object"},
                    "enable_thinking": False,  # 关闭思考模式，避免超时
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    except Exception:
        logger.exception("[llm.compare] Comparison failed")
        raise RuntimeError("LLM comparison failed")