"""Feedback API: 用户反馈 / 催更 / 问题报告落库。

Endpoint:
    POST /api/v1/feedback  - 提交反馈（barcode 可空，如设置页"报告问题"）
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import Feedback

logger = logging.getLogger("server.feedback")
router = APIRouter()


class FeedbackIn(BaseModel):
    """反馈入参。"""

    barcode: str | None = Field(default=None, max_length=32)
    taste: str | None = Field(default=None, max_length=20)
    feedback: str = Field(min_length=1, max_length=2000)


@router.post("/feedback", response_model=None)
async def submit_feedback(
    request: Request,
    payload: FeedbackIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    content = payload.feedback.strip()
    if not content:
        return JSONResponse(status_code=422, content={"error": "反馈内容不能为空"})

    ip = (request.client.host if request.client else "") or "unknown"
    row = Feedback(
        barcode=(payload.barcode or "").strip() or None,
        taste=(payload.taste or "").strip() or None,
        content=content,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest(),
        created_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    logger.info(
        "Feedback saved id=%s barcode=%s taste=%s len=%d",
        row.id, row.barcode, row.taste, len(content),
    )
    return JSONResponse(content={"status": "ok", "id": row.id})
