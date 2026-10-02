"""Tests for pipeline.cleaner module."""

from pipeline.cleaner.cleaner import clean_subtitle_text, clean_subtitle_segments


class TestCleanSubtitleText:
    def test_remove_timestamps(self):
        raw = "[00:12] 这是测试文本 [01:30] 另一段"
        result = clean_subtitle_text(raw)
        assert "00:12" not in result
        assert "测试文本" in result

    def test_remove_blacklist_phrases(self):
        raw = "这款酒不错 求三连 一键三连"
        result = clean_subtitle_text(raw)
        assert "求三连" not in result
        assert "一键三连" not in result
        assert "这款酒不错" in result

    def test_remove_garbage_chars(self):
        raw = "好酒 ♪♫ 值得推荐 🎵"
        result = clean_subtitle_text(raw)
        assert "♪" not in result
        assert "🎵" not in result
        assert "好酒" in result

    def test_normalize_whitespace(self):
        raw = "  多余   空格  "
        result = clean_subtitle_text(raw)
        assert "  " not in result
        assert result == "多余 空格"

    def test_empty_input(self):
        assert clean_subtitle_text("") == ""
        assert clean_subtitle_text(None) == ""  # type: ignore[arg-type]

    def test_preserve_content(self):
        raw = "麦卡伦12年双桶，雪莉桶的味道很浓郁，性价比不错"
        result = clean_subtitle_text(raw)
        assert "麦卡伦" in result
        assert "雪莉桶" in result


class TestCleanSubtitleSegments:
    def test_clean_segments(self):
        segments = [
            {"from": 0, "to": 5, "content": "这款酒不错"},
            {"from": 5, "to": 10, "content": "求三连"},
            {"from": 10, "to": 15, "content": "推荐购买"},
        ]
        result = clean_subtitle_segments(segments)
        assert "这款酒不错" in result
        assert "推荐购买" in result
        assert "求三连" not in result

    def test_empty_segments(self):
        assert clean_subtitle_segments([]) == ""