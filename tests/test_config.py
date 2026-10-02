"""Tests for shared.config module."""

from shared.config import AppConfig, MySQLConfig, RedisConfig


class TestMySQLConfig:
    def test_default_values(self):
        cfg = MySQLConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 3306
        assert cfg.database == "mr_sheven"

    def test_url_format(self):
        cfg = MySQLConfig(user="root", password="pass", host="db", port=3306, database="test")
        url = cfg.url
        assert "mysql+pymysql://" in url
        assert "root:pass@db:3306/test" in url


class TestRedisConfig:
    def test_default_values(self):
        cfg = RedisConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 6379
        assert cfg.db == 0

    def test_url_without_auth(self):
        cfg = RedisConfig()
        assert cfg.url == "redis://127.0.0.1:6379/0"

    def test_url_with_auth(self):
        cfg = RedisConfig(password="secret")
        assert ":secret@" in cfg.url


class TestAppConfig:
    def test_default_config(self):
        cfg = AppConfig()
        assert cfg.env == "development"
        assert cfg.log_level == "INFO"
        assert isinstance(cfg.mysql, MySQLConfig)
        assert isinstance(cfg.redis, RedisConfig)