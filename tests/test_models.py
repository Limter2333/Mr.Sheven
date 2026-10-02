"""Tests for shared.models - model instantiation and relationships."""

from shared.models import (
    SPU,
    Barcode,
    LLMTask,
    Review,
    SPUAlias,
    ScanLog,
    VideoReview,
)


class TestSPU:
    def test_create_spu(self):
        spu = SPU(name="macallan 12 double cask", brand="Macallan", category="whisky")
        assert spu.name == "macallan 12 double cask"
        assert spu.brand == "Macallan"
        assert spu.category == "whisky"


class TestVideoReview:
    def test_create_video_review(self):
        vr = VideoReview(
            bvid="BV1Yjciz3EuE",
            mid=12345,
            title="测试视频",
            status="NEW",
            retry_count=0,
        )
        assert vr.bvid == "BV1Yjciz3EuE"
        assert vr.status == "NEW"
        assert vr.retry_count == 0


class TestReview:
    def test_create_review(self):
        review = Review(
            spu_id=1,
            video_review_id=1,
            mid=12345,
            score_raw="92",
            score_type="pct100",
            verdict="recommend",
            is_latest=1,
        )
        assert review.score_raw == "92"
        assert review.verdict == "recommend"


class TestBarcode:
    def test_create_barcode(self):
        bc = Barcode(code="3274080005003", spu_id=1, is_non_wine=0)
        assert bc.code == "3274080005003"
        assert bc.is_non_wine == 0


class TestScanLog:
    def test_create_scan_log(self):
        log = ScanLog(barcode="123456789", result_type="HIT_REVIEW")
        assert log.barcode == "123456789"