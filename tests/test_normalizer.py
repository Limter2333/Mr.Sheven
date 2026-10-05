"""Tests for pipeline.normalize.normalizer（含 ASR 语气词清洗）。"""

from pipeline.normalize.normalizer import _normalize_name, _strip_asr_particles


class TestStripAsrParticles:
    def test_strip_trailing_ha(self):
        # 真实脏数据：ASR 把口播尾音"哈"带进品名
        assert _strip_asr_particles("奥兰小红帽珍藏哈") == "奥兰小红帽珍藏"

    def test_strip_multiple_particles(self):
        assert _strip_asr_particles("奔富407啊呀") == "奔富407"

    def test_only_strips_trailing(self):
        # 名字中间的语气词字不剥
        assert _strip_asr_particles("哈瓦那俱乐部") == "哈瓦那俱乐部"

    def test_keeps_short_names(self):
        # 长度 <=2 不剥，避免误伤
        assert _strip_asr_particles("哇") == "哇"
        assert _strip_asr_particles("啊哈") == "啊哈"

    def test_max_two_strips(self):
        # 只剥 2 个，第三个保留
        assert _strip_asr_particles("这款酒啊呀哈") == "这款酒啊"

    def test_plain_names_unchanged(self):
        assert _strip_asr_particles("麦卡伦12年双桶") == "麦卡伦12年双桶"
        assert _strip_asr_particles("山姆凯樽汇白诗南") == "山姆凯樽汇白诗南"


class TestNormalizeName:
    def test_strips_particles_after_punctuation_removal(self):
        assert _normalize_name("奥兰小红帽珍藏哈") == "奥兰小红帽珍藏"

    def test_lowercase_and_symbols(self):
        assert _normalize_name("Macallan 12 Double Cask!") == "macallan 12 double cask"

    def test_whitespace_collapse(self):
        assert _normalize_name("  拉菲   古堡  干红 ") == "拉菲 古堡 干红"

    def test_parentheses_content_kept(self):
        # （五号）去括号但保留内容
        result = _normalize_name("奥兰小红帽橡木桶干红葡萄酒（五号）")
        assert result == "奥兰小红帽橡木桶干红葡萄酒五号"
