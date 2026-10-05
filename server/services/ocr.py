"""酒标 OCR（裁决 C12：中文背标主识别路径）。

默认 provider=qwen_vl：百炼 qwen-vl-ocr（OpenAI 兼容多模态 chat），
复用 LLM_API_KEY / LLM_BASE_URL，无需额外开通。
阿里云读光等其他 OCR 在 `_providers` 加分支即可（OCR_PROVIDER 切换）。

调试通道：POST /api/v1/scan-label 直接传 text 可跳过本模块（文本透传）。
"""

from __future__ import annotations

import base64
import logging

import httpx

from shared.config import config

logger = logging.getLogger("server.ocr")

# 允许的图片类型与大小上限（5MB，背标照片足够）
ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 5 * 1024 * 1024

OCR_PROMPT = "请识别图片中的全部文字，保持原有换行顺序输出，不要翻译、不要总结、不要遗漏。"


class OCRError(Exception):
    """OCR 调用失败（网络/额度/模型错误）。"""


class OCRUnavailableError(OCRError):
    """OCR 未配置（如 OCR_PROVIDER=none 或缺少 API Key）。"""


def sniff_mime(image_bytes: bytes) -> str | None:
    """按文件头识别图片真实类型，识别不出返回 None。

    Web 端（image_picker / MultipartRequest）常把 Content-Type 丢成
    application/octet-stream，不能信声明的 MIME，以魔数为准。
    """
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(image_bytes: bytes, mime_type: str) -> str:
    """校验图片类型与大小，返回可用的 MIME（魔数优先，声明兜底）。非法抛 ValueError。"""
    if not image_bytes:
        raise ValueError("图片内容为空")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 5MB，请压缩后重试")
    declared = (mime_type or "").split(";")[0].strip().lower()
    resolved = sniff_mime(image_bytes) or declared
    if resolved not in ALLOWED_MIME_TYPES:
        raise ValueError(f"不支持的图片类型 {mime_type}，请上传 JPEG/PNG/WebP")
    return resolved


async def ocr_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """识别酒标图片，返回全文文本。

    Raises:
        ValueError: 图片非法
        OCRUnavailableError: OCR 未配置
        OCRError: OCR 调用失败
    """
    mime_type = validate_image(image_bytes, mime_type)

    provider = config.ocr.provider.strip().lower()
    if provider == "none":
        raise OCRUnavailableError("OCR 已禁用（OCR_PROVIDER=none），请传 text 调试或启用 OCR")
    if provider != "qwen_vl":
        raise OCRUnavailableError(f"未知 OCR provider: {provider}")

    return await _ocr_qwen_vl(image_bytes, mime_type)


async def _ocr_qwen_vl(image_bytes: bytes, mime_type: str) -> str:
    """百炼 qwen-vl-ocr：多模态 chat，返回图中文字。"""
    api_key = config.ocr.api_key or config.llm.api_key
    base_url = (config.ocr.base_url or config.llm.base_url).rstrip("/")
    if not api_key:
        raise OCRUnavailableError("缺少 OCR_API_KEY / LLM_API_KEY，无法调用 OCR")

    data_uri = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
    payload = {
        "model": config.ocr.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "temperature": 0.0,
        "enable_thinking": False,
    }

    try:
        async with httpx.AsyncClient(timeout=config.ocr.timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("[ocr] HTTP %d: %s", e.response.status_code, e.response.text[:200])
        # 把上游错误（如 model_not_found）透出，便于定位网关/模型配置问题
        detail = ""
        try:
            err = e.response.json().get("error", {})
            detail = str(err.get("message") or err.get("code") or "")[:120]
        except Exception:
            pass
        raise OCRError(
            f"OCR 服务返回 HTTP {e.response.status_code}{': ' + detail if detail else ''}"
        ) from e
    except httpx.HTTPError:
        logger.exception("[ocr] OCR request failed")
        raise OCRError("OCR 服务请求失败") from None

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error("[ocr] Unexpected response shape: %s", str(data)[:200])
        raise OCRError("OCR 响应格式异常") from e

    # 部分模型会把 content 包成 [{"text": ...}]，兼容处理
    if isinstance(text, list):
        text = "".join(str(seg.get("text", "")) for seg in text if isinstance(seg, dict))
    text = str(text).strip()

    if not text:
        raise OCRError("OCR 未识别到文字，请重拍（避反光、让背标占满取景框）")

    logger.info("[ocr] Recognized %d chars", len(text))
    return text
