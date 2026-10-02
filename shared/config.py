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


@dataclass(frozen=True)
class BarcodeAPIConfig:
    aliyun_key: str = field(default_factory=lambda: _env("BARCODE_API_KEY", ""))
    aliyun_url: str = field(
        default_factory=lambda: _env(
            "BARCODE_API_URL",
            "https://market.aliyun.com/apimarket/product/BarcodeQuery",
        )
    )


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    barcode_api: BarcodeAPIConfig = field(default_factory=BarcodeAPIConfig)


# Singleton config instance
config = AppConfig()