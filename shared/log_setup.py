"""统一日志落盘规范：./logs/{backend,pipeline,frontend}/ 三目录。

- backend / pipeline：滚动文件 + 控制台双写（本模块负责）
- frontend：Web 端无法写本地盘，由 scripts/run_frontend.sh 把
  flutter run 输出 tee 到 logs/frontend/flutter_run.log

用法：
    from shared.log_setup import log_dir, setup_service_logging
    setup_service_logging("backend")                       # → logs/backend/backend.log
    setup_service_logging("pipeline", filename="scheduler.log")
    path = log_dir("pipeline") / "crawl_overnight.log"     # 自定义文件名
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_ROOT = Path(__file__).resolve().parent.parent / "logs"
SERVICES = frozenset({"backend", "pipeline", "frontend"})

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_TAG = "_mr_sheven_log_service"


def log_dir(service: str) -> Path:
    """返回 ./logs/{service}/ 目录（自动创建）。"""
    if service not in SERVICES:
        raise ValueError(f"未知日志服务: {service}，可选 {sorted(SERVICES)}")
    path = LOG_ROOT / service
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_service_logging(
    service: str,
    filename: str | None = None,
    level: int = logging.INFO,
) -> Path:
    """把根日志接到 ./logs/{service}/{filename}（滚动写入）+ 控制台。

    幂等：同一 service 重复调用只保留一份 handler。
    同时给 uvicorn 系 logger 挂文件 handler，access/error 一并落盘。
    """
    path = log_dir(service) / (filename or f"{service}.log")
    formatter = logging.Formatter(_FMT)
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    setattr(file_handler, _TAG, service)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _TAG, service)

    uvicorn_loggers = [
        logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    ]
    for lg in [root, *uvicorn_loggers]:
        for old in list(lg.handlers):
            if getattr(old, _TAG, None) == service:
                lg.removeHandler(old)
                old.close()

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    for lg in uvicorn_loggers:
        lg.addHandler(file_handler)

    return path
