"""Tests for feedback model and API schema."""

import pytest
from pydantic import ValidationError

from server.api.feedback import FeedbackIn
from shared.models import Feedback


class TestFeedbackModel:
    def test_create_feedback(self):
        fb = Feedback(
            barcode="6901234567892",
            taste="果香型",
            content="希望收录奥兰小红帽的评测",
            ip_hash="a" * 64,
        )
        assert fb.barcode == "6901234567892"
        assert fb.taste == "果香型"
        assert "奥兰" in fb.content

    def test_feedback_without_barcode(self):
        # 设置页"报告问题"没有条码
        fb = Feedback(content="发现一个 bug")
        assert fb.barcode is None
        assert fb.content == "发现一个 bug"


class TestFeedbackIn:
    def test_valid_payload(self):
        payload = FeedbackIn(barcode="6901", taste="干型", feedback="不错")
        assert payload.feedback == "不错"

    def test_barcode_and_taste_optional(self):
        payload = FeedbackIn(feedback="催更")
        assert payload.barcode is None
        assert payload.taste is None

    def test_empty_feedback_rejected(self):
        with pytest.raises(ValidationError):
            FeedbackIn(feedback="")

    def test_feedback_too_long_rejected(self):
        with pytest.raises(ValidationError):
            FeedbackIn(feedback="x" * 2001)
