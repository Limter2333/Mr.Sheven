"""Tests for server.services.label_match（三档匹配校验 + 候选粗排）。"""

from types import SimpleNamespace

from server.services.label_match import (
    _as_float,
    _as_int,
    _as_str,
    _validate_judgment,
    pick_candidates,
)


def _spu(spu_id: int, name: str, brand: str = "", category: str = "wine"):
    return SimpleNamespace(id=spu_id, name=name, brand=brand, category=category)


class TestValidateJudgment:
    def test_exact_accepts_valid_candidate(self):
        result = _validate_judgment(
            {"spu_id": 34, "match_level": "EXACT", "confidence": 0.95, "reason": "同款"},
            {34, 48},
        )
        assert result.match_level == "EXACT"
        assert result.spu_id == 34
        assert result.confidence == 0.95

    def test_series_with_valid_candidate(self):
        result = _validate_judgment(
            {"spu_id": 34, "match_level": "SERIES", "confidence": 0.95, "reason": "同系列"},
            {34},
        )
        assert result.match_level == "SERIES"
        assert result.spu_id == 34

    def test_none_clears_spu_id(self):
        result = _validate_judgment(
            {"spu_id": 34, "match_level": "NONE", "confidence": 0.95, "reason": "不匹配"},
            {34},
        )
        assert result.match_level == "NONE"
        assert result.spu_id is None

    def test_exactly_like_probe_rejects_cross_product(self):
        # 真瓶验证场景：橡木桶五号 不绑 珍藏 —— LLM 给 null + NONE
        result = _validate_judgment(
            {"spu_id": None, "match_level": "NONE", "confidence": 0.95,
             "reason": "OCR明确标识为橡木桶干红（五号），候选项为珍藏系列，不匹配"},
            {34, 48},
        )
        assert result.match_level == "NONE"
        assert result.spu_id is None

    def test_out_of_candidates_degrades_to_none(self):
        # 幻觉 spu_id 必须被拒
        result = _validate_judgment(
            {"spu_id": 999, "match_level": "EXACT", "confidence": 0.9, "reason": "编造"},
            {34, 48},
        )
        assert result.match_level == "NONE"
        assert result.spu_id is None

    def test_invalid_level_degrades_to_none(self):
        result = _validate_judgment(
            {"spu_id": 34, "match_level": "MAYBE", "confidence": 0.5, "reason": ""},
            {34},
        )
        assert result.match_level == "NONE"

    def test_non_dict_input(self):
        assert _validate_judgment(["oops"], {1}).match_level == "NONE"
        assert _validate_judgment("oops", {1}).match_level == "NONE"

    def test_confidence_clamped(self):
        result = _validate_judgment(
            {"spu_id": 34, "match_level": "EXACT", "confidence": 3.0, "reason": ""},
            {34},
        )
        assert result.confidence == 1.0

    def test_string_spu_id_coerced(self):
        result = _validate_judgment(
            {"spu_id": "34", "match_level": "SERIES", "confidence": 0.5, "reason": ""},
            {34},
        )
        assert result.spu_id == 34


class TestPickCandidates:
    def test_top_match_with_brand_bonus(self):
        spus = [
            _spu(1, "奥兰小红帽珍藏哈", brand="奥兰"),
            _spu(2, "奔富407", brand="奔富"),
        ]
        fields = {"product_name": "奥兰小红帽橡木桶干红葡萄酒（五号）", "brand": "奥兰"}
        result = pick_candidates(spus, fields)
        assert result
        assert result[0][0].id == 1

    def test_empty_product_name(self):
        assert pick_candidates([_spu(1, "任意")], {"product_name": ""}) == []

    def test_low_score_excluded(self):
        spus = [_spu(1, "完全无关的酒名xyz")]
        fields = {"product_name": "奥兰小红帽珍藏"}
        result = pick_candidates(spus, fields)
        assert result == []

    def test_top_n_limit(self):
        spus = [_spu(i, f"奥兰小红帽{i}") for i in range(20)]
        fields = {"product_name": "奥兰小红帽珍藏", "brand": "奥兰"}
        result = pick_candidates(spus, fields)
        assert len(result) <= 8


class TestFieldCoercion:
    def test_as_str(self):
        assert _as_str(" 奥兰 ") == "奥兰"
        assert _as_str("") is None
        assert _as_str(None) is None

    def test_as_float(self):
        assert _as_float("13") == 13.0
        assert _as_float("abc") is None
        assert _as_float(None) is None

    def test_as_int(self):
        assert _as_int("750") == 750
        assert _as_int("2020.0") == 2020
        assert _as_int(None) is None
