"""SQLAlchemy ORM models - 7 tables matching 06-implementation-plan.md section 四."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BIGINT,
    CHAR,
    DECIMAL,
    INT,
    JSON,
    SMALLINT,
    TEXT,
    VARCHAR,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SPU(Base):
    """酒款主表（SPU）。年份/酒龄字段预留但 MVP 不启用。"""

    __tablename__ = "spu"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(200), nullable=False, unique=True)
    name_raw: Mapped[Optional[str]] = mapped_column(VARCHAR(200))
    brand: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    category: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # wine/whisky/gin
    country: Mapped[Optional[str]] = mapped_column(VARCHAR(50))
    region: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    abv: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(4, 1))
    volume_ml: Mapped[Optional[int]] = mapped_column(INT)
    vintage_year: Mapped[Optional[int]] = mapped_column(SMALLINT)  # V2 预留
    age_years: Mapped[Optional[int]] = mapped_column(SMALLINT)  # V2 预留
    possible_dup_of: Mapped[Optional[int]] = mapped_column(BIGINT)
    source: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # llm_extract/barcode_api/manual
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    aliases: Mapped[list[SPUAlias]] = relationship(back_populates="spu")
    barcodes: Mapped[list[Barcode]] = relationship(back_populates="spu")
    reviews: Mapped[list[Review]] = relationship(back_populates="spu")

    __table_args__ = (UniqueConstraint("name", name="uk_name"),)


class SPUAlias(Base):
    """别名表（承接 D6 实体对齐）。"""

    __tablename__ = "spu_alias"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    spu_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("spu.id"), nullable=False)
    alias: Mapped[str] = mapped_column(VARCHAR(200), nullable=False)
    alias_norm: Mapped[str] = mapped_column(VARCHAR(200), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # llm/manual/barcode_api

    # Relationships
    spu: Mapped[SPU] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("alias_norm", name="uk_alias"),
        Index("idx_spu", "spu_id"),
    )


class Barcode(Base):
    """条码映射（一酒多码；含非酒拦截与第三方原始报文）。"""

    __tablename__ = "barcode"

    code: Mapped[str] = mapped_column(VARCHAR(32), primary_key=True)  # EAN-13/UPC
    spu_id: Mapped[Optional[int]] = mapped_column(BIGINT, ForeignKey("spu.id"))
    is_non_wine: Mapped[int] = mapped_column(SMALLINT, server_default="0")
    category_hint: Mapped[Optional[str]] = mapped_column(VARCHAR(50))
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON)
    source: Mapped[Optional[str]] = mapped_column(VARCHAR(20))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    spu: Mapped[Optional[SPU]] = relationship(back_populates="barcodes")

    __table_args__ = (Index("idx_spu", "spu_id"),)


class VideoReview(Base):
    """视频评测表（管道状态机载体）。"""

    __tablename__ = "video_review"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    bvid: Mapped[str] = mapped_column(VARCHAR(12), nullable=False)
    mid: Mapped[int] = mapped_column(BIGINT, nullable=False)
    uploader_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    title: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    title_clean: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    title_hash: Mapped[Optional[str]] = mapped_column(CHAR(32))
    pubdate: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # pubdate_date is a generated column: DATE(pubdate) STORED
    # Handled via DDL migration, not ORM
    duration_sec: Mapped[Optional[int]] = mapped_column(INT)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False, default="NEW")
    subtitle_text: Mapped[Optional[str]] = mapped_column(TEXT)
    fail_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    retry_count: Mapped[int] = mapped_column(INT, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    reviews: Mapped[list[Review]] = relationship(back_populates="video_review")
    llm_tasks: Mapped[list[LLMTask]] = relationship(back_populates="video_review")

    __table_args__ = (
        UniqueConstraint("bvid", name="uk_bvid"),
        # uk_mid_day_title: requires pubdate_date generated column, added via DDL
        Index("idx_status", "status"),
        Index("idx_title_hash", "title_hash"),
    )


class Review(Base):
    """评测记录表（一视频多酒、一酒多博主、同博主重评走演变链）。"""

    __tablename__ = "review"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    spu_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("spu.id"), nullable=False)
    video_review_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("video_review.id"), nullable=False
    )
    mid: Mapped[int] = mapped_column(BIGINT, nullable=False)
    score_raw: Mapped[Optional[str]] = mapped_column(VARCHAR(20))
    score_type: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # pct100/scale10/none
    verdict: Mapped[Optional[str]] = mapped_column(VARCHAR(10))  # recommend/neutral/avoid
    flavor_tags: Mapped[Optional[list]] = mapped_column(JSON)
    recommend_index: Mapped[Optional[int]] = mapped_column(SMALLINT)
    quote: Mapped[Optional[str]] = mapped_column(TEXT)
    ts_start: Mapped[Optional[int]] = mapped_column(INT)
    ts_end: Mapped[Optional[int]] = mapped_column(INT)
    score_trend: Mapped[Optional[str]] = mapped_column(VARCHAR(4))  # UP/DOWN/SAME
    trend_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    prev_review_id: Mapped[Optional[int]] = mapped_column(BIGINT)  # 演变链
    confidence: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 2))
    is_latest: Mapped[int] = mapped_column(SMALLINT, default=1)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    spu: Mapped[SPU] = relationship(back_populates="reviews")
    video_review: Mapped[VideoReview] = relationship(back_populates="reviews")

    __table_args__ = (
        Index("idx_spu", "spu_id"),
        Index("idx_video", "video_review_id"),
        Index("idx_spu_mid_latest", "spu_id", "mid", "is_latest"),
    )


class LLMTask(Base):
    """LLM 任务表（COMPARE 对比 / EXTRACT 提取）。"""

    __tablename__ = "llm_task"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    task_type: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # COMPARE/EXTRACT
    video_review_id: Mapped[Optional[int]] = mapped_column(
        BIGINT, ForeignKey("video_review.id")
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(VARCHAR(20), default="PENDING")  # PENDING/RUNNING/DONE/FAILED
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_msg: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    retry_count: Mapped[int] = mapped_column(INT, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    video_review: Mapped[Optional[VideoReview]] = relationship(back_populates="llm_tasks")

    __table_args__ = (Index("idx_status_type", "status", "task_type"),)


class ScanLog(Base):
    """扫码日志（业务指标 + 缺漏反哺抓取优先级）。"""

    __tablename__ = "scan_log"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    barcode: Mapped[Optional[str]] = mapped_column(VARCHAR(32))
    result_type: Mapped[Optional[str]] = mapped_column(VARCHAR(20))  # HIT_REVIEW/HIT_NO_REVIEW/NOT_WINE/NOT_FOUND/SERIES
    ip_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        Index("idx_barcode", "barcode"),
        Index("idx_created", "created_at"),
    )