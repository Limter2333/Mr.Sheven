"""Tests for pipeline.dedup module."""

from pipeline.dedup.checker import DedupResult


class TestDedupResult:
    def test_pass_result(self):
        r = DedupResult(action="pass")
        assert r.action == "pass"
        assert r.reason == ""
        assert r.similar_video_id is None

    def test_dup_suspect_result(self):
        r = DedupResult(action="dup_suspect", reason="title match", similar_video_id=42)
        assert r.action == "dup_suspect"
        assert r.similar_video_id == 42

    def test_repr(self):
        r = DedupResult(action="pass")
        assert "pass" in repr(r)