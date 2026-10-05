"""Configuration management with environment variable loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


@dataclass(frozen=True)
class MySQLConfig:
    host: str = field(default_factory=lambda: _env("MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("MYSQL_PORT", 3306))
    user: str = field(default_factory=lambda: _env("MYSQL_USER", "root"))
    password: str = field(default_factory=lambda: _env("MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: _env("MYSQL_DATABASE", "mr_sheven"))

    @property
    def url(self) -> str:
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )

    @property
    def async_url(self) -> str:
        """Async URL (requires aiomysql, add to deps when needed)."""
        return (
            f"mysql+aiomysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )


@dataclass(frozen=True)
class RedisConfig:
    host: str = field(default_factory=lambda: _env("REDIS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("REDIS_PORT", 6379))
    db: int = field(default_factory=lambda: _env_int("REDIS_DB", 0))
    password: str = field(default_factory=lambda: _env("REDIS_PASSWORD", ""))

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class BilibiliConfig:
    cookies_path: str = field(
        default_factory=lambda: _env("BILIBILI_COOKIES_PATH", "cookies.txt")
    )
    uploader_mids: list[int] = field(
        default_factory=lambda: [
            int(x.strip()) for x in _env("BILIBILI_UPLOADER_MIDS", "").split(",") if x.strip()
        ]
    )


@dataclass(frozen=True)
class BarcodeAPIConfig:
    """阿里云条形码查询 API (showapi).

    curl 示例:
        curl --get 'https://ali-barcode.showapi.com/barcode?code=6938166920785' \\
             -H 'Authorization:APPCODE {appcode}'
    """
    appcode: str = field(default_factory=lambda: _env("BARCODE_API_KEY", ""))
    url: str = field(
        default_factory=lambda: _env("BARCODE_API_URL", "https://ali-barcode.showapi.com/barcode")
    )
    timeout: int = field(default_factory=lambda: _env_int("BARCODE_API_TIMEOUT", 10))


@dataclass(frozen=True)
class OCRConfig:
    """酒标 OCR 配置（裁决 C12：中文背标主识别路径）。

    默认走 OpenAI 兼容 /chat/completions 多模态接口，
    api_key/base_url 留空时回落到 LLM_API_KEY / LLM_BASE_URL。
    model 必须是所配网关上**存在的多模态模型**：
        - 标准百炼：qwen-vl-ocr / qwen-vl-plus
        - token-plan 网关：qwen3.8-flash / qwen3.8-max（无 qwen-vl 系列）
    阿里云读光等其他 OCR 可在 server/services/ocr.py 增加 provider 分支接入。

    provider:
        qwen_vl - OpenAI 兼容多模态 chat 识图（默认）
        none    - 禁用 OCR，仅允许 text 透传（调试）
    """
    provider: str = field(default_factory=lambda: _env("OCR_PROVIDER", "qwen_vl"))
    api_key: str = field(default_factory=lambda: _env("OCR_API_KEY", ""))
    base_url: str = field(default_factory=lambda: _env("OCR_BASE_URL", ""))
    model: str = field(default_factory=lambda: _env("OCR_MODEL", "qwen-vl-ocr"))
    timeout: int = field(default_factory=lambda: _env_int("OCR_TIMEOUT", 60))


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration (OpenAI-compatible API).

    Supports: 百炼 DashScope, OpenAI, DeepSeek, Moonshot, 中转代理等
    任何兼容 /v1/chat/completions 的服务均可。
    """
    api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: _env("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    )
    model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen-plus"))
    temperature: float = field(default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.1")))
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 4096))
    timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 120))


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    barcode_api: BarcodeAPIConfig = field(default_factory=BarcodeAPIConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


# Singleton config instance
config = AppConfig()
